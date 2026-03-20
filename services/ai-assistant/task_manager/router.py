"""Vikunja Task Manager API endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel

log = logging.getLogger(__name__)
router = APIRouter()


class TaskActionRequest(BaseModel):
    message: str


class TaskActionResponse(BaseModel):
    action: str
    preview: str
    requires_confirmation: bool
    parsed: dict


class TaskConfirmRequest(BaseModel):
    parsed: dict


class TaskConfirmResponse(BaseModel):
    result: dict


@router.post("/task", response_model=TaskActionResponse)
async def process_task_request(
    body: TaskActionRequest, request: Request,
) -> TaskActionResponse:
    """Parse a natural language task request.

    Returns a structured preview for user confirmation before execution.
    """
    task_manager = request.app.state.task_manager

    result = await task_manager.process_request(body.message)

    return TaskActionResponse(
        action=result["action"],
        preview=result["preview"],
        requires_confirmation=result["requires_confirmation"],
        parsed=result["parsed"],
    )


@router.post("/task/confirm", response_model=TaskConfirmResponse)
async def confirm_task_action(
    body: TaskConfirmRequest, request: Request,
) -> TaskConfirmResponse:
    """Execute a previously previewed task action after user confirmation."""
    task_manager = request.app.state.task_manager

    result = await task_manager.execute_action(body.parsed)

    return TaskConfirmResponse(result=result)
