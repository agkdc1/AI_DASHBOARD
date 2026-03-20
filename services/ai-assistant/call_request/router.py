"""Call request API endpoints."""

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

log = logging.getLogger(__name__)
router = APIRouter()


class InitiateRequest(BaseModel):
    caller_ext: str
    target_ext: str


class AnalyzeRequest(BaseModel):
    caller_email: str = ""
    target_email: str = ""


class ConfirmRequest(BaseModel):
    project_id: int = 1


@router.post("/initiate")
async def initiate_call(body: InitiateRequest, request: Request):
    """Originate a recorded call between two extensions."""
    svc = request.app.state.call_request
    result = await svc.initiate_call(body.caller_ext, body.target_ext)
    if "error" in result:
        raise HTTPException(status_code=502, detail=result["error"])
    return result


@router.get("/{call_id}/status")
async def call_status(call_id: str, request: Request):
    """Check call status."""
    svc = request.app.state.call_request
    return await svc.get_call_status(call_id)


@router.post("/{call_id}/analyze")
async def analyze_recording(
    call_id: str, body: AnalyzeRequest, request: Request
):
    """Download recording, transcribe, and analyze."""
    svc = request.app.state.call_request
    masking = getattr(request.app.state, "masking", None)
    result = await svc.analyze_recording(
        call_id=call_id,
        caller_email=body.caller_email,
        target_email=body.target_email,
        masking_service=masking,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/{call_id}/confirm")
async def confirm_call(call_id: str, body: ConfirmRequest, request: Request):
    """Create Vikunja task from analyzed call."""
    svc = request.app.state.call_request
    result = await svc.confirm_and_create(call_id, body.project_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result
