"""Yamato B2 Cloud persistent session.

Extends :class:`PersistentSession` for Yamato's business portal and B2 Cloud
waybill system.

Login flow:
    1. Navigate to bmypage.kuronekoyamato.co.jp (business portal)
    2. Fill customer code + password, submit
    3. Click "送り状発行システムB2クラウド" link → SSO to B2 Cloud
    4. Land on newb2web.kuronekoyamato.co.jp/main_menu.html

Waybill (送り状) flow:
    1. From B2 Cloud main menu, navigate to single_issue_reg.html
    2. Fill consignee, shipper, item details
    3. Click "印刷内容の確認へ" → confirmation page
    4. Click issue/print → result page with tracking number
    5. Download waybill PDF
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .. import config as cfg
from ..services.download import DownloadHandler
from .base import PersistentSession

log = logging.getLogger(__name__)

# Daily browser restart threshold (24 hours)
_DAILY_RESTART_SECS = 86400

# B2 Cloud URLs
_BMYPAGE_URL = "https://bmypage.kuronekoyamato.co.jp/"
_B2CLOUD_MENU = "https://newb2web.kuronekoyamato.co.jp/main_menu.html"
_B2CLOUD_SINGLE = "https://newb2web.kuronekoyamato.co.jp/single_issue_reg.html"


class YamatoSession(PersistentSession):
    """Persistent browser session for Yamato B2 Cloud."""

    def __init__(self, vault_client: Any) -> None:
        super().__init__(
            name="yamato",
            vault_client=vault_client,
            config_section="daemon.sessions.yamato",
        )
        self._download_handler = DownloadHandler()
        self._pdf_dir = cfg.pdf_dir() / "yamato"
        self._pdf_dir.mkdir(parents=True, exist_ok=True)
        self._browser_start_time: float = 0.0
        self._on_b2cloud: bool = False

    # ------------------------------------------------------------------
    # Persistent lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Launch browser, inject cookies, attempt login, record start time."""
        from ..browser.session import BrowserSession

        cookies, stored_ua = self.cookie_store.load()
        ua = stored_ua or self.user_agent

        session_id = f"yamato_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        self.browser = BrowserSession(
            session_name=self.name,
            session_id=session_id,
            user_agent=ua,
        )
        await self.browser.start()
        self._browser_start_time = time.monotonic()
        self._log.info("Persistent browser started for Yamato")

        # Inject cookies
        if cookies:
            if ua:
                self.user_agent = ua
            await self._apply_cookies_to_browser()
            self._log.info("Injected %d persisted cookies", len(cookies))

            # Try restoring session on B2 Cloud directly
            try:
                await self.browser.navigate(_B2CLOUD_MENU)
                await asyncio.sleep(random.uniform(3.0, 5.0))

                current_url = await self.browser.page.evaluate(
                    "window.location.href"
                )
                if "newb2web" in current_url:
                    self.is_logged_in = True
                    self._on_b2cloud = True
                    self.last_activity = datetime.now(timezone.utc)
                    self._log.info("Yamato B2 Cloud session restored from cookies")
                    return
            except Exception:
                self._log.debug("Cookie-based B2 Cloud session verification failed")

        # Cookies expired or missing — full login
        self._log.info("Cookies invalid/missing, attempting full login")
        success = await self.login()
        if success:
            self.is_logged_in = True
            self.last_activity = datetime.now(timezone.utc)
        else:
            self._log.warning("Initial Yamato login failed — human intervention may be needed")

    # ------------------------------------------------------------------
    # Keepalive
    # ------------------------------------------------------------------

    async def keepalive(self) -> bool:
        """Navigate B2 Cloud pages to keep the session alive.

        Returns ``False`` if the session has expired.
        """
        if self.browser is None or self.browser.page is None:
            self._log.warning("keepalive called with no active browser")
            return False

        # Check for daily restart
        elapsed = time.monotonic() - self._browser_start_time
        if elapsed > _DAILY_RESTART_SECS:
            self._log.info(
                "Browser running for %.1f hours — triggering daily restart",
                elapsed / 3600,
            )
            await self._daily_restart()
            return True

        try:
            page = self.browser.page

            # Navigate to B2 Cloud main menu (this exercises the session)
            await self.browser.navigate(_B2CLOUD_MENU)
            await asyncio.sleep(random.uniform(2.0, 4.0))

            # Check where we ended up
            current_url = await page.evaluate("window.location.href")

            if "newb2web" in current_url and "system_error" not in current_url:
                # Still on B2 Cloud — session alive
                self._on_b2cloud = True
                self.last_activity = datetime.now(timezone.utc)
                await self.save_cookies()
                self._log.debug("Yamato keepalive successful (on B2 Cloud)")
                return True

            if "system_error" in current_url:
                # B2 Cloud system error — session may be invalid
                self._log.warning("Yamato keepalive: B2 Cloud system error")
                self._on_b2cloud = False
                return False

            if "bmypage" in current_url:
                # Redirected to bmypage — check if it's the login form
                has_login = await page.evaluate(
                    "!!document.querySelector('#code1')"
                )
                if has_login:
                    self._log.warning("Yamato session expired (redirected to login)")
                    self._on_b2cloud = False
                    return False
                # On bmypage but not login — try navigating to B2 Cloud
                self._log.info("On bmypage dashboard, navigating to B2 Cloud")
                if await self._navigate_to_b2cloud():
                    self.last_activity = datetime.now(timezone.utc)
                    await self.save_cookies()
                    return True
                return False

            # Unknown page
            self._log.warning("Yamato keepalive: unexpected URL %s", current_url)
            return False

        except Exception:
            self._log.exception("Yamato keepalive failed")
            return False

    async def _daily_restart(self) -> None:
        """Save cookies, close browser, relaunch, re-login."""
        self._log.info("Performing daily browser restart")

        try:
            await self.save_cookies()
        except Exception:
            self._log.exception("Error saving cookies before daily restart")

        try:
            if self.browser is not None:
                await self.browser.close()
                self.browser = None
        except Exception:
            self._log.exception("Error closing browser during daily restart")

        self.is_logged_in = False
        self._on_b2cloud = False
        await self.start()

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    async def login(self) -> bool:
        """Log into Yamato business portal and navigate to B2 Cloud.

        Returns:
            ``True`` on success (browser is on B2 Cloud main menu).
            ``False`` if login fails.
        """
        if self.browser is None or self.browser.page is None:
            self._log.error("login called with no active browser")
            return False

        # Read credentials from environment variables (injected by K8s secret)
        creds = {
            "login_id": os.environ.get("YAMATO_LOGIN_ID", ""),
            "password": os.environ.get("YAMATO_PASSWORD", ""),
        }
        if not creds["login_id"] or not creds["password"]:
            self._log.error("Yamato credentials not found in environment")
            return False

        # Navigate to login page
        await self.browser.navigate(_BMYPAGE_URL)
        await asyncio.sleep(random.uniform(1.5, 3.0))

        try:
            page = self.browser.page

            # Fill credentials using JS (nodriver click/focus is unreliable on this site)
            login_result = await page.evaluate(
                """
                (function() {
                    var c = document.querySelector('#code1');
                    var p = document.querySelector('#password');
                    if (!c || !p) return 'no_form';
                    c.value = '%s';
                    p.value = '%s';
                    var btn = document.querySelector('a.login');
                    if (btn) { btn.click(); return 'ok'; }
                    return 'no_button';
                })()
                """
                % (creds["login_id"], creds["password"])
            )

            if login_result == "no_form":
                # Already logged in? Check URL
                current_url = await page.evaluate("window.location.href")
                if "LOGGEDIN" in current_url or "bmypage" in current_url:
                    self._log.info("Already logged in to bmypage")
                else:
                    self._log.warning("Login form not found")
                    return False
            elif login_result == "no_button":
                self._log.warning("Login button not found")
                return False
            else:
                await asyncio.sleep(random.uniform(4.0, 6.0))

            # Verify login succeeded
            current_url = await page.evaluate("window.location.href")
            has_login_form = await page.evaluate(
                "!!document.querySelector('#code1')"
            )

            if has_login_form and "LOGGEDIN" not in current_url:
                self._log.warning("Yamato login failed (login form still visible)")
                return False

            self._log.info("Yamato bmypage login successful")

            # Navigate to B2 Cloud
            if await self._navigate_to_b2cloud():
                self.is_logged_in = True
                self._on_b2cloud = True
                self.last_activity = datetime.now(timezone.utc)
                await self.save_cookies()
                return True

            # Couldn't reach B2 Cloud but bmypage login succeeded
            self._log.warning("bmypage login OK but B2 Cloud navigation failed")
            self.is_logged_in = True
            self._on_b2cloud = False
            await self.save_cookies()
            return True

        except Exception:
            self._log.exception("Yamato login failed")
            return False

    async def _navigate_to_b2cloud(self) -> bool:
        """Navigate to B2 Cloud via the bmypage SSO handshake.

        The bmypage portal exposes an AJAX endpoint ``ME0002.json`` that
        returns the B2 Cloud SSO entry URL (``serviceUrl``) when called
        with ``serviceId=06``.  Navigating to that URL in the same browser
        session completes the OAuth handshake and lands on B2 Cloud.

        Returns ``True`` if we successfully land on B2 Cloud.
        """
        if self.browser is None or self.browser.page is None:
            return False

        page = self.browser.page

        try:
            # Call ME0002.json to obtain the B2 Cloud SSO URL
            sso_url = await page.evaluate(
                """
                (function() {
                    var result = null;
                    try {
                        $.ajax({
                            async: false,
                            data: { serviceId: '06' },
                            dataType: 'json',
                            url: '/bmypage/ME0002.json',
                            type: 'POST',
                            traditional: false,
                            success: function(data) { result = data.serviceUrl || null; },
                            error: function() { result = null; }
                        });
                    } catch(e) { result = null; }
                    return result;
                })()
                """
            )

            if not sso_url:
                self._log.warning("ME0002.json did not return a service URL")
                return False

            self._log.info("B2 Cloud SSO URL: %s", sso_url)

            # Navigate to the SSO URL — this triggers the OAuth handshake
            # and redirects to B2 Cloud main menu
            await self.browser.navigate(sso_url)
            await asyncio.sleep(random.uniform(5.0, 8.0))

            # Verify we're on B2 Cloud
            current_url = await page.evaluate("window.location.href")
            if "newb2web" in current_url and "system_error" not in current_url:
                self._log.info("Navigated to B2 Cloud: %s", current_url)
                self._on_b2cloud = True
                return True

            self._log.warning(
                "B2 Cloud SSO navigation failed, landed on: %s", current_url
            )
            return False

        except Exception:
            self._log.exception("B2 Cloud navigation failed")
            return False

    # ------------------------------------------------------------------
    # Session health check
    # ------------------------------------------------------------------

    async def is_alive(self) -> bool:
        """Check if the Yamato session is still valid.

        Navigates to B2 Cloud main menu and checks whether we're
        redirected to login (expired) or stay on B2 Cloud (alive).
        """
        if self.browser is None or self.browser.page is None:
            return False

        try:
            page = self.browser.page

            await self.browser.navigate(_B2CLOUD_MENU)
            await asyncio.sleep(random.uniform(2.0, 4.0))

            current_url = await page.evaluate("window.location.href")

            if "newb2web" in current_url:
                self._on_b2cloud = True
                self._log.debug("Yamato session alive (on B2 Cloud)")
                return True

            # Check if we're on bmypage login
            has_login = await page.evaluate(
                "!!document.querySelector('#code1')"
            )
            if has_login:
                self._log.info("Yamato session expired (login form detected)")
                self._on_b2cloud = False
                return False

            # On bmypage but logged in — not expired, just not on B2 Cloud
            self._log.debug("Yamato session alive (on bmypage, not login)")
            self._on_b2cloud = False
            return True

        except Exception:
            self._log.exception("Yamato is_alive check failed")
            return False

    # ------------------------------------------------------------------
    # Waybill creation
    # ------------------------------------------------------------------

    async def create_waybill(self, params: dict[str, Any]) -> dict[str, Any]:
        """Navigate to B2 Cloud waybill form, fill details, submit, download PDF.

        Args:
            params: Shipment details dict with keys:
                - ``recipient_name`` (str): お届け先名称
                - ``recipient_kana`` (str, optional): カナ読み
                - ``recipient_postal`` (str): 郵便番号 (e.g. "104-8125")
                - ``recipient_address`` (str): 市区町村 + 丁目番地
                - ``recipient_building`` (str, optional): 建物名
                - ``recipient_phone`` (str): 電話番号
                - ``items_description`` (str): 品名 (e.g. "衣類")
                - ``sales_order_id`` (str): InvenTree order reference

        Returns:
            Dict with ``tracking_number`` and ``pdf_path`` on success.

        Raises:
            RuntimeError: If the waybill could not be created.
        """
        if self.browser is None or self.browser.page is None:
            raise RuntimeError("No active browser for waybill creation")

        page = self.browser.page

        # Configure downloads
        await self._download_handler.configure_browser(page, self._pdf_dir)

        # Step 1: Navigate to waybill form
        await self.browser.navigate(_B2CLOUD_SINGLE)
        await asyncio.sleep(random.uniform(3.0, 5.0))

        # Verify we're on the form page
        current_url = await page.evaluate("window.location.href")
        if "single_issue" not in current_url:
            # Session may have expired — try re-login
            self._log.warning("Not on waybill form, attempting re-login")
            if not await self.login():
                raise RuntimeError("Re-login failed during waybill creation")
            await self.browser.navigate(_B2CLOUD_SINGLE)
            await asyncio.sleep(random.uniform(3.0, 5.0))
            current_url = await page.evaluate("window.location.href")
            if "single_issue" not in current_url:
                raise RuntimeError(
                    f"Could not reach waybill form, on: {current_url}"
                )

        self._log.info("On waybill form: %s", current_url)

        # Step 2: Fill in shipment details
        await self._fill_shipment_form(params)

        # Step 3: Click "印刷内容の確認へ" (go to confirmation)
        # Use setTimeout to avoid CDP evaluate hanging if click triggers
        # a page navigation that destroys the execution context.
        try:
            confirm_result = await asyncio.wait_for(
                page.evaluate(
                    """
                    (function() {
                        var btn = document.querySelector('#confirm_issue_btn');
                        if (btn) { setTimeout(function() { btn.click(); }, 100); return 'found_clicking'; }
                        // Fallback: search by text
                        var all = document.querySelectorAll('a, button, input[type="button"]');
                        for (var i = 0; i < all.length; i++) {
                            var txt = (all[i].textContent || all[i].value || '').trim();
                            if (txt.indexOf('確認') >= 0 && txt.length < 30) {
                                var el = all[i];
                                setTimeout(function() { el.click(); }, 100);
                                return 'found_by_text: ' + txt;
                            }
                        }
                        return 'not_found';
                    })()
                    """
                ),
                timeout=10.0,
            )
        except asyncio.TimeoutError:
            confirm_result = "timeout"
        self._log.info("Confirm button: %s", confirm_result)
        await asyncio.sleep(random.uniform(5.0, 8.0))
        self._log.info("Waited after confirm click")

        # Check if we moved to confirmation page
        try:
            current_url = await asyncio.wait_for(
                page.evaluate("window.location.href"), timeout=10.0
            )
            title = await asyncio.wait_for(
                page.evaluate("document.title"), timeout=10.0
            )
        except asyncio.TimeoutError:
            self._log.warning("Timed out reading page URL/title after confirm")
            current_url = "unknown"
            title = "unknown"
        self._log.info("After confirm click: url=%s title=%s", current_url, title)

        # Check if we're still on the form page (validation errors)
        if "single_issue" in current_url and "print_check" not in current_url:
            # Still on the form — validation errors occurred
            try:
                err_text = await asyncio.wait_for(
                    page.evaluate(
                        """
                        (function() {
                            // Collect visible error messages
                            var errs = document.querySelectorAll(
                                '.error_msg, .error_msg_top, [class*="error"], .err, .validationError'
                            );
                            var result = [];
                            for (var i = 0; i < errs.length; i++) {
                                var t = errs[i].textContent.trim();
                                if (t && t.length < 200) result.push(t);
                            }
                            // Also check for tooltip-style errors
                            var tips = document.querySelectorAll('.ui-tooltip-content, [role="tooltip"]');
                            for (var j = 0; j < tips.length; j++) {
                                result.push('tooltip: ' + tips[j].textContent.trim());
                            }
                            return result.join(' | ') || 'no error elements found';
                        })()
                        """
                    ),
                    timeout=10.0,
                )
            except (asyncio.TimeoutError, Exception):
                err_text = "could not read errors"
            self._log.error(
                "Validation failed — still on form page. Errors: %s", err_text
            )
            raise RuntimeError(f"Form validation failed: {err_text}")

        # Take screenshot for debugging
        await self.browser.screenshot("waybill_confirm")

        # Log all buttons on the confirmation page for debugging
        try:
            buttons_info = await asyncio.wait_for(
                page.evaluate(
                    """
                    (function() {
                        var btns = document.querySelectorAll('a, button, input[type="button"], input[type="submit"]');
                        var result = [];
                        for (var i = 0; i < btns.length; i++) {
                            var txt = (btns[i].textContent || btns[i].value || '').trim();
                            if (txt && txt.length < 60) {
                                result.push({
                                    tag: btns[i].tagName,
                                    id: btns[i].id || '',
                                    cls: (btns[i].className || '').substring(0, 40),
                                    href: btns[i].href || '',
                                    text: txt
                                });
                            }
                        }
                        // Also look for any 12-digit numbers already on page
                        var numMatch = document.body.textContent.match(/\\d{4}[-\\s]?\\d{4}[-\\s]?\\d{4}/g);
                        return JSON.stringify({buttons: result, tracking_nums: numMatch});
                    })()
                    """
                ),
                timeout=10.0,
            )
            self._log.info("Confirm page elements: %s", buttons_info)
        except (asyncio.TimeoutError, Exception):
            self._log.warning("Could not enumerate confirm page elements")

        # Step 4: Click "発行開始" (start_print) on the confirmation page.
        # This button registers the waybill via AJAX and opens a PDF in a
        # hidden iframe (B2_OKURIJYO?issue_no=...&fileonly=1). The PDF is
        # a one-time download — subsequent requests return an HTML skeleton.
        #
        # Strategy: Enable CDP Network domain to capture the iframe's PDF
        # response body. After the click, use Network.getResponseBody to
        # extract the PDF bytes and parse them for the tracking number.
        import json as _json
        import nodriver as _uc

        # Enable CDP Fetch domain to intercept the B2_OKURIJYO PDF
        # response BEFORE Chrome's built-in PDF viewer consumes it.
        # The Fetch domain intercepts at the response stage, letting us
        # capture the raw PDF bytes.
        _captured_pdf_bytes: list[bytes] = []  # mutable container

        async def _on_fetch_paused(
            event: _uc.cdp.fetch.RequestPaused,
        ) -> None:
            """Capture B2_OKURIJYO PDF response body."""
            req_url = str(event.request.url)
            self._log.info(
                "Fetch paused: %s (status=%s)",
                req_url[:200],
                event.response_status_code,
            )
            try:
                # Get the response body (raw PDF bytes)
                body, is_b64 = await page.send(
                    _uc.cdp.fetch.get_response_body(
                        request_id=event.request_id
                    )
                )
                if body:
                    import base64 as _b64

                    if is_b64:
                        raw = _b64.b64decode(body)
                    else:
                        raw = body.encode("latin-1")
                    self._log.info(
                        "Captured response: %d bytes, starts=%s",
                        len(raw),
                        raw[:30],
                    )
                    _captured_pdf_bytes.append(raw)
            except Exception as e:
                self._log.warning(
                    "Fetch getResponseBody failed: %s", e
                )

            # Continue the response so Chrome can proceed normally
            try:
                await page.send(
                    _uc.cdp.fetch.continue_response(
                        request_id=event.request_id
                    )
                )
            except Exception:
                pass

        page.add_handler(
            _uc.cdp.fetch.RequestPaused, _on_fetch_paused
        )

        try:
            await page.send(
                _uc.cdp.fetch.enable(
                    patterns=[
                        _uc.cdp.fetch.RequestPattern(
                            url_pattern="*B2_OKURIJYO*fileonly*",
                            request_stage=_uc.cdp.fetch.RequestStage.RESPONSE,
                        )
                    ]
                )
            )
            self._log.info("CDP Fetch domain enabled for B2_OKURIJYO")
        except Exception as e:
            self._log.warning("Could not enable CDP Fetch: %s", e)

        # Install XHR interceptor for AJAX monitoring
        try:
            await asyncio.wait_for(
                page.evaluate(
                    """
                    (function() {
                        window.__b2_ajax_responses = [];
                        var origOpen = XMLHttpRequest.prototype.open;
                        var origSend = XMLHttpRequest.prototype.send;
                        XMLHttpRequest.prototype.open = function(method, url) {
                            this.__url = url;
                            return origOpen.apply(this, arguments);
                        };
                        XMLHttpRequest.prototype.send = function() {
                            var xhr = this;
                            xhr.addEventListener('load', function() {
                                window.__b2_ajax_responses.push({
                                    url: xhr.__url,
                                    status: xhr.status,
                                    response: xhr.responseText.substring(0, 4000)
                                });
                            });
                            return origSend.apply(this, arguments);
                        };
                    })()
                    """
                ),
                timeout=5.0,
            )
        except (asyncio.TimeoutError, Exception) as e:
            self._log.warning("Could not install XHR interceptor: %s", e)

        assert self.browser is not None and self.browser.browser is not None
        browser = self.browser.browser

        # Record target IDs before click to detect new popup targets
        pre_click_target_ids = {t.target.target_id for t in browser.targets}
        self._log.info("Targets before issue click: %d", len(pre_click_target_ids))

        # Click 発行開始 using jQuery only (single click)
        try:
            issue_result = await asyncio.wait_for(
                page.evaluate(
                    """
                    (function() {
                        var btn = document.querySelector('#start_print');
                        if (!btn) return JSON.stringify({status: 'not_found'});
                        btn.scrollIntoView({behavior: 'instant', block: 'center'});
                        var rect = btn.getBoundingClientRect();
                        var info = {
                            status: 'found',
                            text: btn.textContent.trim(),
                            visible: rect.width > 0 && rect.height > 0
                        };
                        if (typeof $ !== 'undefined') {
                            $('#start_print').click();
                            info.click_method = 'jquery_direct';
                        } else {
                            btn.click();
                            info.click_method = 'dom_direct';
                        }
                        return JSON.stringify(info);
                    })()
                    """
                ),
                timeout=10.0,
            )
            self._log.info("Issue button click: %s", issue_result)
        except asyncio.TimeoutError:
            self._log.warning("Issue button click timed out")

        # Wait for AJAX flow to complete.
        # B2 Cloud: POST /b2/p/new → poll /b2/p/polling → B2_OKURIJYO
        # After 3+ AJAX responses, wait extra time for popup to open.
        for wait_i in range(15):
            await asyncio.sleep(2.0)
            try:
                check_info = await asyncio.wait_for(
                    page.evaluate(
                        """
                        (function() {
                            var url = window.location.href;
                            var bodyText = document.body ? document.body.innerText : '';
                            var trackingMatch = bodyText.match(/\\d{4}[-\\s]?\\d{4}[-\\s]?\\d{4}/);
                            var ajaxCount = (window.__b2_ajax_responses || []).length;
                            return JSON.stringify({
                                url: url,
                                tracking_found: trackingMatch ? trackingMatch[0] : null,
                                ajax_count: ajaxCount,
                                target_count: %d
                            });
                        })()
                        """
                        % len(browser.targets)
                    ),
                    timeout=5.0,
                )
                info = _json.loads(check_info)
                self._log.info("Post-issue check %d: %s", wait_i + 1, check_info)

                if info.get("tracking_found"):
                    break
                if "print_check" not in info.get("url", ""):
                    break
                # After AJAX completes, wait for iframe to load the PDF
                # and for the main page to potentially update with tracking
                if info.get("ajax_count", 0) >= 3:
                    # Check if new targets appeared (iframe with PDF)
                    new_targets = [
                        t for t in browser.targets
                        if t.target.target_id not in pre_click_target_ids
                    ]
                    if new_targets:
                        self._log.info(
                            "New target(s) detected after AJAX: %d, "
                            "waiting for page to update...",
                            len(new_targets),
                        )
                        # Wait extra time for the page to update after
                        # the PDF iframe loads
                        await asyncio.sleep(5.0)
                        break
                    # Give iframe a few more cycles to appear
                    if wait_i >= 7:
                        self._log.info(
                            "AJAX done, no new targets after %d checks",
                            wait_i + 1,
                        )
                        break
            except (asyncio.TimeoutError, Exception):
                self._log.info("Post-issue check %d: evaluate timeout", wait_i + 1)
                break

        # Read intercepted AJAX responses
        ajax_responses = []
        issue_no = None
        try:
            ajax_data = await asyncio.wait_for(
                page.evaluate(
                    "JSON.stringify(window.__b2_ajax_responses || [])"
                ),
                timeout=5.0,
            )
            ajax_responses = _json.loads(ajax_data)
            self._log.info(
                "Captured %d AJAX response(s)", len(ajax_responses)
            )
            for resp in ajax_responses:
                self._log.info(
                    "AJAX: %s (status=%s) -> %s",
                    resp.get("url", "?"),
                    resp.get("status", "?"),
                    str(resp.get("response", ""))[:500],
                )
                resp_text = resp.get("response", "")
                if "/b2/p/new" in resp.get("url", ""):
                    try:
                        resp_json = _json.loads(resp_text)
                        issue_no = resp_json.get("feed", {}).get("title", "")
                        if issue_no:
                            self._log.info("Issue number: %s", issue_no)
                    except (ValueError, TypeError):
                        pass
        except (asyncio.TimeoutError, Exception) as e:
            self._log.warning("Could not read AJAX responses: %s", e)

        # Take screenshot of current state
        await self.browser.screenshot("waybill_after_issue")

        # Disable Fetch intercept to avoid affecting subsequent requests
        try:
            await page.send(_uc.cdp.fetch.disable())
        except Exception:
            pass

        # Log captured PDF and save it immediately
        self._log.info(
            "Captured %d PDF response(s) via Fetch",
            len(_captured_pdf_bytes),
        )

        # --- Extract tracking number ---
        tracking_number = None
        _pdf_save_path: Path | None = None

        # Save the first valid PDF from Fetch capture
        for _fb in _captured_pdf_bytes:
            if _fb[:5] == b"%PDF-" and issue_no:
                _pdf_save_path = self._pdf_dir / f"{issue_no}.pdf"
                _pdf_save_path.write_bytes(_fb)
                self._log.info(
                    "Saved Fetch-captured PDF: %s (%d bytes)",
                    _pdf_save_path,
                    len(_fb),
                )
                break

        # Strategy 1: Check main page for tracking numbers
        try:
            main_page_data = await asyncio.wait_for(
                page.evaluate(
                    """
                    (function() {
                        var text = document.body ? document.body.innerText : '';
                        var matches = text.match(/\\d{4}[-\\s]?\\d{4}[-\\s]?\\d{4}/g);
                        var tds = document.querySelectorAll('td');
                        var tdNums = [];
                        for (var i = 0; i < tds.length; i++) {
                            var t = tds[i].textContent.trim();
                            if (/^\\d{12}$/.test(t)) tdNums.push(t);
                        }
                        return JSON.stringify({
                            url: window.location.href,
                            matches: matches,
                            td_nums: tdNums
                        });
                    })()
                    """
                ),
                timeout=5.0,
            )
            mpd = _json.loads(main_page_data)
            if mpd.get("td_nums"):
                tracking_number = mpd["td_nums"][0]
                self._log.info("Found tracking on main page (td): %s", tracking_number)
            elif mpd.get("matches"):
                for m in mpd["matches"]:
                    cleaned = re.sub(r"[^\d]", "", m)
                    if len(cleaned) == 12:
                        tracking_number = cleaned
                        self._log.info("Found tracking on main page: %s", tracking_number)
                        break
        except (asyncio.TimeoutError, Exception):
            pass

        # Strategy 2: Search AJAX responses for tracking numbers
        if not tracking_number:
            for resp in ajax_responses:
                resp_text = resp.get("response", "")
                for m in re.findall(r"\d{4}[-\s]?\d{4}[-\s]?\d{4}", resp_text):
                    cleaned = re.sub(r"[^\d]", "", m)
                    if len(cleaned) == 12:
                        tracking_number = cleaned
                        self._log.info("Found tracking in AJAX: %s", tracking_number)
                        break
                if tracking_number:
                    break

        # Strategy 3: Parse the PDF captured by CDP Fetch interceptor.
        # The Fetch handler captured the raw response body of the
        # B2_OKURIJYO?fileonly=1 iframe request — the actual PDF bytes
        # before Chrome's PDF viewer consumed them.
        #
        # Use pypdf structured text extraction FIRST — raw binary scan
        # catches false positives from PDF stream/object data.
        if not tracking_number and _captured_pdf_bytes:
            for pdf_idx, pdf_bytes in enumerate(_captured_pdf_bytes):
                self._log.info(
                    "Processing captured PDF #%d: %d bytes, "
                    "starts=%s",
                    pdf_idx,
                    len(pdf_bytes),
                    pdf_bytes[:30],
                )

                # Check if it's actually a PDF
                if pdf_bytes[:5] != b"%PDF-":
                    self._log.info(
                        "Captured data is not PDF: %s",
                        pdf_bytes[:100],
                    )
                    continue

                # pypdf structured extraction (preferred — no false positives)
                try:
                    from pypdf import PdfReader
                    import io

                    reader = PdfReader(io.BytesIO(pdf_bytes))
                    for pg_i, pg in enumerate(reader.pages):
                        pg_text = pg.extract_text() or ""
                        self._log.info(
                            "PDF page %d text (%d chars): %s",
                            pg_i,
                            len(pg_text),
                            pg_text[:500],
                        )
                        # Look for hyphenated tracking first (most reliable)
                        for m in re.findall(
                            r"\d{4}-\d{4}-\d{4}", pg_text
                        ):
                            cleaned = re.sub(r"[^\d]", "", m)
                            if len(cleaned) == 12:
                                tracking_number = cleaned
                                self._log.info(
                                    "Found tracking in PDF (hyphenated): %s",
                                    tracking_number,
                                )
                                break
                        if not tracking_number:
                            for m in re.findall(
                                r"\d{4}[\s-]?\d{4}[\s-]?\d{4}",
                                pg_text,
                            ):
                                cleaned = re.sub(r"[^\d]", "", m)
                                if len(cleaned) == 12:
                                    tracking_number = cleaned
                                    self._log.info(
                                        "Found tracking in PDF: %s",
                                        tracking_number,
                                    )
                                    break
                        if tracking_number:
                            break
                except ImportError:
                    self._log.info("pypdf not available, falling back to binary scan")
                    # Fallback: raw binary scan
                    pdf_text = pdf_bytes.decode(
                        "latin-1", errors="ignore"
                    )
                    for m in re.findall(
                        r"\d{4}-\d{4}-\d{4}", pdf_text
                    ):
                        cleaned = re.sub(r"[^\d]", "", m)
                        if len(cleaned) == 12:
                            tracking_number = cleaned
                            self._log.info(
                                "Found tracking in PDF binary: %s",
                                tracking_number,
                            )
                            break
                except Exception as e:
                    self._log.warning("pypdf failed: %s", e)

                if tracking_number:
                    break
        elif not tracking_number:
            self._log.info("No PDF captured by Fetch interceptor")

        # Take final screenshot
        await self.browser.screenshot("waybill_result")

        if not tracking_number:
            raise RuntimeError("Could not extract tracking number from result page")

        # Step 6: Use the Fetch-captured PDF if available, otherwise try download
        pdf_path: Path | None = None
        if _pdf_save_path and _pdf_save_path.exists():
            # Rename to include tracking number for easier lookup
            final_pdf = self._pdf_dir / f"{tracking_number}.pdf"
            if _pdf_save_path != final_pdf:
                _pdf_save_path.rename(final_pdf)
            pdf_path = final_pdf
            self._log.info("Using Fetch-captured PDF: %s", pdf_path)
        else:
            pdf_path = await self._download_waybill_pdf(
                params.get("sales_order_id", "unknown"),
                tracking_number,
            )

        result = {
            "tracking_number": tracking_number,
            "pdf_path": str(pdf_path) if pdf_path else None,
        }

        self._log.info(
            "Waybill created: tracking=%s pdf=%s",
            tracking_number,
            pdf_path,
        )
        self.last_activity = datetime.now(timezone.utc)
        return result

    async def _fill_shipment_form(self, params: dict[str, Any]) -> None:
        """Fill the B2 Cloud waybill form fields using JS for reliability."""
        assert self.browser is not None
        page = self.browser.page

        # Helper: set value via JS and trigger change event
        async def set_field(selector: str, value: str) -> bool:
            if not value:
                return True
            result = await page.evaluate(
                """
                (function() {
                    var el = document.querySelector('%s');
                    if (!el) return false;
                    el.focus();
                    el.value = '%s';
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                    return true;
                })()
                """
                % (selector.replace("'", "\\'"), value.replace("'", "\\'"))
            )
            if not result:
                self._log.warning("Field not found: %s", selector)
            return bool(result)

        # --- Consignee (お届け先) ---
        await set_field("#consignee_telephone", params.get("recipient_phone", ""))
        await asyncio.sleep(random.uniform(0.2, 0.5))

        # Postal code — set value but do NOT click zip lookup button.
        # The zip lookup opens a modal popup that requires manual selection.
        # Instead, fill address fields directly below.
        postal = params.get("recipient_postal", "")
        if postal:
            await set_field("#consignee_zip_code", postal)
            await asyncio.sleep(random.uniform(0.3, 0.5))

        # Address fields — fill directly (no auto-fill from postal code)
        address = params.get("recipient_address", "")
        if address:
            # Split address: first token is city/district, rest is street
            parts = address.split(" ", 1) if " " in address else [address, ""]
            await set_field("#consignee_address02", parts[0])
            await asyncio.sleep(random.uniform(0.2, 0.4))
            if len(parts) > 1 and parts[1]:
                await set_field("#consignee_address03", parts[1])
            else:
                await set_field("#consignee_address03", address)
            await asyncio.sleep(random.uniform(0.2, 0.4))

        # Building
        building = params.get("recipient_building", "")
        if building:
            await set_field("#consignee_address04", building)
            await asyncio.sleep(random.uniform(0.2, 0.4))

        # Recipient name — unnamed field, select by placeholder
        name = params.get("recipient_name", "")
        if name:
            await page.evaluate(
                """
                (function() {
                    var container = document.getElementById('todoke_info');
                    if (!container) return;
                    var inputs = container.querySelectorAll('input[type="text"]');
                    for (var i = 0; i < inputs.length; i++) {
                        if (inputs[i].placeholder && inputs[i].placeholder.indexOf('ヤマト運輸') >= 0) {
                            inputs[i].focus();
                            inputs[i].value = '%s';
                            inputs[i].dispatchEvent(new Event('input', {bubbles: true}));
                            inputs[i].dispatchEvent(new Event('change', {bubbles: true}));
                            break;
                        }
                    }
                })()
                """
                % name.replace("'", "\\'")
            )
            await asyncio.sleep(random.uniform(0.2, 0.4))

        # Recipient kana
        kana = params.get("recipient_kana", "")
        if kana:
            await page.evaluate(
                """
                (function() {
                    var container = document.getElementById('todoke_info');
                    if (!container) return;
                    var inputs = container.querySelectorAll('input[type="text"]');
                    for (var i = 0; i < inputs.length; i++) {
                        if (inputs[i].placeholder && inputs[i].placeholder.indexOf('ｸﾛﾈｺ') >= 0) {
                            inputs[i].focus();
                            inputs[i].value = '%s';
                            inputs[i].dispatchEvent(new Event('input', {bubbles: true}));
                            inputs[i].dispatchEvent(new Event('change', {bubbles: true}));
                            break;
                        }
                    }
                })()
                """
                % kana.replace("'", "\\'")
            )
            await asyncio.sleep(random.uniform(0.2, 0.4))

        # --- Shipper (ご依頼主) ---
        # Fill from params or fall back to SHIPPER_* env defaults.
        shipper_phone = params.get("shipper_phone", "") or os.environ.get(
            "SHIPPER_PHONE", ""
        )
        if shipper_phone:
            await set_field("#shipper_telephone", shipper_phone)
            await asyncio.sleep(random.uniform(0.2, 0.4))

        shipper_postal = params.get("shipper_postal", "") or os.environ.get(
            "SHIPPER_POSTAL", ""
        )
        if shipper_postal:
            await set_field("#shipper_zip_code", shipper_postal)
            await asyncio.sleep(random.uniform(0.3, 0.5))

        shipper_city = params.get("shipper_city", "") or os.environ.get(
            "SHIPPER_CITY", ""
        )
        if shipper_city:
            await set_field("#shipper_address2", shipper_city)
            await asyncio.sleep(random.uniform(0.2, 0.4))

        shipper_street = params.get("shipper_street", "") or os.environ.get(
            "SHIPPER_STREET", ""
        )
        if shipper_street:
            await set_field("#shipper_address3", shipper_street)
            await asyncio.sleep(random.uniform(0.2, 0.4))

        shipper_name = params.get("shipper_name", "") or os.environ.get(
            "SHIPPER_NAME", ""
        )
        if shipper_name:
            await page.evaluate(
                """
                (function() {
                    var container = document.getElementById('irainusi_Info');
                    if (!container) return;
                    var inputs = container.querySelectorAll('input[type="text"]');
                    for (var i = 0; i < inputs.length; i++) {
                        if (inputs[i].placeholder && inputs[i].placeholder.indexOf('ヤマト運輸') >= 0) {
                            inputs[i].focus();
                            inputs[i].value = '%s';
                            inputs[i].dispatchEvent(new Event('input', {bubbles: true}));
                            inputs[i].dispatchEvent(new Event('change', {bubbles: true}));
                            break;
                        }
                    }
                })()
                """
                % shipper_name.replace("'", "\\'")
            )

        # --- Item description (品名) ---
        await set_field("#item_name1", params.get("items_description", ""))
        await asyncio.sleep(random.uniform(0.2, 0.4))

        # Take screenshot after filling
        await self.browser.screenshot("waybill_filled")
        self._log.info("Waybill form filled")

    async def _extract_tracking_number(self) -> str | None:
        """Extract the tracking number from the result page."""
        assert self.browser is not None
        page = self.browser.page

        # Try various selectors and patterns
        tracking = await page.evaluate(
            """
            (function() {
                // Look for tracking number in common locations
                var selectors = [
                    '.tracking_number', '.trackingNo', '#tracking_number',
                    'td[id*="tracking"]', 'span[id*="tracking"]',
                    'td[id*="denpyo"]', 'span[id*="denpyo"]'
                ];
                for (var i = 0; i < selectors.length; i++) {
                    var el = document.querySelector(selectors[i]);
                    if (el && el.textContent.trim()) {
                        return el.textContent.trim();
                    }
                }
                // Fallback: look for 12-digit number pattern in page text
                var text = document.body.textContent;
                var match = text.match(/\\b(\\d{4}[-\\s]?\\d{4}[-\\s]?\\d{4})\\b/);
                if (match) return match[1].replace(/[-\\s]/g, '');
                return null;
            })()
            """
        )

        if tracking:
            # Clean up: remove non-digit chars
            cleaned = re.sub(r"[^\d]", "", str(tracking))
            if len(cleaned) >= 12:
                self._log.info("Extracted tracking number: %s", cleaned)
                return cleaned

        # Fallback: try Gemini page analysis
        try:
            from ..vision.page_analyzer import analyze_page

            ss = await self.browser.screenshot("tracking_result")
            page_state = analyze_page(ss)
            t = page_state.get("tracking_number")
            if t:
                return str(t)
        except Exception:
            self._log.debug("Gemini tracking extraction not available")

        return None

    async def _download_waybill_pdf(
        self,
        sales_order_id: str,
        tracking_number: str,
    ) -> Path | None:
        """Click the download/print button and wait for the PDF.

        Returns the path to the downloaded PDF, or ``None`` on failure.
        """
        assert self.browser is not None
        page = self.browser.page

        # Click print/download button
        click_result = await page.evaluate(
            """
            (function() {
                var selectors = [
                    '#print_btn', 'a[id*="print"]', 'input[id*="print"]',
                    '#download_btn', 'a[id*="download"]'
                ];
                for (var i = 0; i < selectors.length; i++) {
                    var el = document.querySelector(selectors[i]);
                    if (el) { el.click(); return 'clicked: ' + selectors[i]; }
                }
                // Fallback: text search
                var all = document.querySelectorAll('a, button, input[type="button"]');
                for (var j = 0; j < all.length; j++) {
                    var text = all[j].textContent.trim() || all[j].value || '';
                    if (text.indexOf('印刷') >= 0 && text.length < 20) {
                        all[j].click();
                        return 'clicked_text: ' + text;
                    }
                }
                return 'not_found';
            })()
            """
        )
        self._log.info("Print button click: %s", click_result)

        if click_result == "not_found":
            self._log.warning("Could not find print/download button")
            return None

        # Wait for PDF to appear
        pdf_path = await self._download_handler.wait_for_download(
            self._pdf_dir, timeout_secs=60
        )

        if pdf_path is None:
            self._log.warning("PDF download timed out")
            return None

        # Verify it is a valid PDF
        if not self._download_handler.verify_pdf(pdf_path):
            self._log.warning("Downloaded file is not a valid PDF")
            return None

        # Rename to standard format
        target_name = self._download_handler.generate_filename(
            carrier="yamato",
            sales_order_id=sales_order_id,
            tracking_number=tracking_number,
        )
        target_path = self._pdf_dir / target_name
        pdf_path.rename(target_path)
        self._log.info("PDF saved: %s", target_path)

        return target_path
