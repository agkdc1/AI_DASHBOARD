"""Tests for the Guide-Only Assistant service."""

from unittest.mock import MagicMock, patch

import pytest

from helpers import make_gemini_model, make_gemini_response


class TestAssistantChat:
    async def test_basic_message(self, assistant_service):
        result = await assistant_service.chat("インベントリの使い方を教えて")
        assert isinstance(result, str)
        assert len(result) > 0

    async def test_with_sop_context(self, assistant_service):
        await assistant_service.load_sop_context("テストSOPコンテキスト")
        assert assistant_service._context_cache == "テストSOPコンテキスト"

        result = await assistant_service.chat("SOPに基づいて説明して")
        # Model was called with contents that include SOP preamble
        call_args = assistant_service._model.generate_content.call_args
        contents = call_args[0][0]
        assert len(contents) >= 3  # SOP user, SOP model ack, actual user msg

    async def test_with_conversation_history(self, assistant_service):
        history = [
            {"role": "user", "text": "前の質問"},
            {"role": "model", "text": "前の回答"},
        ]
        result = await assistant_service.chat("続きを教えて", conversation_history=history)
        call_args = assistant_service._model.generate_content.call_args
        contents = call_args[0][0]
        # History turns + current message
        assert len(contents) >= 3

    @pytest.mark.timeout(60)
    async def test_with_screenshot_uri(self, assistant_service):
        # Mock the lazy vertexai import to avoid slow import under coverage
        mock_vertexai = MagicMock()
        with patch.dict("sys.modules", {
            "vertexai": mock_vertexai,
            "vertexai.generative_models": mock_vertexai.generative_models,
        }):
            result = await assistant_service.chat(
                "この画面は何ですか",
                masked_screenshot_uri="gs://bucket/screenshot.png",
            )
        call_args = assistant_service._model.generate_content.call_args
        contents = call_args[0][0]
        last_msg = contents[-1]
        assert len(last_msg["parts"]) >= 2  # text + file_data

    async def test_gemini_error_fallback(self, assistant_service):
        assistant_service._model.generate_content.side_effect = Exception("API error")
        result = await assistant_service.chat("テスト")
        assert "エラー" in result

    async def test_empty_history(self, assistant_service):
        result = await assistant_service.chat("テスト", conversation_history=[])
        assert isinstance(result, str)


class TestAssistantLoadSop:
    async def test_load_sop(self, assistant_service):
        await assistant_service.load_sop_context("SOP内容")
        assert assistant_service._context_cache == "SOP内容"


class TestCompareScreenshots:
    async def test_normal_comparison(self, assistant_service):
        result = await assistant_service.compare_screenshots(
            before_uri="gs://bucket/before.png",
            after_uri="gs://bucket/after.png",
            expected_action="ボタンをクリック",
        )
        assert isinstance(result, str)

    async def test_comparison_error(self, assistant_service):
        assistant_service._model.generate_content.side_effect = Exception("Model error")
        result = await assistant_service.compare_screenshots(
            "gs://a", "gs://b", "test"
        )
        assert "エラー" in result


class TestEnsureModel:
    async def test_lazy_init(self):
        from assistant.service import AssistantService
        svc = AssistantService()
        assert svc._model is None
        # After injecting, ensure it reuses
        svc._model = make_gemini_model()
        model = svc._ensure_model()
        assert model is svc._model

    async def test_reuse_existing(self, assistant_service):
        model1 = assistant_service._ensure_model()
        model2 = assistant_service._ensure_model()
        assert model1 is model2
