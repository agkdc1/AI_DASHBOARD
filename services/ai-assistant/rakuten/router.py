"""Rakuten API key management endpoints."""

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

log = logging.getLogger(__name__)
router = APIRouter()


class KeyStatusResponse(BaseModel):
    renewed_at: str | None
    age_days: int | None
    days_until_reminder: int | None
    days_until_deadline: int | None
    assigned_employees: list[str]


class KeySubmitRequest(BaseModel):
    service_secret: str
    license_key: str
    submitted_by: str = ""


class KeySubmitResponse(BaseModel):
    renewed_at: str
    inventree_updated: bool
    vikunja_task_closed: bool


class AssigneeRequest(BaseModel):
    employees: list[str]


class InstructionsResponse(BaseModel):
    title: str
    steps: list[str]
    link: str


@router.get("/status", response_model=KeyStatusResponse)
async def get_key_status(request: Request) -> KeyStatusResponse:
    """Get current API key age and reminder status."""
    svc = request.app.state.rakuten
    status = await svc.get_key_status()
    return KeyStatusResponse(**status)


@router.post("/keys", response_model=KeySubmitResponse)
async def submit_keys(body: KeySubmitRequest, request: Request) -> KeySubmitResponse:
    """Submit renewed API keys."""
    svc = request.app.state.rakuten
    if not body.service_secret or not body.license_key:
        raise HTTPException(status_code=400, detail="Both keys are required")
    result = await svc.submit_new_keys(
        service_secret=body.service_secret,
        license_key=body.license_key,
        submitted_by=body.submitted_by,
    )
    return KeySubmitResponse(**result)


@router.put("/assignees")
async def set_assignees(body: AssigneeRequest, request: Request):
    """Set the employees responsible for key renewal."""
    svc = request.app.state.rakuten
    return await svc.update_assignees(body.employees)


@router.get("/instructions", response_model=InstructionsResponse)
async def get_instructions(
    request: Request, lang: str = "ja"
) -> InstructionsResponse:
    """Get step-by-step renewal instructions."""
    svc = request.app.state.rakuten
    return InstructionsResponse(**svc.get_instructions(lang))
