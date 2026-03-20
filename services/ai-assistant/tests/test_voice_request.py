"""Tests for the Voice Request service."""

import json
import sys
from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx

from helpers import make_gemini_model, make_speech_client


def _patch_speech_client(mock_client):
    """Patch google.cloud.speech at sys.modules level for lazy imports."""
    mock_mod = MagicMock()
    mock_mod.SpeechClient.return_value = mock_client
    mock_mod.RecognitionAudio.return_value = MagicMock()
    mock_mod.RecognitionConfig.return_value = MagicMock()
    mock_mod.RecognitionConfig.AudioEncoding.LINEAR16 = "LINEAR16"
    return patch.dict("sys.modules", {
        "google.cloud.speech": mock_mod,
        "google.cloud": MagicMock(speech=mock_mod),
    })


class TestTranscribeAudio:
    async def test_success(self, voice_request_service):
        mock_client = make_speech_client("テスト音声依頼です。")
        with _patch_speech_client(mock_client):
            from voice_request.service import VoiceRequestService
            svc = VoiceRequestService()
            result = await svc.transcribe_audio(b"\x00" * 100)
        assert result == "テスト音声依頼です。"

    async def test_empty_results(self, voice_request_service):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.results = []
        mock_client.recognize.return_value = mock_response
        with _patch_speech_client(mock_client):
            from voice_request.service import VoiceRequestService
            svc = VoiceRequestService()
            result = await svc.transcribe_audio(b"\x00" * 100)
        assert result == ""


class TestProcessVoice:
    async def test_full_pipeline(self, voice_request_service, masking_service):
        with patch.object(voice_request_service, "transcribe_audio", return_value="佐藤太郎さんに連絡してください"):
            result = await voice_request_service.process_voice(
                b"\x00", "caller@test.com", "target@test.com",
                masking_service=masking_service,
            )

        assert "request_id" in result
        assert "transcript_masked" in result
        assert "[REDACTED_NAME]" in result["transcript_masked"]
        assert result["caller_email"] == "caller@test.com"
        assert result["request_id"] in voice_request_service._pending

    async def test_without_masking(self, voice_request_service):
        with patch.object(voice_request_service, "transcribe_audio", return_value="テスト"):
            result = await voice_request_service.process_voice(
                b"\x00", "a@b.com", "c@d.com", masking_service=None,
            )
        assert result["transcript_masked"] == "テスト"

    async def test_stores_pending(self, voice_request_service):
        with patch.object(voice_request_service, "transcribe_audio", return_value="テスト"):
            result = await voice_request_service.process_voice(
                b"\x00", "a@b.com", "c@d.com",
            )
        pending = voice_request_service.get_pending(result["request_id"])
        assert pending is not None

    async def test_gemini_error_fallback(self, voice_request_service):
        voice_request_service._model.generate_content.side_effect = Exception("Gemini error")
        with patch.object(voice_request_service, "transcribe_audio", return_value="テスト"):
            result = await voice_request_service.process_voice(
                b"\x00", "a@b.com", "c@d.com",
            )
        assert result["title"] == "音声依頼"
        assert result["description"] == "テスト"


class TestAnalyze:
    async def test_valid_json(self, voice_request_service):
        result = await voice_request_service._analyze("テスト内容")
        assert "title" in result
        assert "priority" in result

    async def test_error(self, voice_request_service):
        voice_request_service._model.generate_content.side_effect = Exception("Error")
        result = await voice_request_service._analyze("テスト")
        assert result["title"] == "音声依頼"
        assert result["missing_details"] == []


class TestConfirmAndCreate:
    @respx.mock
    async def test_success(self, voice_request_service):
        request_id = "test-req-id"
        voice_request_service._pending[request_id] = {
            "request_id": request_id,
            "title": "テストタスク",
            "description": "説明",
            "priority": 2,
            "due_date": None,
        }
        respx.put("https://vikunja.test/api/v1/projects/1/tasks").mock(
            return_value=httpx.Response(201, json={"id": 42})
        )

        result = await voice_request_service.confirm_and_create(request_id, 1)
        assert result["task_created"] is True
        assert result["task_id"] == 42
        assert request_id not in voice_request_service._pending

    async def test_not_found(self, voice_request_service):
        result = await voice_request_service.confirm_and_create("bad-id", 1)
        assert "error" in result

    @respx.mock
    async def test_vikunja_error(self, voice_request_service):
        request_id = "err-req"
        voice_request_service._pending[request_id] = {
            "title": "タスク", "description": "", "priority": 2, "due_date": None,
        }
        respx.put("https://vikunja.test/api/v1/projects/1/tasks").mock(
            return_value=httpx.Response(500, text="Server error")
        )
        result = await voice_request_service.confirm_and_create(request_id, 1)
        assert "error" in result
