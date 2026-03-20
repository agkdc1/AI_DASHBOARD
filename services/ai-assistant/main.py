"""AI Guidance & Task Management System — FastAPI application."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from config import settings
from masking.router import router as masking_router
from assistant.router import router as assistant_router
from task_manager.router import router as task_router
from meeting.router import router as meeting_router
from evolution.router import router as evolution_router
from phone.router import router as phone_router
from rakuten.router import router as rakuten_router
from voice_request.router import router as voice_request_router
from call_request.router import router as call_request_router
from iam.router import router as iam_router
from auth.router import router as auth_router
from seating.router import router as seating_router
from fax_review.router import router as fax_review_router
from password_sync.router import router as password_sync_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Startup: warm up PaddleOCR (first load is slow)
    from masking.service import MaskingService
    masking = MaskingService()
    app.state.masking = masking
    await masking.warm_up()

    # Initialize Gemini clients
    from assistant.service import AssistantService
    assistant = AssistantService()
    app.state.assistant = assistant

    # Load SOP context from GCS bucket on startup
    try:
        from google.cloud import storage as gcs
        client = gcs.Client(project=settings.gcp_project)
        bucket = client.bucket(settings.sop_bucket)
        sop_texts = []
        for blob in bucket.list_blobs():
            if blob.name.endswith(".md"):
                sop_texts.append(blob.download_as_text())
        if sop_texts:
            await assistant.load_sop_context("\n\n---\n\n".join(sop_texts))
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Failed to load SOPs from GCS: %s", e)

    from task_manager.service import TaskManagerService
    app.state.task_manager = TaskManagerService()

    from meeting.service import MeetingService
    app.state.meeting = MeetingService()

    from phone.service import PhoneService
    app.state.phone = PhoneService()

    from rakuten.service import RakutenKeyService
    app.state.rakuten = RakutenKeyService()

    from rakuten.scheduler import start_reminder_loop
    app.state.rakuten_reminder_task = await start_reminder_loop(app.state.rakuten)

    from voice_request.service import VoiceRequestService
    app.state.voice_request = VoiceRequestService()

    from call_request.service import CallRequestService
    app.state.call_request = CallRequestService()

    # Initialize IAM database
    from iam.db import init_db
    await init_db()

    # Initialize seating database
    from seating.db import init_db as init_seating_db
    await init_seating_db()

    # Initialize fax review service
    from fax_review.service import FaxReviewService
    app.state.fax_review = FaxReviewService()

    # Initialize password sync service
    from password_sync.service import PasswordSyncService
    app.state.password_sync = PasswordSyncService()

    yield

    # Cancel background tasks
    if hasattr(app.state, "rakuten_reminder_task"):
        app.state.rakuten_reminder_task.cancel()

    # Cleanup


app = FastAPI(
    title="Shinbee AI Assistant",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(masking_router, prefix="/mask", tags=["PII Masking"])
app.include_router(assistant_router, prefix="/assistant", tags=["Assistant"])
app.include_router(task_router, prefix="/assistant", tags=["Task Manager"])
app.include_router(meeting_router, prefix="/meeting", tags=["Meeting Mode"])
app.include_router(evolution_router, prefix="/evolution", tags=["Evolution"])
app.include_router(phone_router, prefix="/phone", tags=["Phone Admin"])
app.include_router(rakuten_router, prefix="/rakuten", tags=["Rakuten Keys"])
app.include_router(voice_request_router, prefix="/voice-request", tags=["Voice Request"])
app.include_router(call_request_router, prefix="/call-request", tags=["Call Request"])
app.include_router(iam_router, prefix="/iam", tags=["IAM"])
app.include_router(auth_router, tags=["Auth Proxy"])
app.include_router(seating_router, prefix="/seating", tags=["Seating"])
app.include_router(fax_review_router, prefix="/fax-review", tags=["Fax Review"])
app.include_router(password_sync_router, tags=["Password Sync"])


@app.get("/health")
async def health():
    return {"status": "healthy", "version": "1.0.0"}
