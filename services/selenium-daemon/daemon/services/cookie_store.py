"""Disk-persisted cookie jar per session.

Each session (rakuten, yamato, sagawa) stores its browser cookies and
user-agent string in a JSON file on disk.  This enables on-demand sessions
to restore authenticated state without re-logging in, and allows the
Chrome Extension human-fallback flow to persist injected cookies.

JSON format::

    {
        "cookies": [
            {
                "name": "sid",
                "value": "abc123",
                "domain": ".example.co.jp",
                "path": "/",
                "secure": true,
                "httpOnly": true,
                "sameSite": "Lax",
                "expires": 1735689600
            }
        ],
        "user_agent": "Mozilla/5.0 ...",
        "saved_at": "2026-02-17T12:00:00+00:00"
    }
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Keys preserved per cookie dict
_COOKIE_FIELDS = (
    "name",
    "value",
    "domain",
    "path",
    "secure",
    "httpOnly",
    "sameSite",
    "expires",
)


class CookieStore:
    """Disk-persisted cookie jar for a single browser session.

    Parameters:
        session_name: Identifier used in the filename, e.g. ``"rakuten"``.
        cookie_dir:   Directory that holds the JSON cookie files.
    """

    def __init__(self, session_name: str, cookie_dir: Path) -> None:
        self.session_name = session_name
        self._cookie_dir = cookie_dir
        self._cookie_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def cookie_file(self) -> Path:
        """Absolute path to the cookie JSON file for this session."""
        return self._cookie_dir / f"{self.session_name}.json"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save(
        self,
        cookies: list[dict[str, Any]],
        user_agent: str | None = None,
    ) -> None:
        """Persist *cookies* and optional *user_agent* to disk.

        Each cookie dict is normalised to contain only the canonical fields.
        Unknown keys are silently dropped.
        """
        normalised: list[dict[str, Any]] = []
        for raw in cookies:
            entry: dict[str, Any] = {}
            for key in _COOKIE_FIELDS:
                if key in raw:
                    entry[key] = raw[key]
            # name + value are mandatory
            if "name" in entry and "value" in entry:
                normalised.append(entry)

        payload = {
            "cookies": normalised,
            "user_agent": user_agent,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }

        tmp = self.cookie_file.with_suffix(".tmp")
        try:
            tmp.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.replace(self.cookie_file)
            log.info(
                "Saved %d cookies for session '%s' (ua=%s)",
                len(normalised),
                self.session_name,
                "yes" if user_agent else "no",
            )
        except Exception:
            log.exception("Failed to save cookies for '%s'", self.session_name)
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            raise

    def load(self) -> tuple[list[dict[str, Any]], str | None]:
        """Load cookies and user-agent from disk.

        Returns:
            A tuple of ``(cookies_list, user_agent_string)``.
            If the cookie file is missing or corrupt, returns ``([], None)``.
        """
        if not self.cookie_file.exists():
            log.debug("No cookie file for '%s'", self.session_name)
            return [], None

        try:
            data = json.loads(self.cookie_file.read_text(encoding="utf-8"))
            cookies = data.get("cookies", [])
            user_agent = data.get("user_agent")
            log.info(
                "Loaded %d cookies for session '%s' (saved_at=%s)",
                len(cookies),
                self.session_name,
                data.get("saved_at", "unknown"),
            )
            return cookies, user_agent
        except (json.JSONDecodeError, KeyError, TypeError):
            log.exception(
                "Corrupt cookie file for '%s', returning empty",
                self.session_name,
            )
            return [], None

    def clear(self) -> None:
        """Delete the cookie file from disk."""
        if self.cookie_file.exists():
            self.cookie_file.unlink()
            log.info("Cleared cookies for session '%s'", self.session_name)
        else:
            log.debug(
                "No cookie file to clear for '%s'", self.session_name
            )
