"""Periodic task scheduler for the Browser Daemon.

Handles:
    1. **Rakuten renewal timer** -- triggers key renewal every ``interval_days``.
    2. **Rakuten recon** -- Gemini-scheduled reconnaissance (3-14 days).
    3. **On-demand cookie refresh** -- keeps Yamato/Sagawa sessions fresh
       by periodically launching an ephemeral browser to verify/refresh cookies.
    4. **Meta-optimizer** -- rewrites CAPTCHA prompt every 5 Rakuten sessions.
    5. **GCS log upload** -- archives session logs and screenshots.
    6. **Local cleanup** -- prunes old logs/screenshots/PDFs.
    7. **Fallback email** -- notifies admin on renewal failure via SendGrid.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, TYPE_CHECKING

from .. import config as cfg

if TYPE_CHECKING:
    from ..sessions.base import BaseSession, OnDemandSession
    from ..sessions.rakuten import RakutenSession
    from ..secret_client import SecretClient

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------

def _load_state() -> dict[str, Any]:
    """Load persistent scheduler state from disk."""
    sf = cfg.state_file()
    if sf.exists():
        try:
            return json.loads(sf.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            log.warning("Corrupt state.json, starting fresh")
    return {
        "last_renewal_at": None,
        "last_recon_at": None,
        "next_recon_at": None,
        "next_recon_interval_days": 7,
        "total_recon_sessions": 0,
        "total_renewal_sessions": 0,
        "total_captcha_attempts": 0,
        "total_captcha_successes": 0,
    }


def _save_state(state: dict[str, Any]) -> None:
    """Persist scheduler state to disk."""
    sf = cfg.state_file()
    sf.parent.mkdir(parents=True, exist_ok=True)
    tmp = sf.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(sf)


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------


class Scheduler:
    """Periodic task scheduler for the Browser Daemon.

    Runs in the background alongside the FastAPI server and KeepAlive
    service.  Each task has its own interval and last-run timestamp.

    Args:
        sessions: Dict mapping session name to :class:`BaseSession`.
        secret_client: Authenticated :class:`SecretClient`.
        rakuten_session: The Rakuten :class:`PersistentSession` (or None
                         if Rakuten is disabled).
    """

    def __init__(
        self,
        sessions: dict[str, BaseSession],
        vault_client: SecretClient,
        rakuten_session: RakutenSession | None = None,
    ) -> None:
        self._sessions = sessions
        self._vault = vault_client
        self._rakuten = rakuten_session
        self._running: bool = True
        self._state: dict[str, Any] = _load_state()

        # Track last-run timestamps for periodic tasks
        self._last_cookie_refresh: dict[str, float] = {}
        self._last_cleanup: float = 0.0
        self._last_gcs_upload: float = 0.0

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    def stop(self) -> None:
        """Signal the scheduler to exit."""
        self._running = False
        _save_state(self._state)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Async scheduler loop. Checks tasks every 60 seconds."""
        log.info("Scheduler started")

        while self._running:
            await asyncio.sleep(60)
            if not self._running:
                break

            now = time.monotonic()
            now_utc = datetime.now(timezone.utc)

            try:
                # 1. Rakuten renewal timer
                await self._check_renewal_timer(now_utc)
            except Exception:
                log.exception("Scheduler: renewal timer check failed")

            try:
                # 2. Rakuten recon
                await self._check_recon_timer(now_utc)
            except Exception:
                log.exception("Scheduler: recon timer check failed")

            try:
                # 3. On-demand cookie refresh (Yamato/Sagawa)
                await self._check_cookie_refresh(now)
            except Exception:
                log.exception("Scheduler: cookie refresh check failed")

            try:
                # 4. Meta-optimizer
                await self._check_meta_optimizer()
            except Exception:
                log.exception("Scheduler: meta-optimizer check failed")

            try:
                # 5. Local cleanup (every 6 hours)
                if now - self._last_cleanup > 21600:
                    self._cleanup_local()
                    self._last_cleanup = now
            except Exception:
                log.exception("Scheduler: cleanup failed")

            try:
                # 6. GCS log upload (every 2 hours)
                if now - self._last_gcs_upload > 7200:
                    await self._upload_logs_to_gcs()
                    self._last_gcs_upload = now
            except Exception:
                log.exception("Scheduler: GCS upload failed")

        _save_state(self._state)
        log.info("Scheduler stopped")

    # ------------------------------------------------------------------
    # Rakuten renewal timer
    # ------------------------------------------------------------------

    async def _check_renewal_timer(self, now: datetime) -> None:
        """Check if it is time to trigger a Rakuten API key renewal."""
        if self._rakuten is None:
            return

        try:
            interval_days = cfg.cfg("daemon.renewal.interval_days")
        except Exception:
            interval_days = 80

        last_renewal = self._state.get("last_renewal_at")
        if last_renewal is None:
            # Never renewed -- schedule for now
            log.info("No previous renewal recorded, scheduling renewal")
            # The actual renewal job is submitted via the job queue;
            # we just log the intent here
            return

        last_dt = datetime.fromisoformat(last_renewal)
        next_renewal = last_dt + timedelta(days=interval_days)

        if now >= next_renewal:
            log.info(
                "Renewal timer fired (last=%s, interval=%dd)",
                last_renewal,
                interval_days,
            )
            # TODO: Submit a renew_keys job to the job queue.
            # For now, just log the intent. The job queue integration
            # will be wired in main.py lifespan.

    # ------------------------------------------------------------------
    # Rakuten recon
    # ------------------------------------------------------------------

    async def _check_recon_timer(self, now: datetime) -> None:
        """Check if it is time for a Rakuten reconnaissance session."""
        if self._rakuten is None:
            return

        try:
            recon_enabled = cfg.cfg("daemon.recon.enabled")
        except Exception:
            recon_enabled = True

        if not recon_enabled:
            return

        next_recon = self._state.get("next_recon_at")
        if next_recon is None:
            # Schedule first recon
            try:
                min_days = cfg.cfg("daemon.recon.interval_min_days")
                max_days = cfg.cfg("daemon.recon.interval_max_days")
            except Exception:
                min_days, max_days = 3, 14

            days = random.randint(min_days, max_days)
            next_dt = now + timedelta(days=days)
            self._state["next_recon_at"] = next_dt.isoformat()
            _save_state(self._state)
            log.info("First recon scheduled for %s", next_dt.isoformat())
            return

        next_dt = datetime.fromisoformat(next_recon)
        if now >= next_dt:
            log.info("Recon timer fired (scheduled=%s)", next_recon)
            # TODO: Submit a recon job or execute inline.
            # Schedule next recon using Gemini (or random fallback)
            await self._schedule_next_recon(now)

    async def _schedule_next_recon(self, now: datetime) -> None:
        """Use Gemini to schedule the next recon interval, with fallback."""
        try:
            min_days = cfg.cfg("daemon.recon.interval_min_days")
            max_days = cfg.cfg("daemon.recon.interval_max_days")
        except Exception:
            min_days, max_days = 3, 14

        try:
            from ..vision.captcha import schedule_next_recon

            stats = {
                "total_recon_sessions": self._state.get("total_recon_sessions", 0),
                "total_captcha_attempts": self._state.get("total_captcha_attempts", 0),
                "total_captcha_successes": self._state.get("total_captcha_successes", 0),
                "success_rate": (
                    self._state.get("total_captcha_successes", 0)
                    / max(1, self._state.get("total_captcha_attempts", 1))
                ),
                "last_interval": self._state.get("next_recon_interval_days", 7),
                "days_until_renewal": self._days_until_renewal(),
            }
            schedule = schedule_next_recon(
                session_summary="(see GCS logs)",
                stats=stats,
            )
            days = schedule.get("next_interval_days", 7)
            days = max(min_days, min(max_days, days))
        except Exception:
            log.warning("Gemini scheduling failed, using random interval")
            days = random.randint(min_days, max_days)

        next_dt = now + timedelta(days=days)
        self._state["last_recon_at"] = now.isoformat()
        self._state["next_recon_at"] = next_dt.isoformat()
        self._state["next_recon_interval_days"] = days
        self._state["total_recon_sessions"] = (
            self._state.get("total_recon_sessions", 0) + 1
        )
        _save_state(self._state)
        log.info("Next recon scheduled in %d days (%s)", days, next_dt.isoformat())

    def _days_until_renewal(self) -> int:
        """Calculate days remaining until the renewal deadline."""
        last = self._state.get("last_renewal_at")
        if not last:
            return 80
        try:
            deadline_days = cfg.cfg("daemon.renewal.deadline_days")
        except Exception:
            deadline_days = 88
        last_dt = datetime.fromisoformat(last)
        deadline = last_dt + timedelta(days=deadline_days)
        remaining = (deadline - datetime.now(timezone.utc)).days
        return max(0, remaining)

    # ------------------------------------------------------------------
    # On-demand cookie refresh (Yamato / Sagawa)
    # ------------------------------------------------------------------

    async def _check_cookie_refresh(self, now: float) -> None:
        """Periodically refresh cookies for on-demand sessions.

        Launches an ephemeral browser, loads persisted cookies, navigates
        to verify the session, saves refreshed cookies, and kills the
        browser.
        """
        for name, session in self._sessions.items():
            # Only on-demand sessions need periodic cookie refresh
            try:
                mode = cfg.cfg(f"daemon.sessions.{name}.mode")
            except Exception:
                continue

            if mode != "on_demand":
                continue

            try:
                interval = cfg.cfg(
                    f"daemon.sessions.{name}.cookie_refresh_interval_secs"
                )
            except Exception:
                interval = 10800  # 3 hours

            last_refresh = self._last_cookie_refresh.get(name, 0.0)
            if now - last_refresh < interval:
                continue

            log.info("Cookie refresh for '%s'", name)
            self._last_cookie_refresh[name] = now

            try:
                from ..sessions.base import OnDemandSession

                if not isinstance(session, OnDemandSession):
                    continue

                # Acquire browser, verify session, release
                await session.acquire_browser()

                if session.is_logged_in:
                    log.info("Cookie refresh: '%s' session still valid", name)
                else:
                    log.info(
                        "Cookie refresh: '%s' expired, attempting login", name
                    )
                    success = await session.login()
                    if not success:
                        log.warning(
                            "Cookie refresh: '%s' login failed -- "
                            "session needs human login",
                            name,
                        )

                await session.release_browser()

            except Exception:
                log.exception("Cookie refresh failed for '%s'", name)
                # Ensure browser is released even on error
                try:
                    from ..sessions.base import OnDemandSession
                    if isinstance(session, OnDemandSession):
                        await session.release_browser()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Meta-optimizer
    # ------------------------------------------------------------------

    async def _check_meta_optimizer(self) -> None:
        """Run the meta-optimizer every 5 Rakuten sessions.

        Rewrites the CAPTCHA prompt based on accumulated session data.
        """
        if self._rakuten is None:
            return

        total = (
            self._state.get("total_recon_sessions", 0)
            + self._state.get("total_renewal_sessions", 0)
        )
        if total == 0 or total % 5 != 0:
            return

        # Avoid running twice for the same total
        last_meta_total = self._state.get("_last_meta_optimizer_total", 0)
        if total == last_meta_total:
            return

        log.info("Running meta-optimizer (total sessions: %d)", total)
        self._state["_last_meta_optimizer_total"] = total

        try:
            from ..vision.captcha import run_meta_optimizer

            # Load recent sessions from GCS
            sessions_text = ""
            try:
                from google.cloud import storage
                from google.auth import identity_pool
                import os

                cred_path = os.environ.get(
                    "GOOGLE_APPLICATION_CREDENTIALS",
                    "/app/Vault/pki/wif-credential-config.json",
                )
                creds = identity_pool.Credentials.from_file(cred_path)
                creds = creds.with_scopes(
                    ["https://www.googleapis.com/auth/devstorage.read_write"]
                )
                client = storage.Client(
                    project=cfg.cfg("gcp.project_id"),
                    credentials=creds,
                )
                bucket = client.bucket(cfg.gcs_bucket())
                prefix = f"{cfg.gcs_prefix()}/sessions/"
                blobs = list(bucket.list_blobs(prefix=prefix))

                # Get recent session logs
                jsonl_blobs = [
                    b for b in blobs if b.name.endswith("session.jsonl")
                ]
                for blob in jsonl_blobs[-5:]:
                    sessions_text += f"\n--- {blob.name} ---\n"
                    sessions_text += blob.download_as_text()[:2000]
            except Exception:
                log.debug("GCS download for meta-optimizer failed")

            # Current prompt
            prompt_version = self._current_prompt_version()
            prompt_path = cfg.prompts_dir() / f"captcha_v{prompt_version}.txt"
            current_prompt = prompt_path.read_text() if prompt_path.exists() else ""

            total_attempts = self._state.get("total_captcha_attempts", 0)
            total_successes = self._state.get("total_captcha_successes", 0)
            success_rate = total_successes / max(1, total_attempts)

            result = run_meta_optimizer(
                sessions_data=sessions_text[:8000],
                current_prompt=current_prompt,
                stats={
                    "success_rate": success_rate,
                    "per_type_breakdown": "(aggregated from logs)",
                    "failure_modes": "(extracted from logs)",
                },
            )

            confidence = result.get("confidence", 0)
            if confidence < 0.7:
                log.info(
                    "Meta-optimizer confidence %.2f too low, skipping",
                    confidence,
                )
                return

            new_prompt = result.get("new_prompt", "")
            if not new_prompt:
                log.warning("Meta-optimizer returned empty prompt")
                return

            # Save new version
            new_version = prompt_version + 1
            new_path = cfg.prompts_dir() / f"captcha_v{new_version}.txt"
            new_path.write_text(new_prompt)

            # Append to history
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

            log.info(
                "Prompt updated: v%d -> v%d (confidence=%.2f)",
                prompt_version,
                new_version,
                confidence,
            )

        except Exception:
            log.exception("Meta-optimizer failed")

        _save_state(self._state)

    @staticmethod
    def _current_prompt_version() -> int:
        """Find the highest captcha_vN.txt version number."""
        prompts = cfg.prompts_dir()
        versions: list[int] = []
        for f in prompts.glob("captcha_v*.txt"):
            try:
                v = int(f.stem.split("_v")[1])
                versions.append(v)
            except (IndexError, ValueError):
                continue
        return max(versions) if versions else 1

    # ------------------------------------------------------------------
    # GCS log upload
    # ------------------------------------------------------------------

    async def _upload_logs_to_gcs(self) -> None:
        """Upload recent session logs and screenshots to GCS."""
        try:
            from google.cloud import storage
            from google.auth import identity_pool
            import os

            cred_path = os.environ.get(
                "GOOGLE_APPLICATION_CREDENTIALS",
                "/app/Vault/pki/wif-credential-config.json",
            )
            creds = identity_pool.Credentials.from_file(cred_path)
            creds = creds.with_scopes(
                ["https://www.googleapis.com/auth/devstorage.read_write"]
            )
            client = storage.Client(
                project=cfg.cfg("gcp.project_id"),
                credentials=creds,
            )
            bucket = client.bucket(cfg.gcs_bucket())
            prefix = cfg.gcs_prefix()

            # Upload log files
            log_directory = cfg.log_dir()
            if log_directory.is_dir():
                for logfile in log_directory.glob("*.jsonl"):
                    blob = bucket.blob(f"{prefix}/logs/{logfile.name}")
                    if not blob.exists():
                        blob.upload_from_filename(str(logfile))
                        log.debug("Uploaded log: %s", logfile.name)

            # Upload state file
            sf = cfg.state_file()
            if sf.exists():
                blob = bucket.blob(f"{prefix}/state.json")
                blob.upload_from_filename(str(sf))

            log.info("GCS log upload complete")

        except Exception:
            log.exception("GCS log upload failed")

    # ------------------------------------------------------------------
    # Local cleanup
    # ------------------------------------------------------------------

    def _cleanup_local(self) -> None:
        """Prune old local logs, screenshots, and temporary files."""
        try:
            max_sessions = cfg.cfg("daemon.logging.local_retention_sessions")
            max_ss = cfg.cfg("daemon.logging.local_screenshot_retention")
            max_files = cfg.cfg("daemon.logging.max_files")
        except Exception:
            max_sessions = 10
            max_ss = 3
            max_files = 500

        # Prune old log files
        log_directory = cfg.log_dir()
        if log_directory.is_dir():
            logs = sorted(log_directory.glob("*.jsonl"))
            if len(logs) > max_sessions:
                for old in logs[:-max_sessions]:
                    old.unlink(missing_ok=True)
                    log.debug("Pruned old log: %s", old.name)

        # Prune old screenshot directories
        ss_dir = cfg.screenshots_dir()
        if ss_dir.is_dir():
            dirs = sorted(d for d in ss_dir.iterdir() if d.is_dir())
            if len(dirs) > max_ss:
                for old_dir in dirs[:-max_ss]:
                    shutil.rmtree(old_dir, ignore_errors=True)
                    log.debug("Pruned old screenshots: %s", old_dir.name)

        log.info("Local cleanup complete")

    # ------------------------------------------------------------------
    # Fallback email notification
    # ------------------------------------------------------------------

    async def send_renewal_failure_email(
        self,
        error_description: str,
        session_id: str = "",
    ) -> None:
        """Send admin alert email when Rakuten renewal fails.

        Uses SendGrid via credentials stored in Vault at
        ``secret/rakuten/sendgrid``.
        """
        try:
            from sendgrid import SendGridAPIClient
            from sendgrid.helpers.mail import Mail

            secrets = self._vault.read("rakuten/sendgrid")
            sg = SendGridAPIClient(api_key=secrets["api_key"])

            admin_email = cfg.cfg("daemon.fallback.admin_email")
            sentinel_addr = cfg.cfg("daemon.fallback.sentinel_address")

            body = (
                "The automated Rakuten API key renewal daemon failed.\n\n"
                f"Error: {error_description}\n"
                f"Session: {session_id}\n"
                f"Time: {datetime.now(timezone.utc).isoformat()}\n\n"
                "Please:\n"
                "1. Check daemon logs at /app/logs/\n"
                "2. If login failed, use the Chrome Extension to inject cookies\n"
                f"3. Or reply to {sentinel_addr} with the new API keys\n"
            )

            message = Mail(
                from_email=sentinel_addr,
                to_emails=admin_email,
                subject="[SHINBEE] Rakuten Renewal Failed - Action Required",
                plain_text_content=body,
            )

            response = sg.send(message)
            log.info("Fallback email sent (status %s)", response.status_code)

        except Exception:
            log.exception("Failed to send fallback email")
