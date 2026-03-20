"""Adaptive CSS/XPath selector repair via Gemini Flash.

When ``find_element()`` in a session fails for a known selector key, this
module sends the page HTML to Gemini Flash to infer the correct new selector.

See FULLPLAN.md section 2.7 for the full specification.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from ..config import repair_model
from .gemini import call_gemini, _load_prompt, STRUCTURED_CONFIG

log = logging.getLogger(__name__)

# Maximum HTML length to send to Gemini (approximately 30k characters).
_MAX_HTML_LENGTH = 30_000


def _strip_html(raw_html: str) -> str:
    """Reduce HTML to body-only content suitable for Gemini context.

    Processing steps:
    1. Remove ``<script>`` tags and their contents.
    2. Remove ``<style>`` tags and their contents.
    3. Extract only the ``<body>`` content (if present).
    4. Truncate to approximately ``_MAX_HTML_LENGTH`` characters.

    Args:
        raw_html: Full HTML source of the page.

    Returns:
        Cleaned, truncated HTML string.
    """
    # Remove script tags and contents
    html = re.sub(
        r"<script[^>]*>.*?</script>",
        "",
        raw_html,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # Remove style tags and contents
    html = re.sub(
        r"<style[^>]*>.*?</style>",
        "",
        raw_html,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # Extract body content only
    body_match = re.search(
        r"<body[^>]*>(.*)</body>",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if body_match:
        html = body_match.group(1)

    # Collapse excessive whitespace
    html = re.sub(r"\s{2,}", " ", html)

    # Truncate to fit context window
    if len(html) > _MAX_HTML_LENGTH:
        html = html[:_MAX_HTML_LENGTH] + "\n<!-- ... truncated ... -->"

    return html.strip()


def repair_selector(
    session_name: str,
    selector_key: str,
    old_selector: str,
    description: str,
    page_html: str,
    url: str,
) -> str | None:
    """Use Gemini Flash to find a replacement CSS selector for a broken one.

    Loads the ``xpath_repair.txt`` prompt template, substitutes placeholders,
    strips and truncates the HTML, and calls Gemini Flash for a new selector.

    Args:
        session_name: Name of the session (e.g. ``"yamato"``), for logging.
        selector_key: Dotted key in the selectors YAML (e.g. ``"login.username_input"``).
        old_selector: The CSS selector that no longer matches any element.
        description: Human-readable description of the element's purpose.
        page_html: Full HTML source of the current page.
        url: Current page URL (provides context for the model).

    Returns:
        A new CSS selector string if the model is confident enough, or ``None``
        if repair failed or confidence is too low.

        Selection logic:

        - ``confidence >= 0.7`` -- return ``new_selector``
        - ``0.5 <= confidence < 0.7`` -- return ``fallback_selector`` (if provided)
        - ``confidence < 0.5`` -- return ``None``
    """
    # Load and populate the prompt template
    try:
        prompt_template = _load_prompt("xpath_repair.txt")
    except FileNotFoundError:
        log.error(
            "[%s] xpath_repair.txt prompt not found; cannot repair selector",
            session_name,
        )
        return None

    cleaned_html = _strip_html(page_html)

    prompt = (
        prompt_template
        .replace("{{description}}", description)
        .replace("{{old_selector}}", old_selector)
        .replace("{{url}}", url)
        .replace("{{html}}", cleaned_html)
    )

    # Call Gemini Flash (repair model)
    try:
        result = call_gemini(
            model_name=repair_model(),
            system_prompt=prompt,
            images=[],
            user_text="",
            generation_config=STRUCTURED_CONFIG,
        )
    except (json.JSONDecodeError, Exception) as exc:
        log.error(
            "[%s] Gemini repair call failed for '%s': %s",
            session_name, selector_key, exc,
        )
        return None

    # Parse response fields
    new_selector: str | None = result.get("new_selector")
    fallback_selector: str | None = result.get("fallback_selector")
    confidence: float = result.get("confidence", 0.0)
    reasoning: str = result.get("reasoning", "")

    timestamp = datetime.now(timezone.utc).isoformat()

    # Determine which selector to return based on confidence
    chosen: str | None = None
    if confidence >= 0.7 and new_selector:
        chosen = new_selector
        log.info(
            "[%s] Selector repaired: '%s' -> '%s' (confidence=%.2f, key=%s) "
            "at %s. Reasoning: %s",
            session_name,
            old_selector,
            new_selector,
            confidence,
            selector_key,
            timestamp,
            reasoning,
        )
    elif confidence >= 0.5 and fallback_selector:
        chosen = fallback_selector
        log.info(
            "[%s] Selector repaired (fallback): '%s' -> '%s' "
            "(confidence=%.2f, key=%s) at %s. Reasoning: %s",
            session_name,
            old_selector,
            fallback_selector,
            confidence,
            selector_key,
            timestamp,
            reasoning,
        )
    else:
        log.warning(
            "[%s] Selector repair failed: '%s' (key=%s, confidence=%.2f) "
            "at %s. Reasoning: %s",
            session_name,
            old_selector,
            selector_key,
            confidence,
            timestamp,
            reasoning,
        )
        return None

    return chosen
