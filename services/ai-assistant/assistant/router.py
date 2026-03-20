"""Guide-Only Assistant API endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel

log = logging.getLogger(__name__)
router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    masked_screenshot_uri: str | None = None
    conversation_history: list[dict] | None = None


class ChatResponse(BaseModel):
    response: str
    screenshots_compared: bool = False


class VerifyRequest(BaseModel):
    before_uri: str
    after_uri: str
    expected_action: str


class VerifyResponse(BaseModel):
    verification: str


class NavigateRequest(BaseModel):
    message: str
    screenshot_base64: str | None = None
    dom_summary: str | None = None
    current_url: str | None = None
    conversation_history: list[dict] | None = None


class NavigateAction(BaseModel):
    type: str  # "highlight", "navigate", "click", "scroll"
    selector: str | None = None
    url: str | None = None
    label: str | None = None


class NavigateResponse(BaseModel):
    response_text: str
    actions: list[NavigateAction] = []


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, request: Request) -> ChatResponse:
    """Send a message to the guide-only assistant.

    The message and any screenshots must already be PII-masked.
    """
    assistant = request.app.state.assistant

    response_text = await assistant.chat(
        message=body.message,
        masked_screenshot_uri=body.masked_screenshot_uri,
        conversation_history=body.conversation_history,
    )

    return ChatResponse(response=response_text)


@router.post("/reload-sops")
async def reload_sops(request: Request) -> dict:
    """Reload SOP context from GCS bucket."""
    from config import settings
    from google.cloud import storage as gcs

    client = gcs.Client(project=settings.gcp_project)
    bucket = client.bucket(settings.sop_bucket)
    sop_texts = []
    for blob in bucket.list_blobs():
        if blob.name.endswith(".md"):
            sop_texts.append(blob.download_as_text())
            log.info("Loaded SOP: %s", blob.name)

    assistant = request.app.state.assistant
    if sop_texts:
        combined = "\n\n---\n\n".join(sop_texts)
        await assistant.load_sop_context(combined)
        return {"status": "loaded", "files": len(sop_texts), "chars": len(combined)}
    return {"status": "empty", "files": 0}


@router.post("/navigate", response_model=NavigateResponse)
async def navigate(body: NavigateRequest, request: Request) -> NavigateResponse:
    """AI-guided navigation: analyze current page and return actions.

    Used by the Shinbee AI Navigator Chrome extension to guide users
    through the InvenTree portal and Flutter dashboard.
    """
    assistant = request.app.state.assistant

    result = await assistant.navigate(
        message=body.message,
        screenshot_base64=body.screenshot_base64,
        dom_summary=body.dom_summary,
        current_url=body.current_url,
        conversation_history=body.conversation_history,
    )

    actions = [NavigateAction(**a) for a in result.get("actions", [])]
    return NavigateResponse(
        response_text=result.get("response_text", ""),
        actions=actions,
    )


@router.post("/verify", response_model=VerifyResponse)
async def verify_action(body: VerifyRequest, request: Request) -> VerifyResponse:
    """Compare before/after screenshots to verify an action was performed."""
    assistant = request.app.state.assistant

    result = await assistant.compare_screenshots(
        before_uri=body.before_uri,
        after_uri=body.after_uri,
        expected_action=body.expected_action,
    )

    return VerifyResponse(verification=result)
