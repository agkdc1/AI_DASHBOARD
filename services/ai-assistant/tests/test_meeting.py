"""Tests for the Meeting Mode service."""

import json
import sys
from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx

from helpers import make_gemini_model, make_speech_client


def _patch_speech_client(mock_client):
    """Create a context manager that patches google.cloud.speech at import time."""
    mock_speech_module = MagicMock()
    mock_speech_module.SpeechClient.return_value = mock_client
    mock_speech_module.RecognitionAudio.return_value = MagicMock()
    mock_speech_module.RecognitionConfig.return_value = MagicMock()
    mock_speech_module.RecognitionConfig.AudioEncoding.LINEAR16 = "LINEAR16"
    return patch.dict("sys.modules", {"google.cloud.speech": mock_speech_module, "google.cloud": MagicMock(speech=mock_speech_module)})


class TestTranscribeAudio:
    async def test_success(self, meeting_service):
        mock_client = make_speech_client("テスト会議の内容です。")
        with _patch_speech_client(mock_client):
            # Need to reimport to pick up the patched module
            from meeting.service import MeetingService
            svc = MeetingService()
            svc._model = meeting_service._model
            result = await svc.transcribe_audio(b"\x00" * 100)
        assert result == "テスト会議の内容です。"

    async def test_empty_results(self, meeting_service):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.results = []
        mock_client.recognize.return_value = mock_response
        with _patch_speech_client(mock_client):
            from meeting.service import MeetingService
            svc = MeetingService()
            result = await svc.transcribe_audio(b"\x00" * 100)
        assert result == ""

    async def test_error_raises(self, meeting_service):
        mock_speech_module = MagicMock()
        mock_speech_module.SpeechClient.side_effect = Exception("API down")
        with patch.dict("sys.modules", {"google.cloud.speech": mock_speech_module, "google.cloud": MagicMock(speech=mock_speech_module)}):
            from meeting.service import MeetingService
            svc = MeetingService()
            with pytest.raises(Exception, match="API down"):
                await svc.transcribe_audio(b"\x00" * 100)


class TestProcessMeeting:
    async def test_full_pipeline(self, meeting_service, masking_service):
        with patch.object(meeting_service, "transcribe_audio", return_value="佐藤太郎が会議で発言しました。"):
            result = await meeting_service.process_meeting(b"\x00", masking_service)

        assert "dashboard_id" in result
        assert "transcript_masked" in result
        assert "action_items" in result
        assert "decisions" in result
        assert "doc_updates" in result
        assert result["pii_detections"] >= 1
        # Stored in pending
        assert result["dashboard_id"] in meeting_service._pending

    async def test_gemini_error_fallback(self, meeting_service, masking_service):
        meeting_service._model.generate_content.side_effect = Exception("Gemini error")
        with patch.object(meeting_service, "transcribe_audio", return_value="テスト"):
            result = await meeting_service.process_meeting(b"\x00", masking_service)

        # Should still return a valid dashboard with empty items
        assert result["action_items"] == []
        assert result["decisions"] == []
        assert result["doc_updates"] == []

    async def test_stores_pending(self, meeting_service, masking_service):
        with patch.object(meeting_service, "transcribe_audio", return_value="テスト"):
            result = await meeting_service.process_meeting(b"\x00", masking_service)

        dashboard = meeting_service.get_dashboard(result["dashboard_id"])
        assert dashboard is not None
        assert dashboard["dashboard_id"] == result["dashboard_id"]


class TestExtractItems:
    async def test_valid_json(self, meeting_service):
        result = await meeting_service._extract_items("テスト議事録")
        assert "action_items" in result
        assert len(result["action_items"]) == 1

    async def test_markdown_wrapped(self, meeting_service):
        meeting_service._model = make_gemini_model(
            '```json\n{"action_items":[],"decisions":[],"doc_updates":[]}\n```'
        )
        result = await meeting_service._extract_items("テスト")
        assert "action_items" in result

    async def test_error_fallback(self, meeting_service):
        meeting_service._model.generate_content.side_effect = Exception("Error")
        result = await meeting_service._extract_items("テスト")
        assert result["action_items"] == []
        assert result["decisions"] == []
        assert result["doc_updates"] == []


class TestGetDashboard:
    def test_exists(self, meeting_service):
        meeting_service._pending["abc"] = {"dashboard_id": "abc", "action_items": []}
        assert meeting_service.get_dashboard("abc") is not None

    def test_not_found(self, meeting_service):
        assert meeting_service.get_dashboard("nonexistent") is None


class TestApproveItems:
    @respx.mock
    async def test_creates_tasks(self, meeting_service):
        dashboard_id = "test-dash"
        meeting_service._pending[dashboard_id] = {
            "dashboard_id": dashboard_id,
            "action_items": [
                {"title": "タスク1", "description": "説明1", "due_date": None},
                {"title": "タスク2", "description": "説明2", "due_date": "2026-03-01"},
            ],
            "doc_updates": [{"target_doc": "SOP", "change": "更新"}],
        }
        route = respx.put("https://vikunja.test/api/v1/projects/1/tasks").mock(
            return_value=httpx.Response(201, json={"id": 1})
        )
        result = await meeting_service.approve_items(dashboard_id, [0, 1], [0], 1)
        assert result["tasks_created"] == 2
        assert result["docs_queued"] == 1
        assert dashboard_id not in meeting_service._pending

    async def test_invalid_dashboard(self, meeting_service):
        result = await meeting_service.approve_items("bad-id", [0], [], 1)
        assert "error" in result

    @respx.mock
    async def test_partial_approval(self, meeting_service):
        dashboard_id = "partial"
        meeting_service._pending[dashboard_id] = {
            "dashboard_id": dashboard_id,
            "action_items": [
                {"title": "タスク1", "description": ""},
                {"title": "タスク2", "description": ""},
            ],
            "doc_updates": [],
        }
        route = respx.put("https://vikunja.test/api/v1/projects/1/tasks").mock(
            return_value=httpx.Response(201, json={"id": 1})
        )
        result = await meeting_service.approve_items(dashboard_id, [0], [], 1)
        assert result["tasks_created"] == 1

    @respx.mock
    async def test_vikunja_failure(self, meeting_service):
        dashboard_id = "fail"
        meeting_service._pending[dashboard_id] = {
            "dashboard_id": dashboard_id,
            "action_items": [{"title": "タスク", "description": ""}],
            "doc_updates": [],
        }
        route = respx.put("https://vikunja.test/api/v1/projects/1/tasks").mock(
            return_value=httpx.Response(500, json={"error": "Internal"})
        )
        result = await meeting_service.approve_items(dashboard_id, [0], [], 1)
        assert result["tasks_created"] == 0
        assert dashboard_id not in meeting_service._pending
