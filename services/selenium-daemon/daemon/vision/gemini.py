"""Generalized Gemini client for vision and text tasks.

Extracted from rakuten_renewal/agent/captcha_solver.py. Provides a generic
``call_gemini`` function that can be used by any module (CAPTCHA solver,
page analyzer, XPath repair, meta-optimizer, etc.).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from PIL import Image

from ..config import prompts_dir

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Generation config presets
# ---------------------------------------------------------------------------

STRUCTURED_CONFIG: dict[str, Any] = {
    "response_mime_type": "application/json",
    "temperature": 0.2,
    "top_p": 0.8,
    "max_output_tokens": 4096,
}
"""Default generation config for structured JSON tasks (page analysis, etc.)."""

CAPTCHA_CONFIG: dict[str, Any] = {
    "response_mime_type": "application/json",
    "temperature": 0.4,
    "top_p": 0.9,
    "max_output_tokens": 8192,
}
"""Generation config for CAPTCHA solving (higher temperature, more tokens)."""

# ---------------------------------------------------------------------------
# Internal state
# ---------------------------------------------------------------------------

_api_configured = False
_api_available = False
_genai = None  # lazy import of google.generativeai


def _ensure_api() -> None:
    """Configure the Gemini API key if not already done.

    Only reads from ``GOOGLE_API_KEY`` environment variable.
    If no API key is found, Gemini calls are disabled (raises RuntimeError).
    WIF X.509 ambient credentials do NOT work with the Gemini genai SDK
    (causes infinite gRPC retry loop with OAuthError).
    """
    global _api_configured, _api_available, _genai
    if _api_configured:
        if not _api_available:
            raise RuntimeError("Gemini API key not available")
        return

    _api_configured = True

    api_key = os.environ.get("GOOGLE_API_KEY")
    if api_key:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        _genai = genai
        _api_available = True
        log.info("Gemini API configured via API key")
    else:
        _api_available = False
        log.warning(
            "No Gemini API key found; Gemini features disabled. "
            "Set GOOGLE_API_KEY env var to enable."
        )


def _load_prompt(name: str) -> str:
    """Load a prompt file from the prompts directory.

    Args:
        name: File name relative to the prompts directory (e.g. ``"page_state.txt"``).

    Returns:
        The full text content of the prompt file.

    Raises:
        FileNotFoundError: If the prompt file does not exist.
    """
    path = prompts_dir() / name
    return path.read_text()


def _load_image(path: Path) -> Image.Image:
    """Open an image file as a PIL Image.

    Args:
        path: Path to the image file.

    Returns:
        The opened PIL Image (kept in memory for Gemini upload).
    """
    return Image.open(path)


def call_gemini(
    model_name: str,
    system_prompt: str,
    images: list[Path],
    user_text: str = "",
    generation_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Call a Gemini model with structured JSON output.

    Constructs a multi-part content list from a system prompt, zero or more
    images, and optional user text, then sends it to the specified model.

    Args:
        model_name: Gemini model identifier (e.g. ``"gemini-2.0-flash"``).
        system_prompt: The system/instruction prompt text.
        images: Ordered list of image file paths to include in the request.
        user_text: Optional additional user-supplied text appended after images.
        generation_config: Gemini generation config dict. Defaults to
                          ``STRUCTURED_CONFIG`` if not provided.

    Returns:
        Parsed JSON dict from the model's response.

    Raises:
        json.JSONDecodeError: If the model response is not valid JSON.
        RuntimeError: If Gemini API key is not available.
    """
    _ensure_api()  # raises RuntimeError if no API key
    model = _genai.GenerativeModel(model_name)
    gen_cfg = generation_config or STRUCTURED_CONFIG

    content: list[Any] = [system_prompt]
    for img_path in images:
        content.append(_load_image(img_path))
    if user_text:
        content.append(user_text)

    response = model.generate_content(content, generation_config=gen_cfg)
    parsed: dict[str, Any] = json.loads(response.text)
    return parsed
