"""FastAPI application with lifespan for the SHINBEE Browser Daemon.

Startup initializes the secret client (GCP SM), browser sessions, the
job queue, background services (keep-alive, memory guardian, scheduler),
and the job worker loop.  Shutdown persists pending jobs, stops
background tasks, and closes all browser sessions gracefully.

Usage::

    uvicorn daemon.main:app --host 127.0.0.1 --port 8020
"""

from __future__ import annotations

import asyncio
import logging
import logging.handlers
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI

from .api import router
from .config import cfg, log_dir, state_file, cookie_dir, pdf_dir
from .jobs.base import Job, JobStatus, JobType
from .jobs import print_waybill, renew_keys
from .queue import JobQueue
from .secret_client import SecretClient

log = logging.getLogger("daemon")

# ======================================================================
# Logging setup
# ======================================================================

def _setup_logging() -> None:
    """Configure structured JSONL logging to file and stderr."""
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Console handler (human-readable)
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.INFO)
    console_fmt = logging.Formatter(
        "%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console.setFormatter(console_fmt)
    root.addHandler(console)

    # JSONL file handler (structured, machine-readable)
    try:
        logs = log_dir()
        logs.mkdir(parents=True, exist_ok=True)
        jsonl_path = logs / "daemon.jsonl"
        file_handler = logging.handlers.RotatingFileHandler(
            jsonl_path,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)

        # Structured JSON-line format
        jsonl_fmt = logging.Formatter(
            '{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
        file_handler.setFormatter(jsonl_fmt)
        root.addHandler(file_handler)
    except Exception:
        log.warning("Could not set up JSONL file logging", exc_info=True)


# ======================================================================
# Credential pre-check
# ======================================================================

_EXPECTED_CREDENTIALS: dict[str, list[str]] = {
    "daemon/yamato": ["login_id", "password"],
    "daemon/sagawa": ["user_id", "password"],
}


def _check_credentials(secrets: SecretClient) -> None:
    """Read carrier credentials and warn if missing or incomplete.

    Advisory only — does not raise or prevent startup.
    """
    for path, expected_keys in _EXPECTED_CREDENTIALS.items():
        try:
            data = secrets.read(path)
        except Exception:
            log.warning("Secret '%s' could not be read -- credentials missing", path)
            continue

        missing = [k for k in expected_keys if not data.get(k)]
        if missing:
            log.warning(
                "Secret '%s' is incomplete -- missing keys: %s",
                path, ", ".join(missing),
            )
        else:
            log.info("Secret '%s' OK (%d keys)", path, len(expected_keys))


# ======================================================================
# Session factory
# ======================================================================

def _create_sessions(secrets: SecretClient) -> dict[str, object]:
    """Instantiate browser sessions based on config.yaml.

    Creates:
    - Rakuten: persistent session (always-on browser with keep-alive)
    - Yamato: on-demand session (ephemeral browser per job)
    - Sagawa: on-demand session (ephemeral browser per job)

    Sessions that are disabled in config are skipped.
    """
    sessions: dict[str, object] = {}

    session_configs = cfg("daemon.sessions")

    for name, session_cfg in session_configs.items():
        if not session_cfg.get("enabled", True):
            log.info("Session '%s' is disabled -- skipping", name)
            continue

        mode = session_cfg.get("mode", "on_demand")
        log.info("Creating session '%s' (mode=%s)", name, mode)

        try:
            if name == "rakuten":
                from .sessions.rakuten import RakutenSession
                sessions[name] = RakutenSession(vault_client=secrets)
            elif name == "yamato":
                from .sessions.yamato import YamatoSession
                sessions[name] = YamatoSession(vault_client=secrets)
            elif name == "sagawa":
                from .sessions.sagawa import SagawaSession
                sessions[name] = SagawaSession(vault_client=secrets)
            else:
                log.warning("Unknown session name '%s' -- skipping", name)
                continue

        except ImportError:
            log.warning(
                "Session module for '%s' not yet implemented -- skipping",
                name,
            )
        except Exception:
            log.exception("Failed to create session '%s'", name)

    return sessions


# ======================================================================
# Background tasks
# ======================================================================

async def _start_keepalive(
    sessions: dict[str, object],
    queue: JobQueue,
) -> list[asyncio.Task]:
    """Start keep-alive background tasks for all persistent sessions.

    Iterates all sessions and creates a keepalive task for any that
    have a ``keepalive()`` method.  Each session gets its own interval
    from ``daemon.sessions.{name}.keepalive_{min,max}_secs``.

    The keepalive acquires the per-session lock before navigating,
    preventing races with the job worker that uses the same browser.

    Returns the list of created asyncio tasks (may be empty).
    """
    tasks: list[asyncio.Task] = []

    for name, session in sessions.items():
        if not hasattr(session, "keepalive"):
            continue

        # Capture variables for closure
        _name = name
        _session = session

        async def _keepalive_loop(
            sess_name: str = _name,
            sess: object = _session,
        ) -> None:
            import random

            try:
                min_secs = cfg(f"daemon.sessions.{sess_name}.keepalive_min_secs")
                max_secs = cfg(f"daemon.sessions.{sess_name}.keepalive_max_secs")
            except (KeyError, TypeError):
                min_secs, max_secs = 300, 600

            log.info(
                "Keep-alive started for '%s' (interval=%d-%ds)",
                sess_name, min_secs, max_secs,
            )

            while True:
                delay = random.uniform(min_secs, max_secs)
                await asyncio.sleep(delay)

                # Acquire per-session lock to prevent racing with job worker
                lock = queue.get_session_lock(sess_name)
                async with lock:
                    try:
                        success = await sess.keepalive()  # type: ignore[union-attr]
                        if not success:
                            log.warning(
                                "Keep-alive detected expired %s session -- attempting re-login",
                                sess_name,
                            )
                            await sess.login()  # type: ignore[union-attr]
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        log.exception("Keep-alive iteration failed for '%s'", sess_name)

        task = asyncio.create_task(
            _keepalive_loop(), name=f"keepalive-{name}",
        )
        tasks.append(task)

    return tasks


async def _start_memory_guardian(sessions: dict[str, object]) -> asyncio.Task | None:
    """Start the memory guardian background task.

    Monitors daemon RSS and the Rakuten persistent Chrome process.
    """
    try:
        limit_mb = cfg("daemon.memory.limit_mb")
        warning_mb = cfg("daemon.memory.warning_mb")
        check_interval = cfg("daemon.memory.check_interval_secs")
    except (KeyError, TypeError):
        limit_mb, warning_mb, check_interval = 2500, 2000, 30

    import psutil

    async def _guardian_loop() -> None:
        log.info(
            "Memory guardian started (warning=%dMB, limit=%dMB, interval=%ds)",
            warning_mb, limit_mb, check_interval,
        )

        while True:
            await asyncio.sleep(check_interval)

            try:
                process = psutil.Process()
                rss_mb = process.memory_info().rss / (1024 * 1024)

                if rss_mb > limit_mb:
                    log.critical(
                        "MEMORY LIMIT EXCEEDED: %.1fMB > %dMB -- restarting Rakuten browser",
                        rss_mb, limit_mb,
                    )
                    rakuten = sessions.get("rakuten")
                    if rakuten and hasattr(rakuten, "close"):
                        await rakuten.close()  # type: ignore[union-attr]

                elif rss_mb > warning_mb:
                    log.warning("Memory warning: %.1fMB > %dMB", rss_mb, warning_mb)

            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Memory guardian check failed")

    task = asyncio.create_task(_guardian_loop(), name="memory_guardian")
    return task


async def _start_scheduler(
    sessions: dict[str, object],
    queue: JobQueue,
    secrets: SecretClient,
) -> asyncio.Task | None:
    """Start the periodic scheduler.

    Handles:
    - Rakuten API key renewal reminders (based on ``renewed_at`` in GCP SM)
    - On-demand session cookie refresh (Yamato/Sagawa every 3h)
    - Job queue pruning (remove old completed jobs)
    """
    async def _scheduler_loop() -> None:
        log.info("Scheduler started")

        while True:
            await asyncio.sleep(3600)  # check every hour

            try:
                # Prune old completed jobs
                queue.prune_completed(max_age_secs=86400)

                # On-demand cookie refresh for Yamato/Sagawa
                for name, session in sessions.items():
                    if hasattr(session, "refresh_cookies"):
                        try:
                            log.info("Scheduler: refreshing cookies for '%s'", name)
                            await session.refresh_cookies()  # type: ignore[union-attr]
                        except Exception:
                            log.exception("Cookie refresh failed for '%s'", name)

                # Rakuten API key renewal is now manual (services/ai-assistant/rakuten/).
                # The daemon no longer auto-schedules renewal jobs.

            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Scheduler iteration failed")

    task = asyncio.create_task(_scheduler_loop(), name="scheduler")
    return task


# ======================================================================
# Job worker loop
# ======================================================================

async def _job_worker(
    queue: JobQueue,
    sessions: dict[str, object],
    secrets: SecretClient,
) -> None:
    """Main job processing loop.

    Continuously dequeues jobs, acquires the appropriate session lock,
    and dispatches to the correct executor.  Runs until cancelled.
    """
    log.info("Job worker started")

    while True:
        try:
            job = await queue.get_next()
            if job is None:
                continue  # timeout, loop again

            session_name = job.session_name()
            session = sessions.get(session_name)

            if session is None:
                log.error(
                    "No session '%s' for job %s -- failing",
                    session_name, job.job_id,
                )
                job.fail(f"Session '{session_name}' not available")
                continue

            # Acquire per-session lock (one job at a time per browser)
            lock = queue.get_session_lock(session_name)

            async with lock:
                log.info(
                    "Executing job %s (type=%s, session=%s)",
                    job.job_id, job.job_type.value, session_name,
                )

                if job.job_type == JobType.PRINT_WAYBILL:
                    await print_waybill.execute(job, session)  # type: ignore[arg-type]

                elif job.job_type == JobType.RENEW_KEYS:
                    await renew_keys.execute(job, session, secrets)  # type: ignore[arg-type]

                else:
                    job.fail(f"Unknown job type: {job.job_type.value}")

                log.info(
                    "Job %s finished: status=%s",
                    job.job_id, job.status.value,
                )

        except asyncio.CancelledError:
            log.info("Job worker cancelled -- stopping")
            raise
        except Exception:
            log.exception("Unexpected error in job worker loop")
            await asyncio.sleep(1.0)  # back-off before retrying


# ======================================================================
# FastAPI lifespan
# ======================================================================

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager for startup and shutdown.

    Startup:
      1. Configure logging.
      2. Create SecretClient (GCP Secret Manager).
      3. Create browser sessions (Rakuten persistent, Yamato/Sagawa on-demand).
      4. Create JobQueue and load pending jobs from ``state.json``.
      5. Ensure output directories exist.
      6. Start background tasks (keep-alive, memory guardian, scheduler).
      7. Start the job worker loop.

    Shutdown:
      1. Cancel all background tasks.
      2. Save pending jobs to ``state.json``.
      3. Close all browser sessions (saves cookies).
    """
    # --- Startup ---

    _setup_logging()
    log.info("SHINBEE Browser Daemon starting up")

    # Record start time for uptime calculation
    app.state.start_time = time.time()

    # Secret client (GCP Secret Manager)
    secrets = SecretClient()
    app.state.secrets = secrets
    log.info("SecretClient initialized")

    # Pre-check carrier credentials (advisory)
    _check_credentials(secrets)

    # Sessions
    sessions = _create_sessions(secrets)
    app.state.sessions = sessions
    log.info("Created %d session(s): %s", len(sessions), list(sessions.keys()))

    # Job queue
    queue = JobQueue()
    app.state.job_queue = queue

    # Load pending jobs from state file
    _state_file = state_file()
    if _state_file.exists():
        reloaded = queue.load_state(_state_file)
        log.info("Reloaded %d pending job(s) from %s", reloaded, _state_file)

    # Ensure output directories
    try:
        for carrier in ("yamato", "sagawa"):
            (pdf_dir() / carrier).mkdir(parents=True, exist_ok=True)
        cookie_dir().mkdir(parents=True, exist_ok=True)
        log.dir = log_dir()  # type: ignore[attr-defined]
    except Exception:
        log.warning("Could not create output directories", exc_info=True)

    # Start persistent sessions (Rakuten)
    for name, session in sessions.items():
        if hasattr(session, "start"):
            try:
                log.info("Starting persistent session '%s'", name)
                await asyncio.wait_for(
                    session.start(),  # type: ignore[union-attr]
                    timeout=120,
                )
            except asyncio.TimeoutError:
                log.warning("Session '%s' start timed out after 120s -- continuing", name)
            except Exception:
                log.exception("Failed to start session '%s'", name)

    # Background tasks
    background_tasks: list[asyncio.Task] = []

    keepalive_tasks = await _start_keepalive(sessions, queue)
    background_tasks.extend(keepalive_tasks)

    guardian_task = await _start_memory_guardian(sessions)
    if guardian_task:
        background_tasks.append(guardian_task)

    scheduler_task = await _start_scheduler(sessions, queue, secrets)
    if scheduler_task:
        background_tasks.append(scheduler_task)

    # Job worker
    worker_task = asyncio.create_task(
        _job_worker(queue, sessions, secrets),
        name="job_worker",
    )
    background_tasks.append(worker_task)

    log.info(
        "Startup complete -- %d background task(s) running",
        len(background_tasks),
    )

    yield  # --- Application is running ---

    # --- Shutdown ---
    log.info("SHINBEE Browser Daemon shutting down")

    # Cancel background tasks
    for task in background_tasks:
        task.cancel()

    # Wait for tasks to finish
    if background_tasks:
        results = await asyncio.gather(*background_tasks, return_exceptions=True)
        for task, result in zip(background_tasks, results):
            if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
                log.error("Task '%s' raised during shutdown: %s", task.get_name(), result)

    # Save pending jobs
    queue.save_state(_state_file)

    # Close all sessions (saves cookies, kills browsers)
    for name, session in sessions.items():
        try:
            log.info("Closing session '%s'", name)
            await session.close()  # type: ignore[union-attr]
        except Exception:
            log.exception("Error closing session '%s'", name)

    log.info("Shutdown complete")


# ======================================================================
# Application
# ======================================================================

app = FastAPI(
    title="SHINBEE Browser Daemon",
    description=(
        "Central browser automation hub for Rakuten RMS, Yamato B2 Cloud, "
        "and Sagawa e飛伝III. Handles waybill PDF generation and Rakuten "
        "API key renewal."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router)
