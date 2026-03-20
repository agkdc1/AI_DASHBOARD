"""Rakuten RMS API Key Renewal Agent — main orchestrator.

Usage:
    python -m agent.main --mode recon    # Dry-run: login + CAPTCHA, no renewal
    python -m agent.main --mode renew    # Full: login + CAPTCHA + key renewal
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import config as cfg
from .browser import BrowserSession
from .captcha_solver import (
    analyze_page,
    extract_keys,
    run_meta_optimizer,
    schedule_next_recon,
    solve_captcha,
    verify_action,
)
from .firestore_poll import poll_2fa_code
from .gcs_sync import download_recent_sessions, upload_session
from .logger import SessionLogger
from .notifier import send_fallback_email
from .vault_client import VaultClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# --- State management ---------------------------------------------------------

def load_state() -> dict[str, Any]:
    sf = cfg.state_file()
    if sf.exists():
        return json.loads(sf.read_text())
    return {
        "last_renewal_at": None,
        "last_recon_at": None,
        "next_recon_at": None,
        "next_recon_interval_days": 7,
        "next_recon_suggested_by": "default",
        "total_recon_sessions": 0,
        "total_renewal_sessions": 0,
        "total_captcha_attempts": 0,
        "total_captcha_successes": 0,
    }


def save_state(state: dict[str, Any]) -> None:
    sf = cfg.state_file()
    sf.parent.mkdir(parents=True, exist_ok=True)
    sf.write_text(json.dumps(state, indent=2, ensure_ascii=False))


# --- Retry strategy -----------------------------------------------------------

def get_retry_delay(attempt: int) -> int:
    """Return delay in seconds based on attempt number (escalating strategy)."""
    if attempt <= 5:
        return cfg.cfg("rakuten.retry_delay_secs")
    elif attempt <= 15:
        return 60
    elif attempt <= 30:
        return 300
    else:
        return 900


# --- Prompt versioning --------------------------------------------------------

def current_prompt_version() -> int:
    """Find the highest captcha_vN.txt version number."""
    prompts = cfg.prompts_dir()
    versions = []
    for f in prompts.glob("captcha_v*.txt"):
        try:
            v = int(f.stem.split("_v")[1])
            versions.append(v)
        except (IndexError, ValueError):
            continue
    return max(versions) if versions else 1


# --- Core workflow ------------------------------------------------------------

async def shared_steps(
    browser: BrowserSession,
    vault: VaultClient,
    logger: SessionLogger,
) -> dict[str, Any] | None:
    """Steps 1-7: Login, handle 2FA, navigate to key page, solve CAPTCHAs.

    Returns the page_state dict when successfully on the API key management page,
    or None if an unrecoverable error occurred.
    """
    # 1. Fetch credentials
    creds = vault.read("rakuten/rms")
    logger.event("vault_read", path="secret/rakuten/rms", ok=True)

    # 2. Launch browser
    await browser.start()
    logger.event("browser_launch", headless=cfg.cfg("rakuten.browser.headless"))

    # 3. Navigate to RMS login
    rms_url = cfg.cfg("rakuten.rms_url")
    await browser.navigate(rms_url)
    logger.event("navigate", url=rms_url)

    # Page state loop — keep analyzing until we reach the key page or fail
    max_page_transitions = 20
    prompt_version = current_prompt_version()

    for _ in range(max_page_transitions):
        ss = await browser.screenshot("page_state")
        page_state = analyze_page(ss)
        page_type = page_state.get("page_type", "unknown")
        logger.event("page_state", page_type=page_type, has_captcha=page_state.get("has_captcha"))

        if page_type == "login_form":
            # Find input fields and type credentials
            elements = page_state.get("interactive_elements", [])
            id_field = next((e for e in elements if e["type"] == "text_input" and "id" in e["label"].lower()), None)
            pw_field = next((e for e in elements if e["type"] == "text_input" and "pass" in e["label"].lower()), None)
            login_btn = next((e for e in elements if e["type"] == "button" and "login" in e["label"].lower()), None)

            if id_field:
                bbox = id_field["bbox"]
                cx, cy = bbox["x"] + bbox["w"] // 2, bbox["y"] + bbox["h"] // 2
                await browser.move_mouse(cx, cy)
                await browser.click(cx, cy)
                await asyncio.sleep(random.uniform(0.3, 0.8))
                await browser.type_text(creds["login_id"])
                await asyncio.sleep(random.uniform(0.5, 1.5))

            if pw_field:
                bbox = pw_field["bbox"]
                cx, cy = bbox["x"] + bbox["w"] // 2, bbox["y"] + bbox["h"] // 2
                await browser.move_mouse(cx, cy)
                await browser.click(cx, cy)
                await asyncio.sleep(random.uniform(0.3, 0.8))
                await browser.type_text(creds["password"])
                await asyncio.sleep(random.uniform(0.5, 1.0))

            if login_btn:
                bbox = login_btn["bbox"]
                cx, cy = bbox["x"] + bbox["w"] // 2, bbox["y"] + bbox["h"] // 2
                await browser.move_mouse(cx, cy)
                await asyncio.sleep(random.uniform(0.3, 0.7))
                await browser.click(cx, cy)
                await asyncio.sleep(random.uniform(2.0, 4.0))

            logger.event("login_attempt")

        elif page_type == "2fa_prompt":
            logger.event("2fa_detected", screenshot=str(ss))
            code = await poll_2fa_code()
            if code is None:
                logger.event("2fa_timeout")
                return None
            logger.event("firestore_poll", found=True, code=code[:1] + "*****",
                         wait_secs=0)

            # Type 2FA code
            elements = page_state.get("interactive_elements", [])
            code_field = next((e for e in elements if e["type"] == "text_input"), None)
            submit_btn = next((e for e in elements if e["type"] == "button"), None)

            if code_field:
                bbox = code_field["bbox"]
                cx, cy = bbox["x"] + bbox["w"] // 2, bbox["y"] + bbox["h"] // 2
                await browser.move_mouse(cx, cy)
                await browser.click(cx, cy)
                await asyncio.sleep(random.uniform(0.3, 0.6))
                await browser.type_text(code)
                await asyncio.sleep(random.uniform(0.5, 1.0))

            if submit_btn:
                bbox = submit_btn["bbox"]
                cx, cy = bbox["x"] + bbox["w"] // 2, bbox["y"] + bbox["h"] // 2
                await browser.move_mouse(cx, cy)
                await asyncio.sleep(random.uniform(0.2, 0.5))
                await browser.click(cx, cy)
                await asyncio.sleep(random.uniform(2.0, 4.0))

        elif page_type == "captcha_challenge" or page_state.get("has_captcha"):
            logger.event("captcha_detected", screenshot=str(ss))
            solution = solve_captcha(ss, prompt_version=prompt_version)
            logger.event(
                "gemini_call",
                prompt=f"captcha_v{prompt_version}",
                model=cfg.captcha_model(),
                screenshot=str(ss),
                response={
                    "confidence": solution.get("confidence"),
                    "challenge_type": solution.get("challenge", {}).get("type"),
                    "actions_count": len(solution.get("actions", [])),
                },
            )

            before_ss = ss
            actions = solution.get("actions", [])
            if actions:
                await browser.execute_actions(actions)

            await asyncio.sleep(random.uniform(1.0, 2.0))
            after_ss = await browser.screenshot("post_captcha")
            verification = verify_action(before_ss, after_ss)
            success = verification.get("action_succeeded", False)
            logger.event("captcha_result", success=success,
                         challenge_type=solution.get("challenge", {}).get("type"))

            if not success:
                log.warning("CAPTCHA solve failed: %s", verification.get("summary"))
                # Will retry on next loop iteration

        elif page_type == "dashboard":
            # Navigate to API key page
            api_key_url = cfg.cfg("rakuten.api_key_page")
            await browser.navigate(api_key_url)
            logger.event("navigate", url=api_key_url)
            await asyncio.sleep(random.uniform(2.0, 4.0))

        elif page_type in ("api_key_management", "api_key_confirm", "api_key_result"):
            return page_state

        elif page_type == "error_page":
            logger.event("error_page", error=page_state.get("error_text"))
            return None

        else:
            log.warning("Unknown page type: %s", page_type)
            # Try navigating to API key page directly
            api_key_url = cfg.cfg("rakuten.api_key_page")
            await browser.navigate(api_key_url)
            await asyncio.sleep(random.uniform(2.0, 4.0))

    log.error("Exceeded max page transitions")
    return None


async def recon_mode(
    browser: BrowserSession,
    vault: VaultClient,
    logger: SessionLogger,
    state: dict[str, Any],
) -> bool:
    """Recon: reach key page, screenshot, log out, schedule next."""
    page_state = await shared_steps(browser, vault, logger)
    if page_state is None:
        return False

    # R1. Screenshot the key management page
    ss = await browser.screenshot("api_key_page")
    analyze_page(ss)
    logger.event("mode_fork", mode="recon", action="stop_before_renewal")

    # R2. Close browser (acts as logout)
    await browser.close()

    # R3. Log session
    # (handled by caller)

    # R4. Upload to GCS
    # (handled by caller)

    # R5. Schedule next recon
    stats = {
        "total_recon_sessions": state.get("total_recon_sessions", 0),
        "total_captcha_attempts": state.get("total_captcha_attempts", 0),
        "total_captcha_successes": state.get("total_captcha_successes", 0),
        "success_rate": (
            state.get("total_captcha_successes", 0) / max(1, state.get("total_captcha_attempts", 1))
        ),
        "last_interval": state.get("next_recon_interval_days", 7),
        "days_until_renewal": _days_until_renewal(state),
    }

    try:
        schedule = schedule_next_recon(
            session_summary="(see GCS logs)",
            stats=stats,
        )
        next_days = schedule["next_interval_days"]
        next_hour = schedule.get("preferred_hour_utc", random.randint(0, 23))
    except Exception:
        log.exception("Gemini scheduling failed, using random interval")
        next_days = random.randint(
            cfg.cfg("rakuten.recon.interval_min_days"),
            cfg.cfg("rakuten.recon.interval_max_days"),
        )
        next_hour = random.randint(0, 23)
        schedule = {"next_interval_days": next_days, "reasoning": "fallback_random"}

    now = datetime.now(timezone.utc)
    next_recon = (now + timedelta(days=next_days)).replace(hour=next_hour, minute=0, second=0)

    state["last_recon_at"] = now.isoformat()
    state["next_recon_at"] = next_recon.isoformat()
    state["next_recon_interval_days"] = next_days
    state["next_recon_suggested_by"] = cfg.gemini_model()
    state["total_recon_sessions"] = state.get("total_recon_sessions", 0) + 1

    logger.event("schedule_next",
                 next_interval_days=next_days,
                 next_recon_at=next_recon.isoformat(),
                 suggested_by=cfg.gemini_model())

    return True


async def renew_mode(
    browser: BrowserSession,
    vault: VaultClient,
    logger: SessionLogger,
    state: dict[str, Any],
) -> bool:
    """Renewal: reach key page, click renew, extract keys, store in Vault."""
    page_state = await shared_steps(browser, vault, logger)
    if page_state is None:
        return False

    logger.event("mode_fork", mode="renew", action="proceed_to_renewal")
    prompt_version = current_prompt_version()

    # 8. Click Renew button
    elements = page_state.get("interactive_elements", [])
    renew_btn = next(
        (e for e in elements
         if e["type"] == "button" and any(kw in e["label"].lower() for kw in ("renew", "regenerate", "reissue", "再発行"))),
        None,
    )

    if renew_btn:
        bbox = renew_btn["bbox"]
        cx, cy = bbox["x"] + bbox["w"] // 2, bbox["y"] + bbox["h"] // 2
        before_ss = await browser.screenshot("before_renew")
        await browser.move_mouse(cx, cy)
        await asyncio.sleep(random.uniform(0.3, 0.7))
        await browser.click(cx, cy)
        await asyncio.sleep(random.uniform(2.0, 4.0))

        # Handle confirmation dialog
        confirm_ss = await browser.screenshot("confirm_dialog")
        confirm_state = analyze_page(confirm_ss)

        if confirm_state.get("page_type") == "api_key_confirm":
            confirm_elements = confirm_state.get("interactive_elements", [])
            confirm_btn = next(
                (e for e in confirm_elements
                 if e["type"] == "button" and any(kw in e["label"].lower() for kw in ("confirm", "ok", "yes", "確認"))),
                None,
            )
            if confirm_btn:
                bbox = confirm_btn["bbox"]
                cx, cy = bbox["x"] + bbox["w"] // 2, bbox["y"] + bbox["h"] // 2
                await browser.move_mouse(cx, cy)
                await asyncio.sleep(random.uniform(0.3, 0.5))
                await browser.click(cx, cy)
                await asyncio.sleep(random.uniform(3.0, 5.0))
    else:
        log.error("Could not find renew button on page")
        return False

    # 9. Extract new API keys
    result_ss = await browser.screenshot("key_result")
    key_data = extract_keys(result_ss)
    logger.event("gemini_call", prompt="extract_keys", model=cfg.gemini_model(),
                 screenshot=str(result_ss),
                 response={"keys_found": key_data.get("keys_found"), "confidence": key_data.get("confidence")})

    if not key_data.get("keys_found"):
        log.error("No keys found on result page")
        return False

    creds = key_data.get("credentials", {})
    logger.event("key_extracted", fields=list(creds.keys()))

    # 10. Store in Vault
    now_iso = datetime.now(timezone.utc).isoformat()
    vault.write("rakuten/api_keys", {
        "service_secret": creds.get("service_secret", ""),
        "license_key": creds.get("license_key", ""),
        "renewed_at": now_iso,
    })
    logger.event("vault_write", path="secret/rakuten/api_keys", ok=True)

    state["last_renewal_at"] = now_iso
    state["total_renewal_sessions"] = state.get("total_renewal_sessions", 0) + 1

    await browser.close()
    return True


def _days_until_renewal(state: dict[str, Any]) -> int:
    last = state.get("last_renewal_at")
    if not last:
        return 80
    last_dt = datetime.fromisoformat(last)
    deadline = last_dt + timedelta(days=cfg.cfg("rakuten.renewal.deadline_days"))
    remaining = (deadline - datetime.now(timezone.utc)).days
    return max(0, remaining)


# --- Meta-optimizer -----------------------------------------------------------

def maybe_run_meta_optimizer(state: dict[str, Any]) -> bool:
    """Run Module D if we've hit the session threshold."""
    total = state.get("total_recon_sessions", 0) + state.get("total_renewal_sessions", 0)
    if total == 0 or total % 5 != 0:
        return False

    log.info("Running meta-optimizer (total sessions: %d)", total)

    try:
        session_dirs = download_recent_sessions(n=5)
    except Exception:
        log.exception("Failed to download sessions from GCS for meta-optimizer")
        return False

    if not session_dirs:
        log.warning("No sessions found in GCS for meta-optimizer")
        return False

    # Aggregate session data
    sessions_text = ""
    for sd in session_dirs:
        jsonl = sd / "session.jsonl"
        if jsonl.exists():
            sessions_text += f"\n--- Session: {sd.name} ---\n"
            sessions_text += jsonl.read_text()

    # Stats
    total_attempts = state.get("total_captcha_attempts", 0)
    total_successes = state.get("total_captcha_successes", 0)
    success_rate = total_successes / max(1, total_attempts)

    # Current prompt
    version = current_prompt_version()
    current_prompt = (cfg.prompts_dir() / f"captcha_v{version}.txt").read_text()

    result = run_meta_optimizer(
        sessions_data=sessions_text[:8000],  # Limit to avoid token overflow
        current_prompt=current_prompt,
        stats={
            "success_rate": success_rate,
            "per_type_breakdown": "  (aggregated from logs)",
            "failure_modes": "  (extracted from logs)",
        },
    )

    confidence = result.get("confidence", 0)
    if confidence < 0.7:
        log.warning("Meta-optimizer confidence too low (%.2f), skipping prompt update", confidence)
        return False

    new_prompt = result.get("new_prompt", "")
    if not new_prompt:
        log.warning("Meta-optimizer returned empty prompt")
        return False

    # Save new version
    new_version = version + 1
    new_path = cfg.prompts_dir() / f"captcha_v{new_version}.txt"
    new_path.write_text(new_prompt)

    # Log to history
    history_path = cfg.prompts_dir() / "history.jsonl"
    entry = {
        "version": new_version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "success_rate_before": success_rate,
        "changes_summary": result.get("changes_summary", ""),
        "confidence": confidence,
    }
    with open(history_path, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    log.info("Prompt updated: v%d -> v%d (confidence=%.2f)", version, new_version, confidence)
    return True


# --- Cleanup ------------------------------------------------------------------

def cleanup_local(session_id: str) -> None:
    """Prune old local logs/screenshots to save disk space."""
    max_sessions = cfg.cfg("rakuten.logging.local_retention_sessions")
    max_ss = cfg.cfg("rakuten.logging.local_screenshot_retention")

    # Prune logs
    log_dir = cfg.log_dir()
    if log_dir.is_dir():
        logs = sorted(log_dir.glob("*.jsonl"))
        if len(logs) > max_sessions:
            for old in logs[:-max_sessions]:
                old.unlink()
                log.debug("Pruned old log: %s", old.name)

    # Prune screenshots
    ss_dir = cfg.screenshots_dir()
    if ss_dir.is_dir():
        dirs = sorted(d for d in ss_dir.iterdir() if d.is_dir())
        if len(dirs) > max_ss:
            import shutil
            for old in dirs[:-max_ss]:
                shutil.rmtree(old)
                log.debug("Pruned old screenshots: %s", old.name)


# --- Main entry point ---------------------------------------------------------

async def run(mode: str) -> int:
    """Run the agent in the specified mode. Returns exit code."""
    now = datetime.now(timezone.utc)
    session_id = f"{now.strftime('%Y-%m-%dT%H%M%SZ')}_{mode}"

    logger = SessionLogger(session_id=session_id, mode=mode, log_dir=cfg.log_dir())
    vault = VaultClient()
    state = load_state()
    max_retries = cfg.cfg("rakuten.max_retries")
    start_time = time.monotonic()
    success = False
    prompt_updated = False

    for attempt in range(1, max_retries + 1):
        logger.session_start(attempt=attempt)
        browser = BrowserSession(session_id=session_id)

        try:
            if mode == "recon":
                success = await recon_mode(browser, vault, logger, state)
            elif mode == "renew":
                success = await renew_mode(browser, vault, logger, state)
            else:
                log.error("Unknown mode: %s", mode)
                return 1

            if success:
                break

        except Exception:
            log.exception("Attempt %d failed", attempt)
            logger.event("error", attempt=attempt, error=str(sys.exc_info()[1]))
        finally:
            await browser.close()

        if attempt < max_retries:
            delay = get_retry_delay(attempt)
            log.info("Retry in %ds (attempt %d/%d)", delay, attempt, max_retries)
            await asyncio.sleep(delay)

    elapsed_ms = int((time.monotonic() - start_time) * 1000)
    result = "success" if success else "fail"
    logger.session_end(result=result, duration_ms=elapsed_ms)

    # Update CAPTCHA stats
    summary = logger.summary()
    state["total_captcha_attempts"] = (
        state.get("total_captcha_attempts", 0) + summary["captcha_attempts"]
    )
    state["total_captcha_successes"] = (
        state.get("total_captcha_successes", 0) + summary["captcha_successes"]
    )
    save_state(state)

    # Upload to GCS
    try:
        upload_session(
            session_id=session_id,
            mode=mode,
            log_dir=cfg.log_dir(),
            screenshots_dir=cfg.screenshots_dir(),
            state_file=cfg.state_file(),
            metadata=summary,
        )
    except Exception:
        log.exception("GCS upload failed (session data retained locally)")

    # Meta-optimizer
    if success:
        prompt_updated = maybe_run_meta_optimizer(state)
        save_state(state)

    # Local cleanup
    cleanup_local(session_id)

    # Human fallback on total failure (renew mode only)
    if not success and mode == "renew":
        try:
            send_fallback_email(
                vault=vault,
                error_description=f"Failed after {max_retries} attempts",
                session_id=session_id,
            )
        except Exception:
            log.exception("Could not send fallback email")

    log.info("Session %s complete: %s (%dms)", session_id, result, elapsed_ms)
    return 0 if success else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Rakuten RMS API Key Renewal Agent")
    parser.add_argument(
        "--mode",
        required=True,
        choices=["recon", "renew"],
        help="recon = dry-run (no key change), renew = full renewal",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(run(args.mode)))


if __name__ == "__main__":
    main()
