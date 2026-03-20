"""Tests for the Call Request service."""

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


class TestInitiateCall:
    @respx.mock
    async def test_success(self, call_request_service):
        respx.post("http://faxapi.test:8010/calls/originate").mock(
            return_value=httpx.Response(200, json={"status": "ok"})
        )
        result = await call_request_service.initiate_call("300", "301")
        assert "call_id" in result
        assert result["status"] == "ringing"
        assert result["call_id"] in call_request_service._pending

    @respx.mock
    async def test_faxapi_error(self, call_request_service):
        respx.post("http://faxapi.test:8010/calls/originate").mock(
            return_value=httpx.Response(500, text="Asterisk error")
        )
        result = await call_request_service.initiate_call("300", "301")
        assert "error" in result

    @respx.mock
    async def test_network_error(self, call_request_service):
        respx.post("http://faxapi.test:8010/calls/originate").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        # The service doesn't catch ConnectError in initiate_call, it raises
        with pytest.raises(httpx.ConnectError):
            await call_request_service.initiate_call("300", "301")


class TestGetCallStatus:
    @respx.mock
    async def test_from_faxapi(self, call_request_service):
        respx.get("http://faxapi.test:8010/calls/abc123/status").mock(
            return_value=httpx.Response(200, json={"status": "completed", "recording": True})
        )
        result = await call_request_service.get_call_status("abc123")
        assert result["status"] == "completed"

    async def test_from_pending(self, call_request_service):
        call_request_service._pending["xyz"] = {
            "call_id": "xyz", "status": "ringing",
        }
        with respx.mock:
            respx.get("http://faxapi.test:8010/calls/xyz/status").mock(
                return_value=httpx.Response(404)
            )
            result = await call_request_service.get_call_status("xyz")
        assert result["status"] == "ringing"

    async def test_not_found(self, call_request_service):
        with respx.mock:
            respx.get("http://faxapi.test:8010/calls/missing/status").mock(
                side_effect=httpx.ConnectError("fail")
            )
            result = await call_request_service.get_call_status("missing")
        assert "error" in result


class TestAnalyzeRecording:
    @respx.mock
    async def test_full_pipeline(self, call_request_service, masking_service):
        respx.get("http://faxapi.test:8010/calls/call1/recording").mock(
            return_value=httpx.Response(200, content=b"\x00" * 100)
        )

        with patch.object(call_request_service, "_transcribe", return_value="佐藤太郎さんとの通話内容です。"):
            result = await call_request_service.analyze_recording(
                "call1", "a@b.com", "c@d.com", masking_service=masking_service,
            )

        assert "transcript_masked" in result
        assert "[REDACTED_NAME]" in result["transcript_masked"]
        assert "call1" in call_request_service._pending

    @respx.mock
    async def test_no_recording(self, call_request_service):
        respx.get("http://faxapi.test:8010/calls/call2/recording").mock(
            return_value=httpx.Response(404, text="Not found")
        )
        result = await call_request_service.analyze_recording(
            "call2", "a@b.com", "c@d.com",
        )
        assert "error" in result

    @respx.mock
    async def test_stores_pending(self, call_request_service):
        respx.get("http://faxapi.test:8010/calls/call3/recording").mock(
            return_value=httpx.Response(200, content=b"\x00" * 50)
        )
        with patch.object(call_request_service, "_transcribe", return_value="テスト通話"):
            result = await call_request_service.analyze_recording(
                "call3", "a@b.com", "c@d.com",
            )
        assert call_request_service._pending.get("call3") is not None


class TestTranscribe:
    async def test_success(self, call_request_service):
        mock_client = make_speech_client("テスト")
        with _patch_speech_client(mock_client):
            from call_request.service import CallRequestService
            svc = CallRequestService()
            result = await svc._transcribe(b"\x00" * 50)
        assert result == "テスト"


class TestAnalyze:
    async def test_valid_json(self, call_request_service):
        result = await call_request_service._analyze("テスト通話内容")
        assert "title" in result
        assert "decisions" in result

    async def test_error(self, call_request_service):
        call_request_service._model.generate_content.side_effect = Exception("Error")
        result = await call_request_service._analyze("テスト")
        assert result["title"] == "通話依頼"
        assert result["decisions"] == []


class TestConfirmAndCreate:
    @respx.mock
    async def test_success(self, call_request_service):
        call_request_service._pending["call1"] = {
            "call_id": "call1",
            "title": "通話タスク",
            "description": "内容",
            "priority": 2,
            "due_date": None,
        }
        respx.put("https://vikunja.test/api/v1/projects/1/tasks").mock(
            return_value=httpx.Response(201, json={"id": 77})
        )

        result = await call_request_service.confirm_and_create("call1", 1)
        assert result["task_created"] is True
        assert result["task_id"] == 77
        assert "call1" not in call_request_service._pending

    async def test_not_found(self, call_request_service):
        result = await call_request_service.confirm_and_create("bad", 1)
        assert "error" in result

    @respx.mock
    async def test_with_due_date(self, call_request_service):
        call_request_service._pending["call2"] = {
            "title": "タスク",
            "description": "",
            "priority": 3,
            "due_date": "2026-04-01T00:00:00Z",
        }
        route = respx.put("https://vikunja.test/api/v1/projects/1/tasks").mock(
            return_value=httpx.Response(201, json={"id": 88})
        )

        result = await call_request_service.confirm_and_create("call2", 1)
        assert result["task_created"] is True
        # Verify due_date was included in the request
        request = route.calls[0].request
        body = json.loads(request.content)
        assert body["due_date"] == "2026-04-01T00:00:00Z"
