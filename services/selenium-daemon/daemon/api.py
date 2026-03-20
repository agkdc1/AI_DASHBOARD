"""FastAPI routes for the Browser Daemon.

Implements the endpoints described in FULLPLAN.md section 2.2:

- Job management (submit, status, cancel)
- Session management (list, restart, login, cookie injection)
- Health check

All routes are mounted under an ``APIRouter`` which is included by the
FastAPI app in ``main.py``.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .jobs.base import Job, JobStatus, JobType
from .queue import JobQueue

log = logging.getLogger(__name__)

router = APIRouter()


# ======================================================================
# Pydantic request / response models
# ======================================================================

class JobSubmitRequest(BaseModel):
    """Schema for ``POST /jobs``."""

    type: str = Field(
        ...,
        description="Job type: 'print_waybill' or 'renew_keys'",
        examples=["print_waybill"],
    )
    carrier: str | None = Field(
        default=None,
        description="Carrier session name: 'yamato', 'sagawa', or 'rakuten'",
        examples=["yamato"],
    )
    priority: int = Field(
        default=5,
        ge=1,
        le=9,
        description="Priority (1=highest, 9=lowest). Default: 5",
    )
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Job-specific parameters (e.g. recipient address for waybill jobs)",
    )


class JobSubmitResponse(BaseModel):
    """Response for ``POST /jobs``."""

    job_id: str
    status: str


class JobStatusResponse(BaseModel):
    """Response for ``GET /jobs/{job_id}``."""

    job_id: str
    type: str
    carrier: str | None
    status: str
    priority: int
    params: dict[str, Any]
    result: dict[str, Any] | None
    error: str | None
    created_at: str
    completed_at: str | None


class CancelResponse(BaseModel):
    """Response for ``DELETE /jobs/{job_id}``."""

    job_id: str
    cancelled: bool


class CookieInjectRequest(BaseModel):
    """Schema for ``POST /sessions/{name}/inject-cookies``.

    Payload sent by the Chrome Extension after a human logs in manually.
    """

    cookies: list[dict[str, Any]] = Field(
        ...,
        description="All cookies for the carrier domain",
    )
    user_agent: str = Field(
        ...,
        description="The human's browser User-Agent string",
    )


class CookieInjectResponse(BaseModel):
    """Response for cookie injection."""

    session: str
    cookies_applied: int
    jobs_requeued: int
    session_valid: bool


class SessionInfo(BaseModel):
    """Status of a single browser session."""

    name: str
    mode: str  # "persistent" or "on_demand"
    is_logged_in: bool
    has_browser: bool
    last_activity: str | None
    pending_jobs: int


class SessionListResponse(BaseModel):
    """Response for ``GET /sessions``."""

    sessions: list[SessionInfo]


class SessionActionResponse(BaseModel):
    """Response for session restart/login actions."""

    session: str
    action: str
    success: bool
    message: str


class HealthResponse(BaseModel):
    """Response for ``GET /health``."""

    status: str
    uptime_seconds: float
    memory_mb: float
    memory_percent: float
    queue_depth: int
    pending_jobs: int
    sessions: list[SessionInfo]


# ======================================================================
# Helper: access app state
# ======================================================================

def _get_queue(request: Request) -> JobQueue:
    return request.app.state.job_queue


def _get_sessions(request: Request) -> dict[str, Any]:
    return request.app.state.sessions


def _get_vault(request: Request) -> Any:
    return request.app.state.vault


def _get_start_time(request: Request) -> float:
    return request.app.state.start_time


# ======================================================================
# Job endpoints
# ======================================================================

@router.post("/jobs", response_model=JobSubmitResponse, status_code=201)
async def submit_job(body: JobSubmitRequest, request: Request) -> JobSubmitResponse:
    """Submit a new job to the daemon queue.

    Validates the job type and carrier, creates a ``Job`` instance, and
    adds it to the priority queue.
    """
    # Validate job type
    try:
        job_type = JobType(body.type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid job type: '{body.type}'. Must be one of: {[t.value for t in JobType]}",
        )

    # Validate carrier for waybill jobs
    valid_carriers = {"yamato", "sagawa", "rakuten"}
    if job_type == JobType.PRINT_WAYBILL:
        if body.carrier and body.carrier not in valid_carriers:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid carrier: '{body.carrier}'. Must be one of: {sorted(valid_carriers)}",
            )
        if not body.carrier:
            body.carrier = "yamato"  # default carrier

    # Validate that the target session exists and is enabled
    sessions = _get_sessions(request)
    job = Job(
        job_type=job_type,
        carrier=body.carrier,
        priority=body.priority,
        params=body.params,
    )

    target_session = job.session_name()
    if target_session not in sessions:
        raise HTTPException(
            status_code=400,
            detail=f"Session '{target_session}' is not configured or enabled",
        )

    queue = _get_queue(request)
    job_id = queue.submit(job)

    log.info("Job submitted via API: %s (type=%s, carrier=%s)", job_id, body.type, body.carrier)

    return JobSubmitResponse(job_id=job_id, status=JobStatus.QUEUED.value)


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str, request: Request) -> JobStatusResponse:
    """Check the status and result of a job."""
    queue = _get_queue(request)
    job = queue.get_job(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    d = job.to_dict()
    return JobStatusResponse(**d)


@router.delete("/jobs/{job_id}", response_model=CancelResponse)
async def cancel_job(job_id: str, request: Request) -> CancelResponse:
    """Cancel a pending job.

    Only jobs in the ``queued`` state can be cancelled.
    """
    queue = _get_queue(request)
    job = queue.get_job(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    cancelled = queue.cancel(job_id)

    if cancelled:
        log.info("Job cancelled via API: %s", job_id)
    else:
        log.info("Job %s could not be cancelled (status=%s)", job_id, job.status.value)

    return CancelResponse(job_id=job_id, cancelled=cancelled)


# ======================================================================
# Session endpoints
# ======================================================================

def _session_info(name: str, session: Any, queue: JobQueue) -> SessionInfo:
    """Build a ``SessionInfo`` for a session object."""
    pending_count = sum(
        1 for j in queue.pending_jobs()
        if j.session_name() == name
    )

    # Determine mode
    mode = "persistent" if hasattr(session, "keepalive") else "on_demand"

    # Determine has_browser
    has_browser = (
        session.browser is not None
    ) if hasattr(session, "browser") else False

    # Last activity
    last_activity = None
    if hasattr(session, "last_activity") and session.last_activity is not None:
        last_activity = session.last_activity.isoformat()

    return SessionInfo(
        name=name,
        mode=mode,
        is_logged_in=getattr(session, "is_logged_in", False),
        has_browser=has_browser,
        last_activity=last_activity,
        pending_jobs=pending_count,
    )


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(request: Request) -> SessionListResponse:
    """List all configured sessions with their current status."""
    sessions = _get_sessions(request)
    queue = _get_queue(request)

    infos = [
        _session_info(name, session, queue)
        for name, session in sessions.items()
    ]

    return SessionListResponse(sessions=infos)


@router.post("/sessions/{name}/restart", response_model=SessionActionResponse)
async def restart_session(name: str, request: Request) -> SessionActionResponse:
    """Force restart a browser session.

    Closes the current browser (saving cookies), then re-launches it.
    """
    sessions = _get_sessions(request)
    session = sessions.get(name)

    if session is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {name}")

    try:
        log.info("Restarting session '%s' via API", name)
        await session.close()
        # For persistent sessions, re-launch the browser
        if hasattr(session, "keepalive"):
            await session.start()
        return SessionActionResponse(
            session=name,
            action="restart",
            success=True,
            message=f"Session '{name}' restarted successfully",
        )
    except Exception as exc:
        log.exception("Failed to restart session '%s'", name)
        return SessionActionResponse(
            session=name,
            action="restart",
            success=False,
            message=f"Restart failed: {exc}",
        )


@router.post("/sessions/{name}/login", response_model=SessionActionResponse)
async def force_login(name: str, request: Request) -> SessionActionResponse:
    """Force a re-login for a specific session.

    Useful when cookies have expired and the operator wants to trigger
    an automated login attempt.
    """
    sessions = _get_sessions(request)
    session = sessions.get(name)

    if session is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {name}")

    try:
        log.info("Forcing login for session '%s' via API", name)
        success = await session.login()
        return SessionActionResponse(
            session=name,
            action="login",
            success=success,
            message=(
                f"Login {'succeeded' if success else 'failed -- human intervention may be needed'}"
            ),
        )
    except Exception as exc:
        log.exception("Login failed for session '%s'", name)
        return SessionActionResponse(
            session=name,
            action="login",
            success=False,
            message=f"Login failed: {exc}",
        )


@router.post(
    "/sessions/{name}/inject-cookies",
    response_model=CookieInjectResponse,
)
async def inject_cookies(
    name: str,
    body: CookieInjectRequest,
    request: Request,
) -> CookieInjectResponse:
    """Inject cookies and user-agent from the Chrome Extension.

    This is the human fallback flow: when automated login fails, a human
    operator manually logs into the carrier site in their browser, and
    the Chrome Extension extracts cookies + UA and POSTs them here.

    Steps:

    1. Save cookies + UA to disk via ``CookieStore``.
    2. Apply cookies to the browser session.
    3. Validate the session via ``is_alive()``.
    4. If valid: requeue all ``PENDING_USER_LOGIN`` jobs for this session.
    """
    sessions = _get_sessions(request)
    session = sessions.get(name)

    if session is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {name}")

    queue = _get_queue(request)

    try:
        log.info(
            "Injecting %d cookies for session '%s' (UA=%s...)",
            len(body.cookies), name, body.user_agent[:50],
        )

        # Apply cookies and user agent to the session
        await session.inject_cookies(body.cookies, body.user_agent)

        # Validate the session
        session_valid = await session.is_alive()

        # Requeue pending jobs if session is valid
        jobs_requeued = 0
        if session_valid:
            jobs_requeued = queue.requeue_pending_user_login(name)
            log.info(
                "Session '%s' validated after cookie injection -- %d jobs requeued",
                name, jobs_requeued,
            )
        else:
            log.warning(
                "Session '%s' failed validation after cookie injection",
                name,
            )

        return CookieInjectResponse(
            session=name,
            cookies_applied=len(body.cookies),
            jobs_requeued=jobs_requeued,
            session_valid=session_valid,
        )

    except Exception as exc:
        log.exception("Cookie injection failed for session '%s'", name)
        raise HTTPException(
            status_code=500,
            detail=f"Cookie injection failed: {exc}",
        )


# ======================================================================
# PDF download endpoint
# ======================================================================

@router.get("/pdfs/{job_id}")
async def download_pdf(job_id: str, request: Request) -> FileResponse:
    """Download the waybill PDF for a completed job."""
    queue = _get_queue(request)
    job = queue.get_job(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Job is not completed (status={job.status.value})",
        )

    result = job.result or {}
    pdf_path_str = result.get("pdf_path")
    if not pdf_path_str:
        raise HTTPException(status_code=404, detail="No PDF available for this job")

    pdf_path = Path(pdf_path_str)
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF file not found on disk")

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"waybill-{job_id}.pdf",
    )


# ======================================================================
# Health endpoint
# ======================================================================

# --- Flutter Test Endpoints ---


class FlutterTestResponse(BaseModel):
    job_name: str = Field(description="K8s Job name")
    status: str = Field(description="Job status: created | running | completed | failed")
    passed: int | None = Field(default=None, description="Number of passed tests")
    failed: int | None = Field(default=None, description="Number of failed tests")
    results: list[dict[str, Any]] | None = Field(default=None, description="Test results")


@router.post("/test/flutter", response_model=FlutterTestResponse, status_code=201)
async def trigger_flutter_tests() -> FlutterTestResponse:
    """Create K8s Job running 'flutter test' and return job name."""
    import subprocess

    job_name = f"flutter-test-{int(time.time())}"
    kubeconfig = "/etc/rancher/k3s/k3s.yaml"
    namespace = "shinbee"
    image = "asia-northeast1-docker.pkg.dev/your-gcp-project-id/shinbee/flutter-builder:latest"

    manifest = f"""apiVersion: batch/v1
