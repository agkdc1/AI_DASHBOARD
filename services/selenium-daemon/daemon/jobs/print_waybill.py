"""Waybill PDF download job executor.

Handles the ``print_waybill`` job type: navigates a carrier portal,
fills in shipment details, registers the shipment, and downloads the
waybill PDF.  Supports both persistent sessions (Rakuten) and on-demand
sessions (Yamato, Sagawa).

Physical printing is deferred to a future phase -- this executor only
downloads the PDF to the local filesystem.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from .base import Job, JobStatus

if TYPE_CHECKING:
    from ..sessions.base import BaseSession, OnDemandSession

log = logging.getLogger(__name__)


def _is_on_demand(session: BaseSession) -> bool:
    """Check whether the session is an OnDemandSession without importing the class."""
    return hasattr(session, "acquire_browser") and hasattr(session, "release_browser")


async def execute(job: Job, session: BaseSession) -> None:
    """Execute a waybill PDF download job.

    Lifecycle:

    1. Ensure the session is logged in (auto-login or cookie restore).
       If login fails, the job is parked in ``PENDING_USER_LOGIN``.
    2. For on-demand sessions: ``acquire_browser()`` to launch Chrome and
       inject persisted cookies.
    3. Call ``session.create_waybill(job.params)`` which navigates the
       carrier portal, fills forms, and downloads the PDF.
    4. On success: ``job.complete(...)`` with tracking number and PDF path.
    5. On failure: ``job.fail(error_message)``.
    6. For on-demand sessions: ``release_browser()`` to save cookies and
       kill Chrome (frees RAM).

    Args:
        job: The job instance with ``params`` containing shipment details.
        session: The carrier session (Yamato, Sagawa, or Rakuten).
    """
    job.status = JobStatus.RUNNING
    on_demand = _is_on_demand(session)

    try:
        # Step 1: acquire browser for on-demand sessions
        if on_demand:
            log.info("[%s] Acquiring on-demand browser for job %s", session.name, job.job_id)
            await session.acquire_browser()  # type: ignore[attr-defined]

        # Step 2: ensure logged in
        try:
            await session.ensure_logged_in()
        except Exception as exc:
            log.warning(
                "[%s] Login failed for job %s: %s",
                session.name, job.job_id, exc,
            )

        if not session.is_logged_in:
            log.warning(
                "[%s] Automated login failed -- parking job %s as PENDING_USER_LOGIN",
                session.name, job.job_id,
            )
            job.set_pending_user_login()
            return

        # Step 3: create waybill (carrier-specific implementation)
        log.info(
            "[%s] Creating waybill for job %s (order=%s)",
            session.name,
            job.job_id,
            job.params.get("sales_order_id", "unknown"),
        )
        result = await session.create_waybill(job.params)  # type: ignore[attr-defined]

        # Step 4: validate result
        tracking_number = result.get("tracking_number")
        pdf_path = result.get("pdf_path")

        if pdf_path and Path(pdf_path).exists():
            log.info(
                "[%s] Waybill created: tracking=%s, pdf=%s",
                session.name, tracking_number, pdf_path,
            )
            job.complete({
                "tracking_number": tracking_number,
                "pdf_path": pdf_path,
                "carrier": session.name,
                "sales_order_id": job.params.get("sales_order_id"),
            })
        else:
            error_msg = f"Waybill PDF not found at expected path: {pdf_path}"
            log.error("[%s] %s", session.name, error_msg)
            job.fail(error_msg)

    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"
        log.exception("[%s] Job %s failed: %s", session.name, job.job_id, error_msg)
        job.fail(error_msg)

    finally:
        # Step 5: release browser for on-demand sessions (always, even on failure)
        if on_demand:
            try:
                await session.release_browser()  # type: ignore[attr-defined]
                log.info("[%s] Released on-demand browser for job %s", session.name, job.job_id)
            except Exception:
                log.exception(
                    "[%s] Failed to release browser for job %s",
                    session.name, job.job_id,
                )
