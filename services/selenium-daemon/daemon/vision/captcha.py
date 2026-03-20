"""CAPTCHA-specific vision functions.

Extracted from rakuten_renewal/agent/captcha_solver.py. All functions use
the generic ``call_gemini`` from ``.gemini`` and read configuration from
``..config``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..config import cfg, gemini_model, captcha_model
from .gemini import call_gemini, _load_prompt, CAPTCHA_CONFIG, STRUCTURED_CONFIG

log = logging.getLogger(__name__)


def analyze_page(screenshot: Path) -> dict[str, Any]:
    """Classify the current page state (Prompt 1 -- page_state.txt).

    Sends a screenshot to Gemini and receives a structured classification
    including page type, presence of CAPTCHA, interactive elements, etc.

    Args:
        screenshot: Path to a PNG screenshot of the current browser page.

    Returns:
        Parsed JSON dict with keys like ``page_type``, ``has_captcha``,
        ``interactive_elements``, etc.
    """
    prompt = _load_prompt("page_state.txt")
    result = call_gemini(
        model_name=gemini_model(),
        system_prompt=prompt,
        images=[screenshot],
        generation_config=STRUCTURED_CONFIG,
    )
    log.info(
        "Page state: %s (captcha=%s)",
        result.get("page_type"),
        result.get("has_captcha"),
    )
    return result


def solve_captcha(
    screenshot: Path,
    prompt_version: int = 1,
) -> dict[str, Any]:
    """Solve a CAPTCHA from a screenshot (Prompt 2 -- captcha_v{N}.txt).

    Uses the higher-capability ``captcha_model`` and the CAPTCHA-specific
    generation config for more creative reasoning.

    Args:
        screenshot: Path to a PNG screenshot showing the CAPTCHA challenge.
        prompt_version: Version number of the captcha prompt file (default 1).
                       The meta-optimizer may increment this over time.

    Returns:
        Parsed JSON dict with ``challenge``, ``confidence``, ``actions``, etc.
    """
    prompt_file = f"captcha_v{prompt_version}.txt"
    prompt = _load_prompt(prompt_file)
    result = call_gemini(
        model_name=captcha_model(),
        system_prompt=prompt,
        images=[screenshot],
        generation_config=CAPTCHA_CONFIG,
    )
    log.info(
        "CAPTCHA solved: type=%s confidence=%.2f actions=%d",
        result.get("challenge", {}).get("type"),
        result.get("confidence", 0),
        len(result.get("actions", [])),
    )
    return result


def verify_action(before: Path, after: Path) -> dict[str, Any]:
    """Verify if a browser action succeeded (Prompt 3 -- verify_action.txt).

    Compares before and after screenshots to determine whether the intended
    action (e.g. clicking a button, solving a CAPTCHA) was successful.

    Args:
        before: Path to screenshot taken before the action.
        after: Path to screenshot taken after the action.

    Returns:
        Parsed JSON dict with ``action_succeeded``, ``summary``, etc.
    """
    prompt = _load_prompt("verify_action.txt")
    result = call_gemini(
        model_name=gemini_model(),
        system_prompt=prompt,
        images=[before, after],
        generation_config=STRUCTURED_CONFIG,
    )
    log.info(
        "Action verify: succeeded=%s, summary=%s",
        result.get("action_succeeded"),
        result.get("summary"),
    )
    return result


def extract_keys(screenshot: Path) -> dict[str, Any]:
    """Extract API keys from a result page (Prompt 4 -- extract_keys.txt).

    Args:
        screenshot: Path to a PNG screenshot of the API key result page.

    Returns:
        Parsed JSON dict with ``keys_found``, ``confidence``, and key values.
    """
    prompt = _load_prompt("extract_keys.txt")
    result = call_gemini(
        model_name=gemini_model(),
        system_prompt=prompt,
        images=[screenshot],
        generation_config=STRUCTURED_CONFIG,
    )
    log.info(
        "Key extraction: found=%s confidence=%.2f",
        result.get("keys_found"),
        result.get("confidence", 0),
    )
    return result


def schedule_next_recon(
    session_summary: str,
    stats: dict[str, Any],
) -> dict[str, Any]:
    """Ask Gemini for the next recon interval (Prompt 5 -- schedule_next.txt).

    The model analyzes recent session history and statistics to recommend
    an optimal recon interval, clamped to configured min/max bounds.

    Args:
        session_summary: Human-readable summary of the last 10 recon runs.
        stats: Aggregate statistics dict with keys like ``total_recon_sessions``,
               ``total_captcha_attempts``, ``success_rate``, etc.

    Returns:
        Parsed JSON dict with ``next_interval_days``, ``preferred_hour_utc``, etc.
    """
    prompt_template = _load_prompt("schedule_next.txt")
    r_cfg = cfg("daemon.recon")
    prompt = (
        prompt_template
        .replace("{{min_days}}", str(r_cfg["interval_min_days"]))
        .replace("{{max_days}}", str(r_cfg["interval_max_days"]))
    )

    user_msg = (
        f"Session history (last 10 recon runs):\n"
        f"{session_summary}\n"
        f"\n"
        f"Aggregate stats:\n"
        f"- Total recon sessions: {stats.get('total_recon_sessions', 0)}\n"
        f"- Total CAPTCHA attempts: {stats.get('total_captcha_attempts', 0)}\n"
        f"- Total CAPTCHA successes: {stats.get('total_captcha_successes', 0)}\n"
        f"- Success rate: {stats.get('success_rate', 0):.0%}\n"
        f"- Last interval used: {stats.get('last_interval', 7)} days\n"
        f"- Days until next real renewal deadline: "
        f"{stats.get('days_until_renewal', 80)}\n"
        f"\n"
        f"Config constraints:\n"
        f"- min_days: {r_cfg['interval_min_days']}\n"
        f"- max_days: {r_cfg['interval_max_days']}"
    )

    result = call_gemini(
        model_name=gemini_model(),
        system_prompt=prompt,
        images=[],
        user_text=user_msg,
        generation_config=STRUCTURED_CONFIG,
    )

    # Clamp interval to config bounds
    interval = result.get("next_interval_days", 7)
    interval = max(
        r_cfg["interval_min_days"],
        min(r_cfg["interval_max_days"], interval),
    )
    result["next_interval_days"] = interval

    log.info(
        "Next recon in %d days (hour=%s)",
        interval,
        result.get("preferred_hour_utc"),
    )
    return result


def run_meta_optimizer(
    sessions_data: str,
    current_prompt: str,
    stats: dict[str, Any],
) -> dict[str, Any]:
    """Run the meta-optimizer to rewrite the CAPTCHA prompt (Module D).

    Analyzes recent session logs and the current CAPTCHA prompt to suggest
    an improved version.

    Args:
        sessions_data: Concatenated session logs from the last 5 runs.
        current_prompt: The current CAPTCHA system prompt text.
        stats: Aggregate statistics with ``success_rate``, ``per_type_breakdown``,
               ``failure_modes``, etc.

    Returns:
        Parsed JSON dict with ``new_prompt``, ``confidence``, ``changes``, etc.
    """
    meta_prompt = _load_prompt("meta_prompt.txt")

    user_msg = (
        f"Session logs from the last 5 runs:\n"
        f"{sessions_data}\n"
        f"\n"
        f"Aggregate stats:\n"
        f"- Overall success rate: {stats.get('success_rate', 0):.0%}\n"
        f"- Per-type breakdown:\n"
        f"{stats.get('per_type_breakdown', '  (no data yet)')}\n"
        f"\n"
        f"Common failure modes:\n"
        f"{stats.get('failure_modes', '  (none identified)')}\n"
        f"\n"
        f"Current system prompt:\n"
        f"{current_prompt}"
    )

    result = call_gemini(
        model_name=gemini_model(),
        system_prompt=meta_prompt,
        images=[],
        user_text=user_msg,
        generation_config=STRUCTURED_CONFIG,
    )
    log.info("Meta-optimizer: confidence=%.2f", result.get("confidence", 0))
    return result
