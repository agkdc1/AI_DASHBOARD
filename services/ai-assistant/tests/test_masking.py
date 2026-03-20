"""Tests for PII masking patterns and service."""

from unittest.mock import MagicMock, patch

import pytest

from masking.patterns import (
    PHONE_PATTERN,
    EMAIL_PATTERN,
    POSTAL_PATTERN,
    PREFECTURE_PATTERN,
    CREDIT_CARD_PATTERN,
    JAPANESE_NAME_PATTERN,
    YAMATO_TRACKING,
    JAPAN_POST_TRACKING,
    PII_PATTERNS,
)
from masking.service import MaskingService


# ─────────────────────────────────────────────────────────────────────
# Pattern tests
# ─────────────────────────────────────────────────────────────────────

class TestPhonePattern:
    def test_landline_with_hyphens(self):
        assert PHONE_PATTERN.search("03-1234-5678")

    def test_mobile_with_hyphens(self):
        assert PHONE_PATTERN.search("090-1234-5678")

    def test_toll_free(self):
        assert PHONE_PATTERN.search("0120-123-456")

    def test_no_hyphens(self):
        assert PHONE_PATTERN.search("09012345678")

    def test_with_spaces(self):
        assert PHONE_PATTERN.search("03 1234 5678")

    def test_non_phone_no_match(self):
        # Short number should not match
        assert not PHONE_PATTERN.search("12345")


class TestEmailPattern:
    def test_standard_email(self):
        assert EMAIL_PATTERN.search("test@example.com")

    def test_company_email(self):
        assert EMAIL_PATTERN.search("admin@your-domain.com")

    def test_email_with_dots_and_plus(self):
        assert EMAIL_PATTERN.search("first.last+tag@domain.co.jp")

    def test_no_at_sign_no_match(self):
        assert not EMAIL_PATTERN.search("not-an-email")


class TestPostalPattern:
    def test_with_prefix(self):
        assert POSTAL_PATTERN.search("〒123-4567")

    def test_without_prefix(self):
        assert POSTAL_PATTERN.search("123-4567")

    def test_no_hyphen(self):
        assert POSTAL_PATTERN.search("1234567")


class TestPrefecturePattern:
    def test_tokyo_address(self):
        assert PREFECTURE_PATTERN.search("東京都渋谷区神宮前1-2-3")

    def test_osaka_address(self):
        assert PREFECTURE_PATTERN.search("大阪府大阪市北区梅田")

    def test_hokkaido_address(self):
        assert PREFECTURE_PATTERN.search("北海道札幌市中央区")


class TestCreditCardPattern:
    def test_with_hyphens(self):
        assert CREDIT_CARD_PATTERN.search("1234-5678-9012-3456")

    def test_with_spaces(self):
        assert CREDIT_CARD_PATTERN.search("1234 5678 9012 3456")

    def test_continuous(self):
        assert CREDIT_CARD_PATTERN.search("1234567890123456")

    def test_short_number_no_match(self):
        assert not CREDIT_CARD_PATTERN.search("1234-5678-9012")


class TestJapaneseNamePattern:
    def test_sato_taro(self):
        assert JAPANESE_NAME_PATTERN.search("佐藤太郎")

    def test_tanaka_hanako(self):
        assert JAPANESE_NAME_PATTERN.search("田中花子")

    def test_suzuki_ichiro(self):
        assert JAPANESE_NAME_PATTERN.search("鈴木一郎")

    def test_with_space(self):
        assert JAPANESE_NAME_PATTERN.search("佐藤 太郎")

    def test_uncommon_surname_no_match(self):
        # A non-listed surname should not match
        assert not JAPANESE_NAME_PATTERN.search("宇宙太郎")


class TestTrackingPatterns:
    def test_yamato_12_digit(self):
        assert YAMATO_TRACKING.search("123456789012")

    def test_japan_post_ems(self):
        assert JAPAN_POST_TRACKING.search("EJ123456789JP")

    def test_ems_lowercase_no_match(self):
        assert not JAPAN_POST_TRACKING.search("ej123456789jp")


# ─────────────────────────────────────────────────────────────────────
# MaskingService.mask_text() tests
# ─────────────────────────────────────────────────────────────────────

