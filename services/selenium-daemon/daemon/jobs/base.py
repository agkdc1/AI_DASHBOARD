"""Base job class with status tracking and serialization.

Jobs represent units of work submitted to the daemon via the FastAPI API.
Each job has a type, optional carrier association, priority level, and
lifecycle state that transitions through the ``JobStatus`` enum.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any


class JobStatus(str, enum.Enum):
    """Lifecycle states for a daemon job.

    Transitions::

        queued -> running -> completed
                          -> failed
                          -> cancelled  (from queued only)
        running -> pending_user_login   (automated login failed)
        pending_user_login -> queued    (after cookie injection)
    """

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PENDING_USER_LOGIN = "pending_user_login"


class JobType(str, enum.Enum):
    """Supported job types.

    - ``PRINT_WAYBILL``: Download a shipping waybill PDF from a carrier portal.
    - ``RENEW_KEYS``: Renew Rakuten RMS API keys and propagate to Vault/InvenTree.
    """

    PRINT_WAYBILL = "print_waybill"
    RENEW_KEYS = "renew_keys"


class Job:
    """A single unit of work tracked by the daemon.

    Args:
        job_type: The kind of work to perform.
        carrier: Carrier session name (``"yamato"``, ``"sagawa"``, ``"rakuten"``,
                 or ``None`` for jobs that infer their session).
        priority: Lower number = higher priority.  Typical values:
                  1 = renew_keys (urgent), 5 = print_waybill, 9 = keepalive.
        params: Arbitrary parameters specific to the job type (e.g. recipient
                address for waybill jobs).
    """

    def __init__(
        self,
        job_type: JobType,
        carrier: str | None,
        priority: int,
        params: dict[str, Any],
    ) -> None:
        self.job_id: str = f"j-{uuid.uuid4().hex[:8]}"
        self.job_type: JobType = job_type
        self.carrier: str | None = carrier  # "yamato", "sagawa", "rakuten", or None
        self.priority: int = priority
        self.params: dict[str, Any] = params
        self.status: JobStatus = JobStatus.QUEUED
        self.result: dict[str, Any] | None = None
        self.error: str | None = None
        self.created_at: datetime = datetime.now(timezone.utc)
        self.completed_at: datetime | None = None

    # ------------------------------------------------------------------
    # Session routing
    # ------------------------------------------------------------------

    def session_name(self) -> str:
        """Determine which browser session this job requires.

        ``RENEW_KEYS`` always targets the Rakuten session.
        ``PRINT_WAYBILL`` uses the explicit carrier, defaulting to ``"yamato"``.
        """
        if self.job_type == JobType.RENEW_KEYS:
            return "rakuten"
        return self.carrier or "yamato"

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def complete(self, result: dict[str, Any]) -> None:
        """Mark the job as successfully completed with *result* data."""
        self.status = JobStatus.COMPLETED
        self.result = result
        self.completed_at = datetime.now(timezone.utc)

    def fail(self, error: str) -> None:
        """Mark the job as failed with an error message."""
        self.status = JobStatus.FAILED
        self.error = error
        self.completed_at = datetime.now(timezone.utc)

    def set_pending_user_login(self) -> None:
        """Park the job waiting for human cookie injection.

        This state is entered when automated login fails after the
        configured number of retries (CAPTCHA unsolvable, 2FA timeout,
        unexpected page layout).
        """
        self.status = JobStatus.PENDING_USER_LOGIN

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "job_id": self.job_id,
            "type": self.job_type.value,
            "carrier": self.carrier,
            "status": self.status.value,
            "priority": self.priority,
            "params": self.params,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Job:
        """Reconstruct a Job from a serialized dictionary.

        Used when reloading pending jobs from ``state.json`` on startup.
        """
        job = cls(
            job_type=JobType(data["type"]),
            carrier=data.get("carrier"),
            priority=data.get("priority", 5),
            params=data.get("params", {}),
        )
        job.job_id = data["job_id"]
        job.status = JobStatus(data.get("status", "queued"))
        job.result = data.get("result")
        job.error = data.get("error")
        if data.get("created_at"):
            job.created_at = datetime.fromisoformat(data["created_at"])
        if data.get("completed_at"):
            job.completed_at = datetime.fromisoformat(data["completed_at"])
        return job

    def __repr__(self) -> str:
        return (
            f"<Job {self.job_id} type={self.job_type.value} "
            f"carrier={self.carrier} status={self.status.value}>"
        )
