"""Async priority job queue with per-session locking.

Implements the job queue described in FULLPLAN.md section 2.4.  Jobs are
dispatched to browser sessions one at a time using per-session asyncio
locks to prevent concurrent use of a single browser instance.

Priority levels (lower = higher priority):

- 1 -- ``renew_keys`` (time-critical)
- 5 -- ``print_waybill`` (normal)
- 9 -- keepalive (auto-generated, lowest)

Pending jobs (``QUEUED`` and ``PENDING_USER_LOGIN``) are persisted to
``state.json`` on shutdown and reloaded on startup.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from .jobs.base import Job, JobStatus, JobType

log = logging.getLogger(__name__)


class JobQueue:
    """Async priority queue with per-session locking and state persistence.

    The queue uses ``asyncio.PriorityQueue`` internally with a monotonic
    counter as a tiebreaker to preserve FIFO order within the same
    priority level.
    """

    def __init__(self) -> None:
        self._queue: asyncio.PriorityQueue[tuple[int, int, str]] = asyncio.PriorityQueue()
        self._jobs: dict[str, Job] = {}  # job_id -> Job
        self._session_locks: dict[str, asyncio.Lock] = {}  # session_name -> Lock
        self._counter: int = 0  # monotonic tiebreaker

    # ------------------------------------------------------------------
    # Job submission
    # ------------------------------------------------------------------

    def submit(self, job: Job) -> str:
        """Add a job to the queue.

        Returns:
            The assigned ``job_id``.
        """
        self._jobs[job.job_id] = job
        self._counter += 1
        self._queue.put_nowait((job.priority, self._counter, job.job_id))
        log.info(
            "Job submitted: %s (type=%s, carrier=%s, priority=%d)",
            job.job_id, job.job_type.value, job.carrier, job.priority,
        )
        return job.job_id

    # ------------------------------------------------------------------
    # Job lookup
    # ------------------------------------------------------------------

    def get_job(self, job_id: str) -> Job | None:
        """Look up a job by ID. Returns ``None`` if not found."""
        return self._jobs.get(job_id)

    # ------------------------------------------------------------------
    # Cancellation
    # ------------------------------------------------------------------

    def cancel(self, job_id: str) -> bool:
        """Cancel a queued job.

        Only jobs in the ``QUEUED`` state can be cancelled.  Jobs that
        are already running or completed are unaffected.

        Returns:
            ``True`` if the job was cancelled.
        """
        job = self._jobs.get(job_id)
        if job and job.status == JobStatus.QUEUED:
            job.status = JobStatus.CANCELLED
            log.info("Job cancelled: %s", job_id)
            return True
        return False

    # ------------------------------------------------------------------
    # Per-session locking
    # ------------------------------------------------------------------

    def get_session_lock(self, session_name: str) -> asyncio.Lock:
        """Get (or create) the asyncio lock for a browser session.

        Each browser session can execute at most one job at a time.
        The lock is also held during keep-alive browsing for persistent
        sessions.
        """
        if session_name not in self._session_locks:
            self._session_locks[session_name] = asyncio.Lock()
        return self._session_locks[session_name]

    # ------------------------------------------------------------------
    # Queue consumption
    # ------------------------------------------------------------------

    async def get_next(self) -> Job | None:
        """Get the next non-cancelled job from the queue.

        Blocks for up to 1 second waiting for a job.  Returns ``None``
        if the queue is empty after the timeout (allowing the worker
        loop to check for shutdown signals).

        Cancelled or already-processed jobs are silently skipped.
        """
        while True:
            try:
                priority, counter, job_id = await asyncio.wait_for(
                    self._queue.get(), timeout=1.0,
                )
            except asyncio.TimeoutError:
                return None

            job = self._jobs.get(job_id)
            if job is not None and job.status == JobStatus.QUEUED:
                return job
            # Skip cancelled / already-processed jobs and try again

    # ------------------------------------------------------------------
    # PENDING_USER_LOGIN management
    # ------------------------------------------------------------------

    def requeue_pending_user_login(self, session_name: str) -> int:
        """Move all ``PENDING_USER_LOGIN`` jobs for a session back to ``QUEUED``.

        Called after successful cookie injection: the human has logged in
        manually and injected fresh cookies, so parked jobs can now be
        retried.

        Returns:
            Number of jobs requeued.
        """
        count = 0
        for job in self._jobs.values():
            if (
                job.status == JobStatus.PENDING_USER_LOGIN
                and job.session_name() == session_name
            ):
                job.status = JobStatus.QUEUED
                self._counter += 1
                self._queue.put_nowait((job.priority, self._counter, job.job_id))
                count += 1
                log.info(
                    "Requeued PENDING_USER_LOGIN job %s for session '%s'",
                    job.job_id, session_name,
                )

        if count:
            log.info(
                "Requeued %d PENDING_USER_LOGIN job(s) for session '%s'",
                count, session_name,
            )
        return count

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def pending_jobs(self) -> list[Job]:
        """Return all jobs in ``QUEUED`` or ``PENDING_USER_LOGIN`` state."""
        return [
            j for j in self._jobs.values()
            if j.status in (JobStatus.QUEUED, JobStatus.PENDING_USER_LOGIN)
        ]

    def all_jobs(self) -> list[Job]:
        """Return all tracked jobs (for API listing)."""
        return list(self._jobs.values())

    @property
    def depth(self) -> int:
        """Number of items currently in the priority queue (approximate)."""
        return self._queue.qsize()

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def save_state(self, path: str | Path) -> None:
        """Save pending jobs to disk for crash recovery.

        Only ``QUEUED`` and ``PENDING_USER_LOGIN`` jobs are saved; all
        others are transient.  Called on daemon shutdown.
        """
        path = Path(path)
        pending = [
            j.to_dict()
            for j in self._jobs.values()
            if j.status in (JobStatus.QUEUED, JobStatus.PENDING_USER_LOGIN)
        ]

        try:
            tmp = path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"pending_jobs": pending}, f, indent=2, ensure_ascii=False)
            tmp.replace(path)
            log.info("Saved %d pending job(s) to %s", len(pending), path)
        except Exception:
            log.exception("Failed to save job queue state to %s", path)
            if tmp.exists():
                tmp.unlink(missing_ok=True)

    def load_state(self, path: str | Path) -> int:
        """Reload pending jobs from disk.

        Reconstructs ``Job`` objects from the saved JSON and re-submits
        them to the queue.  Called on daemon startup.

        Returns:
            Number of jobs reloaded.
        """
        path = Path(path)
        if not path.exists():
            log.debug("No state file at %s -- starting with empty queue", path)
            return 0

        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            log.exception("Failed to load state from %s", path)
            return 0

        jobs_data = data.get("pending_jobs", [])
        count = 0

        for job_data in jobs_data:
            try:
                job = Job.from_dict(job_data)
                # Reset PENDING_USER_LOGIN jobs to QUEUED on restart
                # (the human may have injected cookies while daemon was down)
                if job.status == JobStatus.PENDING_USER_LOGIN:
                    job.status = JobStatus.QUEUED

                # Ensure the job is in QUEUED state for re-submission
                if job.status == JobStatus.QUEUED:
                    self._jobs[job.job_id] = job
                    self._counter += 1
                    self._queue.put_nowait((job.priority, self._counter, job.job_id))
                    count += 1
                    log.info(
                        "Reloaded job %s (type=%s, carrier=%s)",
                        job.job_id, job.job_type.value, job.carrier,
                    )
            except (KeyError, ValueError) as exc:
                log.warning("Skipping malformed job entry: %s", exc)

        log.info("Reloaded %d job(s) from %s", count, path)
        return count

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def prune_completed(self, max_age_secs: int = 86400) -> int:
        """Remove completed/failed/cancelled jobs older than *max_age_secs*.

        Prevents unbounded growth of the ``_jobs`` dict.

        Returns:
            Number of jobs pruned.
        """
        from datetime import datetime, timezone

        cutoff = datetime.now(timezone.utc).timestamp() - max_age_secs
        to_remove: list[str] = []

        for job_id, job in self._jobs.items():
            if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
                completed_ts = (
                    job.completed_at.timestamp()
                    if job.completed_at
                    else job.created_at.timestamp()
                )
                if completed_ts < cutoff:
                    to_remove.append(job_id)

        for job_id in to_remove:
            del self._jobs[job_id]

        if to_remove:
            log.info("Pruned %d old jobs from tracking dict", len(to_remove))

        return len(to_remove)
