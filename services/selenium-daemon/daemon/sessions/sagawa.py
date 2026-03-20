"""Sagawa e飛伝III on-demand session.

Extends :class:`OnDemandSession` for Sagawa's e飛伝III (e-Hiden III) business
portal.  The flow spans two domains and two browser tabs:

    1. **Smart Club** (``www.e-service.sagawa-exp.co.jp``)
       - Keycloak SSO login (法人 tab → fill user2/pass2 → click login)
       - Dashboard → click 送り状発行（e飛伝Ⅲ）quick menu

    2. **e飛伝III** (``e-hiden3.sagawa-exp.co.jp``, new tab)
       - Element UI SPA
       - Service popup → select 飛脚宅配便
       - Fill waybill form → 登録 (register) → 印刷 (print)
       - Extract tracking number (問い合わせNo.)
       - Download waybill PDF

The browser is launched per-job and killed afterward, with cookies
persisted to disk.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import nodriver as uc

from .. import config as cfg
from ..services.download import DownloadHandler
from .base import OnDemandSession

log = logging.getLogger(__name__)


class SagawaSession(OnDemandSession):
    """On-demand browser session for Sagawa e飛伝III (e-Hiden III)."""

    def __init__(self, vault_client: Any) -> None:
        super().__init__(
            name="sagawa",
            vault_client=vault_client,
            config_section="daemon.sessions.sagawa",
        )
        self._download_handler = DownloadHandler()
        self._pdf_dir = cfg.pdf_dir() / "sagawa"
        self._pdf_dir.mkdir(parents=True, exist_ok=True)
        # e飛伝III runs in a separate tab from Smart Club
        self._ehiden_tab: uc.Tab | None = None

    # ------------------------------------------------------------------
    # Cookie refresh (called by scheduler)
    # ------------------------------------------------------------------

    async def refresh_cookies(self) -> None:
        """Refresh Sagawa session cookies by launching an ephemeral browser."""
        self._log.info("Starting cookie refresh")
        try:
            await self.acquire_browser()

            if self.is_logged_in and await self.is_alive():
                self._log.info("Session alive, saving refreshed cookies")
                await self.save_cookies()
            else:
                self._log.info("Session expired, attempting login")
                success = await self.login()
                if success:
                    self._log.info("Cookie refresh login succeeded")
                    await self.save_cookies()
                else:
                    self._log.warning("Cookie refresh login failed")
        finally:
            await self.release_browser()

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    async def login(self) -> bool:
        """Log into Sagawa Smart Club (法人 / business login).

        Returns:
            ``True`` on success.
            ``False`` if login fails.
        """
        if self.browser is None or self.browser.page is None:
            self._log.error("login called with no active browser")
            return False

        # Read credentials from environment variables (injected by K8s secret)
        creds = {
            "user_id": os.environ.get("SAGAWA_USER_ID", ""),
            "password": os.environ.get("SAGAWA_PASSWORD", ""),
        }
        if not creds["user_id"] or not creds["password"]:
            self._log.error("Sagawa credentials not found in environment")
            return False

        page = self.browser.page

        # Navigate to login page (redirects to Keycloak SSO)
        await self.browser.navigate(self.login_url)
        await asyncio.sleep(random.uniform(3.0, 5.0))

        try:
            # Click 法人 (business) tab — default is 個人 (personal)
            biz_tab = await self.find_element("login.business_tab")
            if biz_tab:
                await biz_tab.click()
                await asyncio.sleep(random.uniform(0.5, 1.0))
                self._log.debug("Clicked business login tab")
            else:
                self._log.warning("Could not find business tab, proceeding")

            # Fill user ID via JavaScript (Element UI inputs need event dispatch)
            await page.evaluate(
                f"""(function() {{
                    var el = document.querySelector('#user2');
                    if (el) {{
                        el.value = '{creds["user_id"]}';
                        el.dispatchEvent(new Event('input', {{bubbles: true}}));
                    }}
                }})()"""
            )
            await asyncio.sleep(random.uniform(0.3, 0.8))

            # Fill password
            await page.evaluate(
                f"""(function() {{
                    var el = document.querySelector('#pass2');
                    if (el) {{
                        el.value = '{creds["password"]}';
                        el.dispatchEvent(new Event('input', {{bubbles: true}}));
                    }}
                }})()"""
            )
            await asyncio.sleep(random.uniform(0.3, 0.8))

            # Submit login
            login_btn = await self.find_element("login.login_button")
            if login_btn:
                await login_btn.click()
                await asyncio.sleep(random.uniform(5.0, 8.0))
            else:
                self._log.warning("Could not find login button")
                return False

            # Check login result — Smart Club dashboard shows ログアウト
            body_text = await page.evaluate(
                "document.body.innerText.substring(0, 500)"
            )
            if "ログアウト" in str(body_text) and "様" in str(body_text):
                self._log.info("Sagawa Smart Club login successful")
                self.is_logged_in = True
                self.last_activity = datetime.now(timezone.utc)
                await self.save_cookies()
                return True

            # Still on login page?
            still_login = await page.evaluate(
                "!!document.querySelector('#user2')"
            )
            if still_login:
                self._log.warning("Sagawa login failed (login form still visible)")
                return False

            # Unexpected page — assume success if no login form
            self._log.info("Sagawa login assumed successful (no login form)")
            self.is_logged_in = True
            self.last_activity = datetime.now(timezone.utc)
            await self.save_cookies()
            return True

        except Exception:
            self._log.exception("Sagawa login failed")
            return False

    # ------------------------------------------------------------------
    # Session health check
    # ------------------------------------------------------------------

    async def is_alive(self) -> bool:
        """Check if the Sagawa session is still valid."""
        if self.browser is None or self.browser.page is None:
            return False

        try:
            await self.browser.navigate(self.login_url)
            await asyncio.sleep(random.uniform(2.0, 4.0))

            page = self.browser.page

            # Login form visible → session expired
            still_login = await page.evaluate(
                "!!document.querySelector('#user2')"
            )
            if still_login:
                self._log.info("Sagawa session expired (login form detected)")
                return False

            # Dashboard text → still alive
            body_text = await page.evaluate(
                "document.body.innerText.substring(0, 500)"
            )
            if "ログアウト" in str(body_text):
                self._log.debug("Sagawa session alive (dashboard detected)")
                return True

            self._log.debug("Sagawa is_alive: ambiguous page")
            return True

        except Exception:
            self._log.exception("Sagawa is_alive check failed")
            return False

    # ------------------------------------------------------------------
    # Navigate to e飛伝III waybill form
    # ------------------------------------------------------------------

    async def _navigate_to_ehiden_form(self) -> uc.Tab | None:
        """Navigate from Smart Club dashboard to e飛伝III waybill form.

        Returns the e飛伝III Tab object, or None on failure.
        """
        if self.browser is None or self.browser.page is None:
            return None

        page = self.browser.page
        browser = page.browser

        # Count current tabs
        initial_targets = browser.targets
        initial_count = len(initial_targets)

        # Click e飛伝III quick menu link (opens new tab)
        clicked = await page.evaluate("""
            (function() {
                var el = document.querySelector('#svcMenuQuickMenu-0');
                if (el) { el.click(); return true; }
                // Fallback: main menu link
                el = document.querySelector('#svcMenuParcel-0');
                if (el) { el.click(); return true; }
                return false;
            })()
        """)
        if not clicked:
            self._log.error("Could not find e飛伝III link on dashboard")
            return None

        # Wait for new tab to open
        self._log.info("Clicked e飛伝III link, waiting for new tab...")
        ehiden_tab = None
        for _ in range(20):  # 20 * 0.5s = 10s max
            await asyncio.sleep(0.5)
            targets = browser.targets
            if len(targets) > initial_count:
                for t in targets:
                    if "e-hiden3" in t.target.url:
                        ehiden_tab = t
                        break
                if ehiden_tab:
                    break

        if not ehiden_tab:
            self._log.error("e飛伝III tab did not open")
            return None

        self._log.info(
            "e飛伝III tab opened: %s", ehiden_tab.target.url[:100]
        )
        await asyncio.sleep(random.uniform(3.0, 5.0))

        # Click 送り状作成 (create waybill) button on e飛伝III menu
        await ehiden_tab.evaluate("""
            (function() {
                var btns = document.querySelectorAll('button');
                for (var i = 0; i < btns.length; i++) {
                    var text = (btns[i].textContent || '');
                    if (text.indexOf('送り状作成') >= 0 &&
                        text.indexOf('1件ずつ') >= 0) {
                        btns[i].click();
                        return;
                    }
                }
            })()
        """)
        await asyncio.sleep(random.uniform(2.0, 3.0))

        # Select 飛脚宅配便 from service popup
        selected = await ehiden_tab.evaluate("""
            (function() {
                var btns = document.querySelectorAll('button.svcPopupBtn');
                for (var i = 0; i < btns.length; i++) {
                    if ((btns[i].textContent || '').trim() === '飛脚宅配便') {
                        btns[i].click();
                        return true;
                    }
                }
                return false;
            })()
        """)
        if not selected:
            self._log.error("Could not find 飛脚宅配便 button in popup")
            return None

        self._log.info("Selected 飛脚宅配便, waiting for form...")
        await asyncio.sleep(random.uniform(5.0, 8.0))

        # Verify we're on the waybill form page
        title = await ehiden_tab.evaluate("document.title")
        if "送り状作成" in str(title):
            self._log.info("On waybill form page: %s", title)
        else:
            self._log.warning("Unexpected page title: %s", title)

        self._ehiden_tab = ehiden_tab
        return ehiden_tab

    # ------------------------------------------------------------------
    # Waybill creation
    # ------------------------------------------------------------------

    async def create_waybill(self, params: dict[str, Any]) -> dict[str, Any]:
        """Navigate to waybill form, fill details, register, download PDF.

        Args:
            params: Shipment details dict with keys:
                - ``recipient_name`` (str)
                - ``recipient_address`` (str)
                - ``recipient_postal`` (str, 999-9999 format)
                - ``recipient_phone`` (str, with hyphens)
                - ``items_description`` (str)
                - ``sales_order_id`` (str)

        Returns:
            Dict with ``tracking_number`` and ``pdf_path`` on success.

        Raises:
            RuntimeError: If the waybill could not be created.
        """
        if self.browser is None or self.browser.page is None:
            raise RuntimeError("No active browser for waybill creation")

        # Step 1: Navigate to e飛伝III waybill form
        ehiden_tab = await self._navigate_to_ehiden_form()
        if ehiden_tab is None:
            raise RuntimeError("Failed to navigate to e飛伝III waybill form")

        # Step 2: Fill shipment details
        await self._fill_shipment_form(ehiden_tab, params)

        # Step 3: Click 印刷 (print) to register + print in one step.
        # This assigns the tracking number and generates the PDF.
        # Using 登録 only saves without assigning a tracking number.
        tracking_number, pdf_path = await self._print_waybill(
            ehiden_tab, params.get("sales_order_id", "unknown")
        )
        if not tracking_number:
            raise RuntimeError(
                "Could not extract tracking number after printing"
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

    async def _fill_shipment_form(
        self, tab: uc.Tab, params: dict[str, Any]
    ) -> None:
        """Fill the e飛伝III waybill form fields.

        Uses CDP ``Input.insertText`` to type into focused fields. This
        approach works with Vue.js / Element UI because it simulates real
        keyboard input, unlike ``el.value = ...`` which bypasses Vue
        reactivity.

        The postal code 反映 (reflect) button is NOT used because it causes
        Vue.js to re-render the entire form, invalidating all DOM elements.
        Instead, all address lines are filled manually.
        """

        async def type_into_field(field_id: str, value: str) -> None:
            """Focus field, clear it, type via CDP insertText."""
            if not value:
                return
            # Focus and select existing text
            await tab.evaluate(f"""
                (function() {{
                    var el = document.querySelector('{field_id}');
                    if (el) {{ el.focus(); el.click(); el.select(); }}
                }})()
            """)
            await asyncio.sleep(0.2)
            # Ctrl+A then Delete to clear
            await tab.send(uc.cdp.input_.dispatch_key_event(
                type_="keyDown", key="a", modifiers=2
            ))
            await tab.send(uc.cdp.input_.dispatch_key_event(
                type_="keyUp", key="a"
            ))
            await tab.send(uc.cdp.input_.dispatch_key_event(
                type_="keyDown", key="Delete"
            ))
            await tab.send(uc.cdp.input_.dispatch_key_event(
                type_="keyUp", key="Delete"
            ))
            await asyncio.sleep(0.1)
            # Insert text
            await tab.send(uc.cdp.input_.insert_text(text=value))
            await asyncio.sleep(random.uniform(0.3, 0.6))

        # Parse address into lines (all manual, no 反映 auto-fill)
        address = params.get("recipient_address", "")
        addr_parts = self._split_address(address)

        # Fill recipient fields
        await type_into_field(
            "#input-otdkSkTel",
            params.get("recipient_phone", ""),
        )
        await type_into_field(
            "#input-otdkSkYbn",
            params.get("recipient_postal", ""),
        )

        # Fill address lines manually
        await type_into_field(
            "#input-otdkSkJsy1", addr_parts.get("line1", "")
        )
        await type_into_field(
            "#input-otdkSkJsy2", addr_parts.get("line2", "")
        )
        if addr_parts.get("line3"):
            await type_into_field(
                "#input-otdkSkJsy3", addr_parts["line3"]
            )

        # Recipient name
        name = params.get("recipient_name", "")
        name_parts = self._split_name(name)
        await type_into_field(
            "#input-otdkSkNm1", name_parts.get("line1", "")
        )
        if name_parts.get("line2"):
            await type_into_field(
                "#input-otdkSkNm2", name_parts["line2"]
            )

        # Item description (品名)
        items_desc = params.get("items_description", "化粧品")
        await type_into_field("#input-hinNm-1", items_desc[:16])

        # Customer reference number (optional)
        if params.get("sales_order_id"):
            await type_into_field(
                "#input-kyakuKnrNo", params["sales_order_id"][:16]
            )

        self._log.info("Filled waybill form fields")

    async def _print_waybill(
        self, tab: uc.Tab, sales_order_id: str
    ) -> tuple[str | None, Path | None]:
        """Click 印刷 to register, print, download ZIP, and extract tracking.

        e飛伝III's 印刷 (print) flow:
          1. Click footer 印刷 → opens print settings dialog
          2. Click inner 印刷 in dialog → downloads a ZIP file
          3. ZIP contains: a PDF waybill + a JSON metadata file
          4. Tracking number (お問い合せ送り状No.) is in the PDF text

        The tracking number is NOT shown in the web interface's print list.
        It is only in the downloaded PDF.

        Returns:
            Tuple of (tracking_number, pdf_path).  Either may be ``None``.
        """
        import json
        import shutil
        import tempfile
        import zipfile

        # Set up download directory via CDP
        download_dir = Path(tempfile.mkdtemp(prefix="sagawa_dl_"))
        try:
            await tab.send(
                uc.cdp.browser.set_download_behavior(
                    behavior="allow",
                    download_path=str(download_dir),
                )
            )
            self._log.info("CDP downloads configured: %s", download_dir)
        except Exception:
            self._log.warning(
                "browser.setDownloadBehavior failed, trying page-level"
            )
            try:
                await tab.send(
                    uc.cdp.page.set_download_behavior(
                        behavior="allow",
                        download_path=str(download_dir),
                    )
                )
            except Exception:
                self._log.exception("Could not configure CDP downloads")

        # Snapshot existing files before download
        existing_files: set[Path] = set(download_dir.glob("*"))

        # Step 1: Click footer 印刷 button → opens print settings dialog
        clicked = await tab.evaluate("""
            (function() {
                var btns = document.querySelectorAll('button');
                for (var i = 0; i < btns.length; i++) {
                    var text = (btns[i].textContent || '').trim();
                    var cls = btns[i].className || '';
                    if (text === '印刷' && cls.indexOf('footer-button') >= 0) {
                        btns[i].click();
                        return true;
                    }
                }
                return false;
            })()
        """)
        if not clicked:
            self._log.error("Could not find footer 印刷 button")
            shutil.rmtree(download_dir, ignore_errors=True)
            return None, None

        self._log.info("Clicked footer 印刷, waiting for settings dialog...")
        await asyncio.sleep(random.uniform(3.0, 5.0))

        # Step 2: Click inner 印刷 in the print settings dialog
        # The dialog title contains '出力条件設定' or '印刷方法'
        inner_result = await tab.evaluate("""
            (function() {
                var wrappers = document.querySelectorAll(
                    '.el-dialog__wrapper'
                );
                for (var i = 0; i < wrappers.length; i++) {
                    var style = window.getComputedStyle(wrappers[i]);
                    if (style.display === 'none') continue;
                    var text = (wrappers[i].textContent || '');
                    if (text.indexOf('出力条件設定') >= 0 ||
                        text.indexOf('印刷方法') >= 0) {
                        var btns = wrappers[i].querySelectorAll('button');
                        for (var j = 0; j < btns.length; j++) {
                            if ((btns[j].textContent || '').trim() === '印刷') {
                                btns[j].click();
                                return 'clicked';
                            }
                        }
                        return 'no_print_button_in_dialog';
                    }
                }
                return 'no_print_dialog';
            })()
        """)

        if inner_result != "clicked":
            self._log.error(
                "Print settings dialog issue: %s", inner_result
            )
            shutil.rmtree(download_dir, ignore_errors=True)
            return None, None

        self._log.info("Clicked inner 印刷, waiting for download...")

        # Step 3: Wait for ZIP download
        zip_path: Path | None = None
        for _ in range(30):  # 30s max
            await asyncio.sleep(1.0)
            current_files = set(download_dir.glob("*"))
            new_files = current_files - existing_files
            # Skip .crdownload partial files
            completed = [
                f for f in new_files if not f.name.endswith(".crdownload")
            ]
            if completed:
                zip_path = completed[0]
                break

        if not zip_path or not zip_path.exists():
            self._log.error("No download received in %s", download_dir)
            # Dismiss any dialog before returning
            await self._dismiss_visible_dialog(tab)
            shutil.rmtree(download_dir, ignore_errors=True)
            return None, None

        self._log.info(
            "Downloaded: %s (%d bytes)",
            zip_path.name,
            zip_path.stat().st_size,
        )

        # Dismiss the "ダウンロード完了" dialog
        await self._dismiss_visible_dialog(tab)

        # Step 4: Extract PDF from ZIP
        pdf_path: Path | None = None
        tracking_number: str | None = None

        try:
            if zipfile.is_zipfile(zip_path):
                extract_dir = download_dir / "extracted"
                extract_dir.mkdir(exist_ok=True)

                with zipfile.ZipFile(zip_path) as zf:
                    zf.extractall(extract_dir)
                    self._log.debug(
                        "ZIP contents: %s",
                        [i.filename for i in zf.infolist()],
                    )

                # Find the PDF
                pdf_files = list(extract_dir.glob("*.pdf"))
                if pdf_files:
                    src_pdf = pdf_files[0]

                    # Step 5: Extract tracking from PDF text
                    tracking_number = self._extract_tracking_from_pdf(
                        src_pdf
                    )

                    # Copy PDF to permanent location
                    final_name = self._download_handler.generate_filename(
                        "sagawa",
                        sales_order_id,
                        tracking_number or "unknown",
                    )
                    final_path = self._pdf_dir / final_name
                    shutil.copy2(src_pdf, final_path)
                    pdf_path = final_path
                    self._log.info("PDF saved: %s", final_path)
                else:
                    self._log.warning("No PDF found in ZIP")
            else:
                self._log.warning(
                    "Downloaded file is not a ZIP: %s", zip_path.name
                )
        except Exception:
            self._log.exception("Failed to process downloaded ZIP")
        finally:
            # Clean up temp download directory
            shutil.rmtree(download_dir, ignore_errors=True)

        return tracking_number, pdf_path

    async def _dismiss_visible_dialog(self, tab: uc.Tab) -> None:
        """Dismiss any visible dialog by clicking OK or 閉じる."""
        await tab.evaluate("""
            (function() {
                var wrappers = document.querySelectorAll(
                    '.el-dialog__wrapper, .el-message-box__wrapper'
                );
                for (var i = 0; i < wrappers.length; i++) {
                    var style = window.getComputedStyle(wrappers[i]);
                    if (style.display === 'none') continue;
                    var btns = wrappers[i].querySelectorAll('button');
                    for (var j = 0; j < btns.length; j++) {
                        var text = (btns[j].textContent || '').trim();
                        if (text === 'OK' || text === '閉じる') {
                            btns[j].click();
                            return;
                        }
                    }
                }
            })()
        """)
        await asyncio.sleep(random.uniform(1.0, 2.0))

    @staticmethod
    def _extract_tracking_from_pdf(pdf_path: Path) -> str | None:
        """Extract tracking number from Sagawa waybill PDF.

        The PDF contains ``お問い合せ送り状№：XXXX-XXXX-XXXX`` where the
        tracking number is 12 digits formatted with hyphens.

        Falls back to searching for any 12-digit number if the labelled
        pattern is not found.
        """
        try:
            from pypdf import PdfReader
        except ImportError:
            log.warning("pypdf not installed, cannot extract tracking from PDF")
            return None

        try:
            reader = PdfReader(str(pdf_path))
            full_text = ""
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    full_text += text

            if not full_text:
                log.warning("No text extracted from PDF: %s", pdf_path.name)
                return None

            # Pattern 1: Labelled tracking number
            # お問い合せ送り状№：4405-6213-4891
            m = re.search(
                r"お問い合せ送り状[NＮ№][\s：:]*"
                r"(\d{4}[-‐−]\d{4}[-‐−]\d{4})",
                full_text,
            )
            if m:
                # Return without hyphens (12 digits)
                tracking = re.sub(r"[-‐−]", "", m.group(1))
                log.info(
                    "Extracted tracking from PDF label: %s", tracking
                )
                return tracking

            # Pattern 2: Any 12-digit number (less reliable)
            numbers = re.findall(r"\d{12}", full_text)
            if numbers:
                # Filter out known non-tracking numbers (e.g. customer code)
                for num in numbers:
                    if not num.startswith("1256"):  # customer code prefix
                        log.info(
                            "Extracted tracking from PDF (12-digit): %s",
                            num,
                        )
                        return num

            log.warning(
                "No tracking number found in PDF text (%d chars)",
                len(full_text),
            )
            return None

        except Exception:
            log.exception("Failed to extract tracking from PDF: %s", pdf_path)
            return None

    # ------------------------------------------------------------------
    # Address / Name splitting helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _split_address(address: str) -> dict[str, str]:
        """Split a full Japanese address into e飛伝III address lines.

        e飛伝III has 3 address fields of 16 full-width chars each:
          - line1: 都道府県 + 市区町村 (auto-filled from postal code)
          - line2: 番地 (street/building number)
          - line3: 建物名・部屋番号 (building/room)

        If postal code auto-fill is used, only line2+line3 need to be set.
        """
        if not address:
            return {}

        # Remove prefecture prefix if present (auto-filled from postal)
        prefectures = [
            "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県",
            "福島県", "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県",
            "東京都", "神奈川県", "新潟県", "富山県", "石川県", "福井県",
            "山梨県", "長野県", "岐阜県", "静岡県", "愛知県", "三重県",
            "滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県",
            "鳥取県", "島根県", "岡山県", "広島県", "山口県", "徳島県",
            "香川県", "愛媛県", "高知県", "福岡県", "佐賀県", "長崎県",
            "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県",
        ]

        addr = address.strip()
        pref = ""
        for p in prefectures:
            if addr.startswith(p):
                pref = p
                addr = addr[len(p):]
                break

        # Try splitting on space
        parts = addr.split(None, 1)
        if len(parts) == 2:
            return {
                "line1": pref + parts[0],
                "line2": parts[1],
                "line3": "",
            }

        # No space — try splitting at first number character
        m = re.search(r"[0-9０-９]", addr)
        if m:
            city = addr[:m.start()]
            street = addr[m.start():]
            return {
                "line1": pref + city,
                "line2": street,
                "line3": "",
            }

        # Single block — put it all in line1
        return {
            "line1": pref + addr,
            "line2": "",
            "line3": "",
        }

    @staticmethod
    def _split_name(name: str) -> dict[str, str]:
        """Split recipient name into two lines if needed (16 chars each)."""
        if not name:
            return {}
        if len(name) <= 16:
            return {"line1": name}
        return {"line1": name[:16], "line2": name[16:32]}
