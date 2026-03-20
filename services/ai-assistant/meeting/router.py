"""Meeting Mode API endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

log = logging.getLogger(__name__)
router = APIRouter()


class MeetingDashboardResponse(BaseModel):
    dashboard_id: str
    transcript_masked: str
    action_items: list[dict]
    decisions: list[dict]
    doc_updates: list[dict]
    pii_detections: int


class ApproveRequest(BaseModel):
    approved_action_indices: list[int]
    approved_doc_indices: list[int] = []
    project_id: int


class ApproveResponse(BaseModel):
    tasks_created: int
    docs_queued: int


@router.post("/upload", response_model=MeetingDashboardResponse)
async def upload_meeting_audio(
    request: Request,
    file: UploadFile = File(...),
) -> MeetingDashboardResponse:
    """Upload meeting audio. Returns an approval dashboard with extracted items.

    Pipeline: audio → Speech-to-Text → PII mask → Gemini extraction → dashboard.
    """
    meeting = request.app.state.meeting
    masking = request.app.state.masking

    audio_bytes = await file.read()
    dashboard = await meeting.process_meeting(audio_bytes, masking)

    return MeetingDashboardResponse(**dashboard)


@router.get("/dashboard/{dashboard_id}", response_model=MeetingDashboardResponse)
async def get_dashboard(dashboard_id: str, request: Request) -> MeetingDashboardResponse:
    """Get a pending approval dashboard."""
    meeting = request.app.state.meeting
    dashboard = meeting.get_dashboard(dashboard_id)
    if not dashboard:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return MeetingDashboardResponse(**dashboard)


@router.post("/{dashboard_id}/approve", response_model=ApproveResponse)
async def approve_items(
    dashboard_id: str,
    body: ApproveRequest,
    request: Request,
) -> ApproveResponse:
    """Approve selected items from the meeting dashboard.

    Approved action items are synced to Vikunja as tasks.
    """
    meeting = request.app.state.meeting

    result = await meeting.approve_items(
        dashboard_id=dashboard_id,
        approved_action_indices=body.approved_action_indices,
        approved_doc_indices=body.approved_doc_indices,
        project_id=body.project_id,
    )

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return ApproveResponse(**result)