kind: Job
metadata:
  name: {job_name}
  namespace: {namespace}
spec:
  backoffLimit: 0
  ttlSecondsAfterFinished: 3600
  template:
    spec:
      nodeSelector:
        kubernetes.io/arch: amd64
      containers:
        - name: flutter-test
          image: {image}
          command: ["sh", "-c"]
          args:
            - |
              cd /workspace
              git clone --depth=1 https://github.com/placeholder/shinbee-dashboard.git .
              flutter pub get
              flutter test --machine 2>/dev/null || true
          resources:
            requests:
              memory: "1Gi"
              cpu: "500m"
            limits:
              memory: "2Gi"
              cpu: "2"
      restartPolicy: Never
"""
    try:
        subprocess.run(
            ["kubectl", f"--kubeconfig={kubeconfig}", "-n", namespace, "apply", "-f", "-"],
            input=manifest,
            text=True,
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Failed to create job: {e.stderr}")

    return FlutterTestResponse(job_name=job_name, status="created")


@router.get("/test/flutter/{job_name}", response_model=FlutterTestResponse)
async def get_flutter_test_results(job_name: str) -> FlutterTestResponse:
    """Get test results from completed K8s Job logs."""
    import json as json_mod
    import subprocess

    kubeconfig = "/etc/rancher/k3s/k3s.yaml"
    namespace = "shinbee"

    # Check job status
    try:
        result = subprocess.run(
            ["kubectl", f"--kubeconfig={kubeconfig}", "-n", namespace,
             "get", "job", job_name, "-o", "jsonpath={.status}"],
            text=True, check=True, capture_output=True,
        )
        status_json = json_mod.loads(result.stdout) if result.stdout else {}
    except subprocess.CalledProcessError:
        raise HTTPException(status_code=404, detail=f"Job {job_name} not found")

    succeeded = status_json.get("succeeded", 0)
    failed_count = status_json.get("failed", 0)

    if succeeded:
        status = "completed"
    elif failed_count:
        status = "failed"
    elif status_json.get("active", 0):
        status = "running"
    else:
        status = "unknown"

    # Get logs if completed
    passed = None
    failed = None
    results: list[dict[str, Any]] | None = None

    if status in ("completed", "failed"):
        try:
            log_result = subprocess.run(
                ["kubectl", f"--kubeconfig={kubeconfig}", "-n", namespace,
                 "logs", f"job/{job_name}"],
                text=True, check=True, capture_output=True,
            )
            # Parse flutter test --machine JSON output
            test_events = []
            for line in log_result.stdout.splitlines():
                line = line.strip()
                if line.startswith("{"):
                    try:
                        test_events.append(json_mod.loads(line))
                    except json_mod.JSONDecodeError:
                        pass

            passed = sum(1 for e in test_events if e.get("type") == "testDone" and e.get("result") == "success")
            failed = sum(1 for e in test_events if e.get("type") == "testDone" and e.get("result") == "failure")
            results = test_events
        except subprocess.CalledProcessError:
            pass

    return FlutterTestResponse(
        job_name=job_name,
        status=status,
        passed=passed,
        failed=failed,
        results=results,
    )


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request) -> HealthResponse:
    """Health check with memory usage, session states, and queue depth."""
    sessions = _get_sessions(request)
    queue = _get_queue(request)
    start_time = _get_start_time(request)

    # Memory stats
    process = psutil.Process()
    mem_info = process.memory_info()
    mem_mb = mem_info.rss / (1024 * 1024)
    mem_percent = process.memory_percent()

    # Session info
    session_infos = [
        _session_info(name, session, queue)
        for name, session in sessions.items()
    ]

    # Uptime
    uptime = time.time() - start_time

    return HealthResponse(
        status="healthy",
        uptime_seconds=round(uptime, 1),
        memory_mb=round(mem_mb, 1),
        memory_percent=round(mem_percent, 1),
        queue_depth=queue.depth,
        pending_jobs=len(queue.pending_jobs()),
        sessions=session_infos,
    )
