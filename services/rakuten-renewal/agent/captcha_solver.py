"""Vision-driven CAPTCHA solver and page analyzer using Gemini."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import google.generativeai as genai
from PIL import Image

from . import config as cfg

log = logging.getLogger(__name__)

# Generation configs
_STRUCTURED_CONFIG = {
    "response_mime_type": "application/json",
    "temperature": 0.2,
    "top_p": 0.8,
    "max_output_tokens": 4096,
}

_CAPTCHA_CONFIG = {
    "response_mime_type": "application/json",
    "temperature": 0.4,
    "top_p": 0.9,
    "max_output_tokens": 8192,
}

_api_configured = False


def _ensure_api() -> None:
    global _api_configured
    if not _api_configured:
        # API key from Vault is set via GOOGLE_API_KEY env var or Vertex AI
        # For now, assume genai is configured via environment
        _api_configured = True


def _load_prompt(name: str) -> str:
    """Load a prompt file from the prompts directory."""
    path = cfg.prompts_dir() / name
    return path.read_text()


def _load_image(path: Path) -> Image.Image:
    return Image.open(path)


def _call_gemini(
    model_name: str,
    system_prompt: str,
    images: list[Path],
    user_text: str = "",
    generation_config: dict | None = None,
) -> dict[str, Any]:
    """Call Gemini with structured JSON output."""
    _ensure_api()
    model = genai.GenerativeModel(model_name)
    gen_cfg = generation_config or _STRUCTURED_CONFIG

    content: list[Any] = [system_prompt]
    for img_path in images:
        content.append(_load_image(img_path))
    if user_text:
        content.append(user_text)

    response = model.generate_content(content, generation_config=gen_cfg)
    parsed = json.loads(response.text)
    return parsed


# --- Public API ---------------------------------------------------------------


def analyze_page(screenshot: Path) -> dict[str, Any]:
    """Classify the current page state (Prompt 1)."""
    prompt = _load_prompt("page_state.txt")
    result = _call_gemini(
        model_name=cfg.gemini_model(),
        system_prompt=prompt,
        images=[screenshot],
    )
    log.info("Page state: %s (captcha=%s)", result.get("page_type"), result.get("has_captcha"))
    return result


def solve_captcha(screenshot: Path, prompt_version: int = 1) -> dict[str, Any]:
    """Solve a CAPTCHA from a screenshot (Prompt 2)."""
    prompt_file = f"captcha_v{prompt_version}.txt"
    prompt = _load_prompt(prompt_file)
    result = _call_gemini(
        model_name=cfg.captcha_model(),
        system_prompt=prompt,
        images=[screenshot],
        generation_config=_CAPTCHA_CONFIG,
    )
    log.info(
        "CAPTCHA solved: type=%s confidence=%.2f actions=%d",
        result.get("challenge", {}).get("type"),
        result.get("confidence", 0),
        len(result.get("actions", [])),
    )
    return result


def verify_action(before: Path, after: Path) -> dict[str, Any]:
    """Verify if a browser action succeeded (Prompt 3)."""
    prompt = _load_prompt("verify_action.txt")
    result = _call_gemini(
        model_name=cfg.gemini_model(),
        system_prompt=prompt,
        images=[before, after],
    )
    log.info("Action verify: succeeded=%s, summary=%s",
             result.get("action_succeeded"), result.get("summary"))
    return result


def extract_keys(screenshot: Path) -> dict[str, Any]:
    """Extract API keys from a result page (Prompt 4)."""
    prompt = _load_prompt("extract_keys.txt")
    result = _call_gemini(
        model_name=cfg.gemini_model(),
        system_prompt=prompt,
        images=[screenshot],
    )
    log.info("Key extraction: found=%s confidence=%.2f",
             result.get("keys_found"), result.get("confidence", 0))
    return result


def schedule_next_recon(
    session_summary: str,
    stats: dict[str, Any],
) -> dict[str, Any]:
    """Ask Gemini for the next recon interval (Prompt 5)."""
    prompt_template = _load_prompt("schedule_next.txt")
    r_cfg = cfg.cfg("rakuten.recon")
    prompt = (
        prompt_template
        .replace("{{min_days}}", str(r_cfg["interval_min_days"]))
        .replace("{{max_days}}", str(r_cfg["interval_max_days"]))
    )

    user_msg = f"""Session history (last 10 recon runs):
{session_summary}

Aggregate stats:
- Total recon sessions: {stats.get('total_recon_sessions', 0)}
- Total CAPTCHA attempts: {stats.get('total_captcha_attempts', 0)}
- Total CAPTCHA successes: {stats.get('total_captcha_successes', 0)}
- Success rate: {stats.get('success_rate', 0):.0%}
- Last interval used: {stats.get('last_interval', 7)} days
- Days until next real renewal deadline: {stats.get('days_until_renewal', 80)}

Config constraints:
- min_days: {r_cfg['interval_min_days']}
- max_days: {r_cfg['interval_max_days']}"""

    result = _call_gemini(
        model_name=cfg.gemini_model(),
        system_prompt=prompt,
        images=[],
        user_text=user_msg,
    )

    # Clamp interval to config bounds
    interval = result.get("next_interval_days", 7)
    interval = max(r_cfg["interval_min_days"], min(r_cfg["interval_max_days"], interval))
    result["next_interval_days"] = interval

    log.info("Next recon in %d days (hour=%s)", interval, result.get("preferred_hour_utc"))
    return result


def run_meta_optimizer(
    sessions_data: str,
    current_prompt: str,
    stats: dict[str, Any],
) -> dict[str, Any]:
    """Run the meta-optimizer to rewrite the CAPTCHA prompt (Module D)."""
    meta_prompt = _load_prompt("meta_prompt.txt")

    user_msg = f"""Session logs from the last 5 runs:
{sessions_data}

Aggregate stats:
- Overall success rate: {stats.get('success_rate', 0):.0%}
- Per-type breakdown:
{stats.get('per_type_breakdown', '  (no data yet)')}

Common failure modes:
{stats.get('failure_modes', '  (none identified)')}

Current system prompt:
{current_prompt}"""

    result = _call_gemini(
        model_name=cfg.gemini_model(),
        system_prompt=meta_prompt,
        images=[],
        user_text=user_msg,
    )
    log.info("Meta-optimizer: confidence=%.2f", result.get("confidence", 0))
    return result
