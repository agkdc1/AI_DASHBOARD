"""PII Masking Service — all raw input passes through here before reaching any LLM."""

from __future__ import annotations

import io
import logging
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from .patterns import PII_PATTERNS

log = logging.getLogger(__name__)


class MaskingService:
    """OCR-based PII detection and redaction for images and text."""

    def __init__(self) -> None:
        self._ocr: Any = None

    async def warm_up(self) -> None:
        """Warm up PaddleOCR (first load downloads models)."""
        log.info("Warming up PaddleOCR...")
        try:
            from paddleocr import PaddleOCR
            self._ocr = PaddleOCR(
                use_angle_cls=True,
                lang="japan",
                show_log=False,
                use_gpu=False,
            )
            log.info("PaddleOCR ready")
        except Exception as e:
            log.warning("PaddleOCR init failed (will retry on first use): %s", e)

    def _ensure_ocr(self) -> Any:
        if self._ocr is None:
            from paddleocr import PaddleOCR
            self._ocr = PaddleOCR(
                use_angle_cls=True,
                lang="japan",
                show_log=False,
                use_gpu=False,
            )
        return self._ocr

    def mask_text(self, text: str) -> tuple[str, list[dict]]:
        """Mask PII in text. Returns (masked_text, list of detections)."""
        detections: list[dict] = []
        masked = text

        for pattern, label in PII_PATTERNS:
            for match in pattern.finditer(text):
                detections.append({
                    "type": label,
                    "original_span": [match.start(), match.end()],
                    "matched": match.group(),
                })

        # Apply replacements in reverse order to preserve positions.
        for pattern, label in reversed(PII_PATTERNS):
            masked = pattern.sub(label, masked)

        return masked, detections

    def mask_image(self, image_bytes: bytes) -> tuple[bytes, str, list[dict]]:
        """Mask PII in an image via OCR + redaction.

        Returns:
            (redacted_image_bytes, extracted_masked_text, detections)
        """
        ocr = self._ensure_ocr()

        # Load image
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img_array = np.array(img)

        # Run OCR
        results = ocr.ocr(img_array, cls=True)

        draw = ImageDraw.Draw(img)
        all_text_parts: list[str] = []
        detections: list[dict] = []

        if results and results[0]:
            for line in results[0]:
                bbox, (text, confidence) = line
                all_text_parts.append(text)

                # Check if this text contains PII
                for pattern, label in PII_PATTERNS:
                    if pattern.search(text):
                        # Redact by drawing black box over the bbox
                        points = [(int(p[0]), int(p[1])) for p in bbox]
                        x_coords = [p[0] for p in points]
                        y_coords = [p[1] for p in points]
                        draw.rectangle(
                            [min(x_coords), min(y_coords),
                             max(x_coords), max(y_coords)],
                            fill="black",
                        )
                        detections.append({
                            "type": label,
                            "text": text,
                            "bbox": bbox,
                            "confidence": confidence,
                        })
                        break  # One redaction per text region

        # Get masked text from all extracted text
        full_text = "\n".join(all_text_parts)
        masked_text, text_detections = self.mask_text(full_text)
        detections.extend(text_detections)

        # Save redacted image
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        redacted_bytes = buf.getvalue()

        return redacted_bytes, masked_text, detections
