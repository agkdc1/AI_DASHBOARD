"""Abstract base classes for browser sessions.

Defines two session models:

* **PersistentSession** -- browser stays running between jobs.  Used for
  Rakuten RMS where CAPTCHA/2FA complexity makes on-demand login impractical.
* **OnDemandSession** -- browser is launched per-job and killed afterward.
  Used for Yamato B2 Cloud and Sagawa e飛伝III to save RAM on the 8 GB Pi.

Both models share a common ``BaseSession`` ABC that provides cookie
persistence, selector loading, element lookup with adaptive XPath repair,
and a human-fallback cookie injection pathway.
"""

from __future__ import annotations

import abc
import asyncio
import logging
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TYPE_CHECKING

import yaml
import nodriver as uc

from .. import config as cfg
from ..services.cookie_store import CookieStore

if TYPE_CHECKING:
    from ..browser.session import BrowserSession

log = logging.getLogger(__name__)


class BaseSession(abc.ABC):
    """Abstract base class for all browser sessions.

    Provides common infrastructure:
    - Cookie persistence via :class:`CookieStore`
    - Selector loading from YAML
    - Element lookup with XPath repair fallback
    - Cookie injection (human-fallback Chrome Extension flow)
    """

    def __init__(
        self,
        name: str,
        vault_client: Any,
        config_section: str | None = None,
    ) -> None:
        """Initialise a session.

        Args:
            name: Session identifier (``"rakuten"``, ``"yamato"``, etc.).
            vault_client: An authenticated :class:`VaultClient` instance.
            config_section: Dot-path to this session's config section.
                            Defaults to ``"daemon.sessions.{name}"``.
        """
        self.name = name
        self._vault = vault_client
        self._config_section = config_section or f"daemon.sessions.{name}"
        self._log = logging.getLogger(f"{__name__}.{name}")

        # Browser state
        self.browser: BrowserSession | None = None
        self.is_logged_in: bool = False
        self.last_activity: datetime = datetime.now(timezone.utc)

        # User-agent synced from human browser (if injected)
        self.user_agent: str | None = None

        # Selectors from YAML
        self.selectors: dict[str, Any] = {}
        self._selector_descriptions: dict[str, str] = {}
        self._load_selectors()

        # Cookie store (disk-persisted)
        self.cookie_store = CookieStore(
            session_name=name,
            cookie_dir=cfg.cookie_dir(),
        )

        # Restore user-agent from cookie store
        _, stored_ua = self.cookie_store.load()
        if stored_ua:
            self.user_agent = stored_ua

    # ------------------------------------------------------------------
    # Config helpers
    # ------------------------------------------------------------------

    def _cfg(self, key: str) -> Any:
        """Read a config value under this session's config section."""
        return cfg.cfg(f"{self._config_section}.{key}")

    @property
    def login_url(self) -> str:
        return self._cfg("login_url")

    @property
    def login_max_retries(self) -> int:
        return self._cfg("login_max_retries")

    # ------------------------------------------------------------------
    # Selector loading
    # ------------------------------------------------------------------

    def _load_selectors(self) -> None:
        """Load CSS/XPath selectors from ``selectors/{name}.yaml``."""
        selectors_file = cfg.selectors_dir() / f"{self.name}.yaml"
        if not selectors_file.exists():
            self._log.warning(
                "Selector file not found: %s", selectors_file
            )
            return

        try:
            data = yaml.safe_load(selectors_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                self._log.warning("Selectors file is not a YAML dict")
                return

            # Extract _descriptions metadata section
            self._selector_descriptions = data.pop("_descriptions", {})
            self.selectors = data
            self._log.info(
                "Loaded selectors: %d sections from %s",
                len(self.selectors),
                selectors_file.name,
            )
        except Exception:
            self._log.exception("Failed to load selectors from %s", selectors_file)

    def _get_selector(self, selector_key: str) -> str | None:
        """Resolve a dot-separated selector key.

        E.g. ``"login.username_input"`` -> value from
        ``selectors["login"]["username_input"]``.
        """
        parts = selector_key.split(".")
        current: Any = self.selectors
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current if isinstance(current, str) else None

    def _get_selector_description(self, selector_key: str) -> str:
        """Get the human description for a selector key (for XPath repair)."""
        return self._selector_descriptions.get(
            selector_key,
            f"Element referenced by selector key '{selector_key}'",
        )

    # ------------------------------------------------------------------
    # Abstract methods
    # ------------------------------------------------------------------

    @abc.abstractmethod
    async def login(self) -> bool:
        """Full login flow.

        Returns ``True`` on success. Returns ``False`` if human
        intervention is needed (triggers ``PENDING_USER_LOGIN`` in the
        job queue).
        """

    @abc.abstractmethod
    async def is_alive(self) -> bool:
        """Check whether the session cookies are still valid.

        Returns ``True`` if the browser is on an authenticated page.
        """

    async def ensure_logged_in(self) -> None:
        """Verify session and re-login if expired.

        Subclasses override this to add browser-specific logic.
        """
        if self.browser is not None and await self.is_alive():
            self._log.debug("Session is alive")
            return

        self._log.info("Session not alive, attempting login")
        success = await self.login()
        if not success:
            raise RuntimeError(
                f"Login failed for session '{self.name}'"
            )

    # ------------------------------------------------------------------
    # Element lookup
    # ------------------------------------------------------------------

    async def find_element(
        self,
        selector_key: str,
        timeout: float = 10.0,
    ) -> Any | None:
        """Find an element using a selector from the YAML config.

        If the selector does not match any element, attempts adaptive
        XPath repair via Gemini Flash.

        Args:
            selector_key: Dot-separated key into the selectors dict,
                          e.g. ``"login.username_input"``.
            timeout: Seconds to wait for the element.

        Returns:
            The nodriver Element, or ``None`` if not found even after
            repair.
        """
        if self.browser is None or self.browser.page is None:
            self._log.warning("find_element called with no active browser")
            return None

        selector_value = self._get_selector(selector_key)
        if selector_value is None:
            self._log.warning(
                "Selector key '%s' not found in selectors YAML",
                selector_key,
            )
            return None

        # Try finding the element directly
        page = self.browser.page
        try:
            element = await asyncio.wait_for(
                page.find(selector_value, timeout=timeout),
                timeout=timeout + 2,
            )
            if element is not None:
                return element
        except (asyncio.TimeoutError, Exception):
            self._log.debug(
                "Selector '%s' (%s) did not match, attempting repair",
                selector_key,
                selector_value,
            )

        # Attempt XPath repair via Gemini Flash
        try:
            from ..vision.xpath_repair import repair_selector

            description = self._get_selector_description(selector_key)

            # Get page HTML and URL for repair context
            html = await page.evaluate("document.documentElement.outerHTML")
            if isinstance(html, str) and len(html) > 50000:
                html = html[:50000]

            current_url = ""
            try:
                current_url = await page.evaluate("window.location.href")
            except Exception:
                pass

            new_selector = repair_selector(
                session_name=self.name,
                selector_key=selector_key,
                old_selector=selector_value,
                description=description,
                page_html=html,
                url=current_url or "",
            )

            if new_selector:
                self._log.info(
                    "Selector repaired: '%s' -> '%s'",
                    selector_value,
                    new_selector,
                )
                element = await page.find(new_selector, timeout=timeout)
                return element
        except ImportError:
            self._log.debug("xpath_repair module not available")
        except Exception:
            self._log.exception("XPath repair failed for '%s'", selector_key)

        return None

    # ------------------------------------------------------------------
    # Cookie management
    # ------------------------------------------------------------------

    async def inject_cookies(
        self,
        cookies: list[dict[str, Any]],
        user_agent: str | None = None,
    ) -> None:
        """Apply cookies (and optional UA) from the Chrome Extension.

        1. Save to disk via CookieStore.
        2. If a browser is running, apply cookies via CDP immediately.

        Args:
            cookies: List of cookie dicts from the Chrome Extension.
            user_agent: The human operator's User-Agent string.
        """
        # Persist
        self.cookie_store.save(cookies, user_agent)
        if user_agent:
            self.user_agent = user_agent

        # Apply to running browser
        if self.browser is not None and self.browser.page is not None:
            await self._apply_cookies_to_browser()
            self._log.info(
                "Injected %d cookies into running browser", len(cookies)
            )
        else:
            self._log.info(
                "Saved %d cookies to disk (no running browser)", len(cookies)
            )

    async def save_cookies(self) -> None:
        """Export current browser cookies via CDP and persist to disk."""
        if self.browser is None or self.browser.page is None:
            self._log.debug("save_cookies: no active browser")
            return

        try:
            # Use CDP to get all cookies from the browser
            result = await self.browser.page.send(
                uc.cdp.network.get_cookies()
            )
            cookies: list[dict[str, Any]] = []
            for cookie in result:
                entry: dict[str, Any] = {
                    "name": cookie.name,
                    "value": cookie.value,
                    "domain": cookie.domain,
                    "path": cookie.path,
                    "secure": cookie.secure,
                    "httpOnly": cookie.http_only,
                }
                if cookie.same_site is not None:
                    entry["sameSite"] = cookie.same_site.value
                if cookie.expires is not None and cookie.expires > 0:
                    entry["expires"] = int(cookie.expires)
                cookies.append(entry)

            self.cookie_store.save(cookies, self.user_agent)
            self._log.info("Saved %d browser cookies to disk", len(cookies))
        except Exception:
            self._log.exception("Failed to export browser cookies")

    async def _apply_cookies_to_browser(self) -> None:
        """Load cookies from CookieStore and inject into the browser via CDP."""
        if self.browser is None or self.browser.page is None:
            return

        cookies, user_agent = self.cookie_store.load()
        if not cookies:
            self._log.debug("No cookies to apply")
            return

        page = self.browser.page

        for cookie in cookies:
            try:
                # Build CDP setCookie params (nodriver uses snake_case)
                params: dict[str, Any] = {
                    "name": cookie["name"],
                    "value": cookie["value"],
                    "domain": cookie.get("domain", ""),
                    "path": cookie.get("path", "/"),
                }
                if cookie.get("secure"):
                    params["secure"] = True
                if cookie.get("httpOnly"):
                    params["http_only"] = True
                if cookie.get("sameSite"):
                    _ss_map = {
                        "Strict": uc.cdp.network.CookieSameSite.STRICT,
                        "Lax": uc.cdp.network.CookieSameSite.LAX,
                        "None": uc.cdp.network.CookieSameSite.NONE,
                    }
                    ss_val = _ss_map.get(cookie["sameSite"])
                    if ss_val is not None:
                        params["same_site"] = ss_val
                if cookie.get("expires"):
                    params["expires"] = uc.cdp.network.TimeSinceEpoch(
                        float(cookie["expires"])
                    )

                await page.send(
                    uc.cdp.network.set_cookie(**params)
                )
            except Exception:
                self._log.debug(
                    "Failed to set cookie '%s' via CDP",
                    cookie.get("name", "?"),
                    exc_info=True,
                )

        self._log.info(
            "Applied %d cookies to browser via CDP", len(cookies)
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Save cookies and close the browser session."""
        try:
            await self.save_cookies()
        except Exception:
            self._log.exception("Error saving cookies during close")

        if self.browser is not None:
            try:
                await self.browser.close()
            except Exception:
                self._log.exception("Error closing browser")
            self.browser = None

        self.is_logged_in = False
        self._log.info("Session '%s' closed", self.name)


# ======================================================================
# PersistentSession
# ======================================================================


class PersistentSession(BaseSession):
    """Always-on browser session.

    Used for Rakuten RMS where CAPTCHA/2FA complexity requires keeping
    the browser running between jobs. The KeepAlive service browses
    pages periodically to prevent session timeout.
    """

    @abc.abstractmethod
    async def keepalive(self) -> bool:
        """Navigate to a safe page and back to maintain the session.

        Returns ``False`` if the session has expired (triggers re-login).
        """

    async def ensure_logged_in(self) -> None:
        """Check session health and re-login if necessary.

        For persistent sessions the browser is already running; this
        method verifies the session is alive and re-authenticates if
        needed.
        """
        if self.browser is not None:
            if await self.is_alive():
                self.last_activity = datetime.now(timezone.utc)
                return

            self._log.info(
                "Persistent session expired, re-logging in"
            )
        else:
            self._log.info(
                "Persistent session has no browser, starting fresh"
            )

        success = await self.login()
        if success:
            self.is_logged_in = True
            self.last_activity = datetime.now(timezone.utc)
        else:
            self.is_logged_in = False
            raise RuntimeError(
                f"Persistent login failed for session '{self.name}'"
            )


# ======================================================================
# OnDemandSession
# ======================================================================


class OnDemandSession(BaseSession):
    """Ephemeral browser session launched per-job.

    Used for Yamato B2 Cloud and Sagawa e飛伝III to save RAM. The
    browser is started via :meth:`acquire_browser`, the job runs, and
    :meth:`release_browser` kills the process.

    Cookies are persisted to disk between invocations, enabling session
    continuity without a permanent browser.
    """

    async def acquire_browser(self) -> None:
        """Launch a browser, inject persisted cookies, and verify session.

        Lifecycle:
        1. Load cookies + user-agent from disk.
        2. Launch Chrome with the synced user-agent.
        3. Inject cookies via CDP.
        4. Navigate to verify session validity.
        5. If invalid, attempt credential-based login.
        """
        from ..browser.session import BrowserSession

        # Load persisted state
        cookies, stored_ua = self.cookie_store.load()
        ua = stored_ua or self.user_agent

        # Launch browser
        session_id = f"{self.name}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        self.browser = BrowserSession(
            session_name=self.name,
            session_id=session_id,
            user_agent=ua,
        )
        await self.browser.start()
        self._log.info("On-demand browser acquired for '%s'", self.name)

        # Inject cookies if we have them
        if cookies:
            if ua:
                self.user_agent = ua
            await self._apply_cookies_to_browser()
            self._log.info(
                "Injected %d persisted cookies", len(cookies)
            )

            # Navigate to verify
            try:
                await self.browser.navigate(self.login_url)
                await asyncio.sleep(random.uniform(2.0, 4.0))
                if await self.is_alive():
                    self.is_logged_in = True
                    self.last_activity = datetime.now(timezone.utc)
                    self._log.info("Session restored from cookies")
                    return
            except Exception:
                self._log.debug("Cookie-based session verification failed")

        # Cookies expired or missing -- full login
        self._log.info("Cookies invalid/missing, attempting full login")
        self.is_logged_in = False

    async def release_browser(self) -> None:
        """Save cookies, close/kill the browser, and free RAM.

        After calling this method, :attr:`browser` is ``None``.
        """
        if self.browser is None:
            return

        try:
            await self.save_cookies()
        except Exception:
            self._log.exception("Error saving cookies during release")

        try:
            await self.browser.close()
        except Exception:
            self._log.exception("Error closing browser during release")

        self.browser = None
        self.is_logged_in = False
        self._log.info("On-demand browser released for '%s'", self.name)

    async def ensure_logged_in(self) -> None:
        """Acquire a browser and ensure an authenticated session.

        Calls :meth:`acquire_browser` internally. If the session could
        not be restored from cookies, calls :meth:`login`.
        """
        await self.acquire_browser()

        if self.is_logged_in:
            return

        success = await self.login()
        if success:
            self.is_logged_in = True
            self.last_activity = datetime.now(timezone.utc)
        else:
            self.is_logged_in = False
            raise RuntimeError(
                f"On-demand login failed for session '{self.name}'"
            )
