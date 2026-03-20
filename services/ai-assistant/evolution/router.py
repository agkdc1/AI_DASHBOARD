"""Weekly Evolution Loop API endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from .service import EvolutionService

log = logging.getLogger(__name__)
router = APIRouter()

_service = EvolutionService()


class EvolutionResponse(BaseModel):
    proposal: str
    email_sent: bool
    task_created: bool


@router.post("/trigger", response_model=EvolutionResponse)
async def trigger_evolution() -> EvolutionResponse:
    """Manually trigger the weekly evolution analysis.

    In production this runs as a K8s CronJob every Saturday 09:00 JST.
    This endpoint allows manual triggering for testing.
    """
    result = await _service.run_weekly_analysis()
    return EvolutionResponse(**result)
