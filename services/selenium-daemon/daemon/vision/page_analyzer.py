"""General page state classification wrapper.

Thin wrapper around :func:`captcha.analyze_page` that provides convenience
helpers for common page-state queries (login detection, CAPTCHA detection,
interactive element listing).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .captcha import analyze_page

log = logging.getLogger(__name__)


def classify_page(screenshot_path: Path) -> dict[str, Any]:
    """Classify the current browser page by analyzing a screenshot.

    Delegates to :func:`captcha.analyze_page` which sends the screenshot
    to Gemini and returns a structured JSON classification.

    Args:
        screenshot_path: Absolute path to a PNG screenshot of the page.

    Returns:
        Parsed classification dict with keys such as:

        - ``page_type`` (str) -- e.g. ``"login"``, ``"dashboard"``, ``"captcha"``,
          ``"form"``, ``"error"``, ``"unknown"``
        - ``has_captcha`` (bool) -- whether a CAPTCHA challenge is visible
        - ``interactive_elements`` (list[dict]) -- clickable/typable elements
        - ``confidence`` (float) -- model confidence in the classification
        - ``summary`` (str) -- human-readable page description
    """
    result = analyze_page(screenshot_path)
    log.debug(
        "Page classified: type=%s, captcha=%s, elements=%d",
        result.get("page_type", "unknown"),
        result.get("has_captcha", False),
        len(result.get("interactive_elements", [])),
    )
    return result


def detect_login_page(page_state: dict[str, Any]) -> bool:
    """Check whether the classified page state indicates a login page.

    Args:
        page_state: Classification dict returned by :func:`classify_page`.

    Returns:
        ``True`` if the page appears to be a login/sign-in page.
    """
    page_type = page_state.get("page_type", "").lower()
    return page_type in ("login", "sign_in", "signin", "login_page")


def detect_captcha(page_state: dict[str, Any]) -> bool:
    """Check whether the classified page state indicates a CAPTCHA challenge.

    Args:
        page_state: Classification dict returned by :func:`classify_page`.

    Returns:
        ``True`` if a CAPTCHA is detected on the page.
    """
    return bool(page_state.get("has_captcha", False))


def get_interactive_elements(page_state: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract the list of interactive elements from a page classification.

    Args:
        page_state: Classification dict returned by :func:`classify_page`.

    Returns:
        List of element dicts, each typically containing:

        - ``type`` (str) -- ``"button"``, ``"input"``, ``"link"``, etc.
        - ``label`` (str) -- visible text or aria-label
        - ``x`` (int), ``y`` (int) -- approximate center coordinates
        - ``selector`` (str) -- suggested CSS selector (if available)
    """
    elements: list[dict[str, Any]] = page_state.get("interactive_elements", [])
    return elements
