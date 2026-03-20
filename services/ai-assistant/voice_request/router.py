"""Voice request API endpoints."""

import logging

from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from pydantic import BaseModel

log = logging.getLogger(__name__)
router = APIRouter()


class ConfirmRequest(BaseModel):
    project_id: int = 1


@router.post("/submit")
async def submit_voice(
    request: Request,
    audio: UploadFile = File(...),
    caller_email: str = Form(""),
    target_email: str = Form(""),
    lang: str = Form("ja-JP"),
):
    """Submit voice recording for analysis."""
    svc = request.app.state.voice_request
    masking = getattr(request.app.state, "masking", None)
    audio_bytes = await audio.read()

    result = await svc.process_voice(
        audio_bytes=audio_bytes,
        caller_email=caller_email,
        target_email=target_email,
        lang=lang,
        masking_service=masking,
    )
    return result


@router.get("/{request_id}")
async def get_preview(request_id: str, request: Request):
    """Get pending voice request preview."""
    svc = request.app.state.voice_request
    preview = svc.get_pending(request_id)
    if not preview:
        raise HTTPException(status_code=404, detail="Request not found")
    return preview


@router.post("/{request_id}/confirm")
async def confirm_request(
    request_id: str, body: ConfirmRequest, request: Request
):
    """Confirm and create Vikunja task from voice request."""
    svc = request.app.state.voice_request
    result = await svc.confirm_and_create(request_id, body.project_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result
