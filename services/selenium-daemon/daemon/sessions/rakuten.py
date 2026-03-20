"""Rakuten RMS persistent session.

Migrated from ``rakuten_renewal/agent/main.py`` ``shared_steps()`` into the
Browser Daemon's persistent session model.  The browser stays running between
jobs, with a KeepAlive service periodically navigating safe pages to prevent
session expiry.

Login flow:
    1. Navigate to RMS login page.
    2. Detect page state via Gemini screenshot analysis.
    3. Handle page types in a loop: login_form -> 2FA -> CAPTCHA -> dashboard.
    4. 2FA codes are polled from Firestore (deposited by Email Sentinel).
    5. If login fails after ``login_max_retries``, return ``False``
       (caller sets ``PENDING_USER_LOGIN``).
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from datetime import datetime, timezone
from typing import Any

from .. import config as cfg
from ..browser.session import BrowserSession
from ..vision.captcha import analyze_page, solve_captcha, verify_action
from .base import PersistentSession

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Firestore 2FA polling (inlined from rakuten_renewal/agent/firestore_poll.py)
# ---------------------------------------------------------------------------

_WIF_CRED_PATH = "/app/Vault/pki/wif-credential-config.json"


def _firestore_client() -> Any:
    """Create a Firestore client using WIF credentials."""
    from google.cloud import firestore
    from google.auth import identity_pool
    import os

    cred_path = os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS", _WIF_CRED_PATH
    )
    creds = identity_pool.Credentials.from_file(cred_path)
    scoped = creds.with_scopes(
        ["https://www.googleapis.com/auth/datastore"]
    )
    return firestore.Client(
        project=cfg.cfg("daemon.sentinel.firestore_project"),
        credentials=scoped,
    )


async def _poll_2fa_code(
    poll_interval: int | None = None,
    timeout: int | None = None,
) -> str | None:
    """Poll Firestore for a fresh 2FA code deposited by Email Sentinel.

    Returns the code string, or ``None`` on timeout.
    """
    interval = poll_interval or cfg.cfg("daemon.sentinel.poll_interval_secs")
    max_wait = timeout or cfg.cfg("daemon.sentinel.poll_timeout_secs")

    from google.cloud import firestore as fs_module

    db = _firestore_client()
    doc_ref = (
        db.collection("auth")
        .document("rakuten")
        .collection("data")
        .document("current_2fa")
    )

    start = time.monotonic()
    while time.monotonic() - start < max_wait:
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            if data and not data.get("consumed", True):
                code = data.get("code")
                doc_ref.update({
                    "consumed": True,
                    "consumed_at": fs_module.SERVER_TIMESTAMP,
                })
                log.info(
                    "2FA code retrieved (waited %.1fs)",
                    time.monotonic() - start,
                )
                return code

        await asyncio.sleep(interval)

    log.warning("2FA poll timed out after %ds", max_wait)
    return None


# ---------------------------------------------------------------------------
# Prompt versioning helper
# ---------------------------------------------------------------------------

def _current_prompt_version() -> int:
    """Find the highest ``captcha_vN.txt`` version number."""
    prompts = cfg.prompts_dir()
    versions: list[int] = []
    for f in prompts.glob("captcha_v*.txt"):
        try:
            v = int(f.stem.split("_v")[1])
            versions.append(v)
        except (IndexError, ValueError):
            continue
    return max(versions) if versions else 1


# ---------------------------------------------------------------------------
# Safe pages for keepalive navigation
# ---------------------------------------------------------------------------

_SAFE_PAGES = [
    # Order list
    "https://order-rms.rms.rakuten.co.jp/order-rb/normalorder-search/",
    # Shop settings
    "https://mainmenu.rms.rakuten.co.jp/rms/mall/shopinfo/",
    # Product list
    "https://item.rms.rakuten.co.jp/rms/mall/item/search/",
]


# ======================================================================
# RakutenSession
# ======================================================================


class RakutenSession(PersistentSession):
    """Persistent browser session for Rakuten RMS.

    Absorbs the login flow from ``rakuten_renewal/agent/main.py``
    ``shared_steps()`` including CAPTCHA solving and 2FA polling.
    """

    def __init__(self, vault_client: Any) -> None:
        super().__init__(
            name="rakuten",
            vault_client=vault_client,
            config_section="daemon.sessions.rakuten",
        )
        self._home_url: str = cfg.cfg("daemon.sessions.rakuten.home_url")
        self._api_key_url: str = cfg.cfg("daemon.sessions.rakuten.api_key_url")

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    async def login(self) -> bool:
        """Full Rakuten RMS login flow.

        Navigates to the RMS login page, fills credentials, solves
        CAPTCHAs via Gemini, and handles 2FA via Firestore polling.

        Returns:
            ``True`` on successful login.
            ``False`` if automated login failed after max retries
            (caller should set ``PENDING_USER_LOGIN``).
        """
        max_retries = self.login_max_retries

        for attempt in range(1, max_retries + 1):
            self._log.info(
                "Login attempt %d/%d", attempt, max_retries
            )
            try:
                success = await self._login_attempt()
                if success:
                    self.is_logged_in = True
                    self.last_activity = datetime.now(timezone.utc)
                    await self.save_cookies()
                    self._log.info("Login successful on attempt %d", attempt)
                    return True
            except Exception:
                self._log.exception("Login attempt %d failed", attempt)

            if attempt < max_retries:
                delay = random.uniform(5.0, 15.0)
                self._log.info("Retrying login in %.1fs", delay)
                await asyncio.sleep(delay)

        self._log.warning(
            "Login failed after %d attempts, requesting human intervention",
            max_retries,
        )
        return False

    async def _login_attempt(self) -> bool:
        """Single login attempt. Returns ``True`` on success."""
        # Ensure browser is running
        if self.browser is None:
            self.browser = BrowserSession(
                session_name="rakuten",
                user_agent=self.user_agent,
            )
            await self.browser.start()

        # Try restoring from cookies first
        cookies, ua = self.cookie_store.load()
        if cookies:
            await self._apply_cookies_to_browser()

        # Fetch credentials from Vault
        creds = self._vault.read("rakuten/rms")

        # Navigate to login page
        await self.browser.navigate(self.login_url)

        # Page state analysis loop
        max_page_transitions = 20
        prompt_version = _current_prompt_version()

        for step in range(max_page_transitions):
            ss = await self.browser.screenshot(f"login_step_{step}")
            page_state = analyze_page(ss)
            page_type = page_state.get("page_type", "unknown")
            self._log.info(
                "Step %d: page_type=%s has_captcha=%s",
                step,
                page_type,
                page_state.get("has_captcha"),
            )

            if page_type == "login_form":
                await self._handle_login_form(page_state, creds)

            elif page_type == "2fa_prompt":
                success = await self._handle_2fa(page_state)
                if not success:
                    return False

            elif page_type == "captcha_challenge" or page_state.get("has_captcha"):
                await self._handle_captcha(ss, page_state, prompt_version)

            elif page_type == "dashboard":
                self._log.info("Reached dashboard -- login successful")
                return True

            elif page_type == "api_key_management":
                self._log.info(
                    "Reached API key management page -- login successful"
                )
                return True

            elif page_type == "error_page":
                self._log.error(
                    "Error page encountered: %s",
                    page_state.get("error_text", "unknown"),
                )
                return False

            else:
                self._log.warning(
                    "Unknown page type '%s', navigating to home",
                    page_type,
                )
                await self.browser.navigate(self._home_url)
                await asyncio.sleep(random.uniform(2.0, 4.0))

        self._log.error("Exceeded max page transitions (%d)", max_page_transitions)
        return False

    # ------------------------------------------------------------------
    # Page handlers
    # ------------------------------------------------------------------

    async def _handle_login_form(
        self,
        page_state: dict[str, Any],
        creds: dict[str, str],
    ) -> None:
        """Fill login form fields and submit."""
        assert self.browser is not None

        elements = page_state.get("interactive_elements", [])

        # Find fields by label heuristics
        id_field = next(
            (e for e in elements
             if e.get("type") == "text_input"
             and "id" in e.get("label", "").lower()),
            None,
        )
        pw_field = next(
            (e for e in elements
             if e.get("type") == "text_input"
             and "pass" in e.get("label", "").lower()),
            None,
        )
        login_btn = next(
            (e for e in elements
             if e.get("type") == "button"
             and "login" in e.get("label", "").lower()),
            None,
        )

        if id_field:
            bbox = id_field["bbox"]
            cx = bbox["x"] + bbox["w"] // 2
            cy = bbox["y"] + bbox["h"] // 2
            await self.browser.move_mouse(cx, cy)
            await self.browser.click(cx, cy)
            await asyncio.sleep(random.uniform(0.3, 0.8))
            await self.browser.type_text(creds["login_id"])
            await asyncio.sleep(random.uniform(0.5, 1.5))

        if pw_field:
            bbox = pw_field["bbox"]
            cx = bbox["x"] + bbox["w"] // 2
            cy = bbox["y"] + bbox["h"] // 2
            await self.browser.move_mouse(cx, cy)
            await self.browser.click(cx, cy)
            await asyncio.sleep(random.uniform(0.3, 0.8))
            await self.browser.type_text(creds["password"])
            await asyncio.sleep(random.uniform(0.5, 1.0))

        if login_btn:
            bbox = login_btn["bbox"]
            cx = bbox["x"] + bbox["w"] // 2
            cy = bbox["y"] + bbox["h"] // 2
            await self.browser.move_mouse(cx, cy)
            await asyncio.sleep(random.uniform(0.3, 0.7))
            await self.browser.click(cx, cy)
            await asyncio.sleep(random.uniform(2.0, 4.0))

        self._log.info("Login form submitted")

    async def _handle_2fa(
        self,
        page_state: dict[str, Any],
    ) -> bool:
        """Handle 2FA prompt by polling Firestore for the code.

        Returns ``True`` if 2FA was successfully entered, ``False`` on
        timeout.
        """
        assert self.browser is not None

        self._log.info("2FA prompt detected, polling Firestore")
        code = await _poll_2fa_code()
        if code is None:
            self._log.warning("2FA code not received (timeout)")
            return False

        self._log.info("2FA code received")

        # Find input field and submit button
        elements = page_state.get("interactive_elements", [])
        code_field = next(
            (e for e in elements if e.get("type") == "text_input"),
            None,
        )
        submit_btn = next(
            (e for e in elements if e.get("type") == "button"),
            None,
        )

        if code_field:
            bbox = code_field["bbox"]
            cx = bbox["x"] + bbox["w"] // 2
            cy = bbox["y"] + bbox["h"] // 2
            await self.browser.move_mouse(cx, cy)
            await self.browser.click(cx, cy)
            await asyncio.sleep(random.uniform(0.3, 0.6))
            await self.browser.type_text(code)
            await asyncio.sleep(random.uniform(0.5, 1.0))

        if submit_btn:
            bbox = submit_btn["bbox"]
            cx = bbox["x"] + bbox["w"] // 2
            cy = bbox["y"] + bbox["h"] // 2
            await self.browser.move_mouse(cx, cy)
            await asyncio.sleep(random.uniform(0.2, 0.5))
            await self.browser.click(cx, cy)
            await asyncio.sleep(random.uniform(2.0, 4.0))

        return True

    async def _handle_captcha(
        self,
        screenshot_path: Any,
        page_state: dict[str, Any],
        prompt_version: int,
    ) -> None:
        """Solve a CAPTCHA using Gemini and execute the solution actions."""
        assert self.browser is not None

        self._log.info("CAPTCHA detected, solving with Gemini")
        solution = solve_captcha(screenshot_path, prompt_version=prompt_version)
        confidence = solution.get("confidence", 0)
        self._log.info(
            "CAPTCHA solution: type=%s confidence=%.2f actions=%d",
            solution.get("challenge", {}).get("type"),
            confidence,
            len(solution.get("actions", [])),
        )

        # Execute CAPTCHA actions
        actions = solution.get("actions", [])
        if actions:
            from ..browser.actions import execute_actions
            await execute_actions(self.browser, actions)

        await asyncio.sleep(random.uniform(1.0, 2.0))

        # Verify action success
        after_ss = await self.browser.screenshot("post_captcha")
        verification = verify_action(screenshot_path, after_ss)
        success = verification.get("action_succeeded", False)
        if not success:
            self._log.warning(
                "CAPTCHA solve may have failed: %s",
                verification.get("summary"),
            )

    # ------------------------------------------------------------------
    # Keep-alive
    # ------------------------------------------------------------------

    async def keepalive(self) -> bool:
        """Navigate to a random safe page and back to maintain session.

        Returns ``False`` if the session appears to have expired.
        """
        if self.browser is None or self.browser.page is None:
            self._log.warning("keepalive: no active browser")
            return False

        safe_page = random.choice(_SAFE_PAGES)
        self._log.debug("Keepalive: navigating to %s", safe_page)

        try:
            await self.browser.navigate(safe_page)

            # Human-like browsing: random scroll + wait
            scroll_amount = random.randint(200, 600)
            await self.browser.scroll(
                x=960, y=540, delta_y=scroll_amount, smooth=True
            )
            await asyncio.sleep(random.uniform(2.0, 3.0))

            # Navigate back to dashboard
            await self.browser.navigate(self._home_url)
            await asyncio.sleep(random.uniform(1.0, 2.0))

            # Quick check that we're still logged in
            alive = await self.is_alive()
            if alive:
                self.last_activity = datetime.now(timezone.utc)
            return alive

        except Exception:
            self._log.exception("Keepalive navigation failed")
            return False

    # ------------------------------------------------------------------
    # Session health check
    # ------------------------------------------------------------------

    async def is_alive(self) -> bool:
        """Check if still authenticated using selectors first.

        Only falls back to Gemini on ambiguous results.
        """
        if self.browser is None or self.browser.page is None:
            return False

        try:
            # Fast check: login form visible → session expired
            login_el = await self.find_element("login.username_input")
            if login_el:
                self._log.info("Rakuten session expired (login form detected)")
                return False

            # Fast check: dashboard element visible → still alive
            dash_el = await self.find_element("dashboard.main_menu")
            if dash_el:
                self._log.debug("Rakuten session alive (dashboard detected)")
                return True

            # API key page also means authenticated
            api_el = await self.find_element("api_key.key_table")
            if api_el:
                self._log.debug("Rakuten session alive (API key page detected)")
                return True

            # Ambiguous — fall back to Gemini
            self._log.debug("Rakuten is_alive: ambiguous page, falling back to Gemini")
            try:
                ss = await self.browser.screenshot("health_check")
                page_state = analyze_page(ss)
                page_type = page_state.get("page_type", "unknown")

                if page_type in ("login_form", "2fa_prompt", "error_page"):
                    self._log.info("Session expired (Gemini: %s)", page_type)
                    return False

                self._log.debug("Rakuten session alive (Gemini: %s)", page_type)
                return True
            except Exception:
                self._log.warning("Gemini fallback failed; assuming session alive")
                return True

        except Exception:
            self._log.exception("is_alive check failed")
            return False