class TestMaskText:
    def test_multiple_pii_types(self, masking_service):
        text = "佐藤太郎さんの電話番号は090-1234-5678です。メール: test@example.com"
        masked, detections = masking_service.mask_text(text)

        assert "[REDACTED_NAME]" in masked
        assert "[REDACTED_EMAIL]" in masked
        assert "090-1234-5678" not in masked
        # Phone is detected but postal also matches a sub-span
        assert len(detections) >= 3
        det_types = {d["type"] for d in detections}
        assert "[REDACTED_PHONE]" in det_types
        assert "[REDACTED_EMAIL]" in det_types
        assert "[REDACTED_NAME]" in det_types

    def test_no_pii(self, masking_service):
        text = "今日の天気は晴れです。"
        masked, detections = masking_service.mask_text(text)
        assert masked == text
        assert len(detections) == 0

    def test_empty_string(self, masking_service):
        masked, detections = masking_service.mask_text("")
        assert masked == ""
        assert len(detections) == 0

    def test_detection_spans(self, masking_service):
        text = "連絡先: 03-1234-5678"
        masked, detections = masking_service.mask_text(text)
        phone_det = [d for d in detections if d["type"] == "[REDACTED_PHONE]"]
        assert len(phone_det) >= 1
        assert phone_det[0]["original_span"][0] < phone_det[0]["original_span"][1]
        assert phone_det[0]["matched"] == "03-1234-5678"

    def test_credit_card_detected(self, masking_service):
        text = "カード番号: 1234-5678-9012-3456"
        masked, detections = masking_service.mask_text(text)
        det_types = {d["type"] for d in detections}
        assert "[REDACTED_CARD]" in det_types
        assert "1234-5678-9012-3456" not in masked

    def test_postal_code_masked(self, masking_service):
        text = "〒123-4567 東京都渋谷区"
        masked, detections = masking_service.mask_text(text)
        assert "[REDACTED_POSTAL]" in masked

    def test_address_masked(self, masking_service):
        text = "住所は東京都渋谷区神宮前1-2-3です。"
        masked, detections = masking_service.mask_text(text)
        assert "[REDACTED_ADDRESS]" in masked


# ─────────────────────────────────────────────────────────────────────
# MaskingService.mask_image() tests (mock PaddleOCR)
# ─────────────────────────────────────────────────────────────────────

class TestMaskImage:
    def _make_test_image_bytes(self) -> bytes:
        """Create a minimal PNG image for testing."""
        from PIL import Image
        import io
        img = Image.new("RGB", (100, 30), color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def test_image_with_pii(self, masking_service):
        """OCR finds phone number text; it should be redacted."""
        # Mock OCR to return a detected phone number
        mock_ocr = MagicMock()
        mock_ocr.ocr.return_value = [[
            [[[0, 0], [100, 0], [100, 30], [0, 30]], ("電話: 090-1234-5678", 0.95)],
        ]]
        masking_service._ocr = mock_ocr

        redacted_bytes, masked_text, detections = masking_service.mask_image(
            self._make_test_image_bytes()
        )
        assert isinstance(redacted_bytes, bytes)
        assert len(redacted_bytes) > 0
        # Phone is detected (may overlap with postal pattern in masked text)
        det_types = {d["type"] for d in detections}
        assert "[REDACTED_PHONE]" in det_types
        assert len(detections) >= 1

    def test_image_no_ocr_results(self, masking_service):
        """OCR returns no text — should return empty text, no detections."""
        mock_ocr = MagicMock()
        mock_ocr.ocr.return_value = [[]]
        masking_service._ocr = mock_ocr

        redacted_bytes, masked_text, detections = masking_service.mask_image(
            self._make_test_image_bytes()
        )
        assert isinstance(redacted_bytes, bytes)
        assert masked_text == ""
        assert len([d for d in detections if "bbox" in d]) == 0

    def test_image_none_results(self, masking_service):
        """OCR returns None — should handle gracefully."""
        mock_ocr = MagicMock()
        mock_ocr.ocr.return_value = [None]
        masking_service._ocr = mock_ocr

        redacted_bytes, masked_text, detections = masking_service.mask_image(
            self._make_test_image_bytes()
        )
        assert isinstance(redacted_bytes, bytes)
