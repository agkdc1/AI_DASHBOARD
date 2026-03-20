"""PII masking API endpoints."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, File, Request, UploadFile
from pydantic import BaseModel

from config import settings

log = logging.getLogger(__name__)
router = APIRouter()


class TextMaskRequest(BaseModel):
    text: str


class TextMaskResponse(BaseModel):
    masked_text: str
    detections: list[dict]
    detection_count: int


class ImageMaskResponse(BaseModel):
    masked_text: str
    detections: list[dict]
    detection_count: int
    redacted_image_id: str


@router.post("/text", response_model=TextMaskResponse)
async def mask_text(body: TextMaskRequest, request: Request) -> TextMaskResponse:
    """Mask PII in text input."""
    masking = request.app.state.masking
    masked_text, detections = masking.mask_text(body.text)

    # Store raw text in PII bucket (local only, 7-day retention)
    await _store_raw(body.text, "text", detections)

    return TextMaskResponse(
        masked_text=masked_text,
        detections=detections,
        detection_count=len(detections),
    )


@router.post("/image", response_model=ImageMaskResponse)
async def mask_image(
    request: Request,
    file: UploadFile = File(...),
) -> ImageMaskResponse:
    """Mask PII in a screenshot/image via OCR + redaction."""
    masking = request.app.state.masking
    image_bytes = await file.read()

    redacted_bytes, masked_text, detections = masking.mask_image(image_bytes)

    # Generate ID for the redacted image
    image_id = str(uuid.uuid4())

    # Store raw image in PII bucket
    await _store_raw(image_bytes, "image", detections, image_id)

    # Store redacted image for later retrieval
    await _store_redacted(redacted_bytes, image_id)

    return ImageMaskResponse(
        masked_text=masked_text,
        detections=detections,
        detection_count=len(detections),
        redacted_image_id=image_id,
    )


async def _store_raw(
    data: str | bytes,
    data_type: str,
    detections: list[dict],
    ref_id: str | None = None,
) -> None:
    """Store raw unmasked data in the PII raw bucket (7-day retention)."""
    try:
        from google.cloud import storage

        client = storage.Client(project=settings.gcp_project)
        bucket = client.bucket(settings.pii_raw_bucket)

        ts = datetime.now(timezone.utc).strftime("%Y%m%d/%H%M%S")
        ref = ref_id or uuid.uuid4().hex[:8]
        blob_name = f"{ts}/{ref}.{data_type}"

        blob = bucket.blob(blob_name)
        if isinstance(data, str):
            blob.upload_from_string(data, content_type="text/plain")
        else:
            blob.upload_from_string(data, content_type="image/png")

        log.info("Stored raw %s in gs://%s/%s", data_type, settings.pii_raw_bucket, blob_name)
    except Exception as e:
        log.warning("Failed to store raw PII data: %s", e)


async def _store_redacted(redacted_bytes: bytes, image_id: str) -> None:
    """Store redacted image for later retrieval by the assistant."""
    try:
        from google.cloud import storage

        client = storage.Client(project=settings.gcp_project)
        bucket = client.bucket(settings.ai_logs_bucket)

        blob = bucket.blob(f"redacted/{image_id}.png")
        blob.upload_from_string(redacted_bytes, content_type="image/png")
    except Exception as e:
        log.warning("Failed to store redacted image: %s", e)
