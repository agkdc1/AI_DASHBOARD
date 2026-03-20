"""Guide-Only Assistant Service — Gemini 2.0 Flash via Vertex AI."""

from __future__ import annotations

import logging
from typing import Any

from config import settings
from .prompts import GUIDE_SYSTEM_PROMPT, GUIDE_CONTEXT_PREAMBLE, NAVIGATE_SYSTEM_PROMPT

log = logging.getLogger(__name__)


class AssistantService:
    """Gemini-powered instructional assistant that only provides guidance."""

    def __init__(self) -> None:
        self._model: Any = None
        self._nav_model: Any = None
        self._context_cache: str | None = None

    def _ensure_model(self) -> Any:
        if self._model is None:
            from google.cloud import aiplatform
            from vertexai.generative_models import GenerativeModel

            aiplatform.init(
                project=settings.gcp_project,
                location=settings.gcp_location,
            )
            self._model = GenerativeModel(
                settings.gemini_model,
                system_instruction=GUIDE_SYSTEM_PROMPT,
            )
        return self._model

    async def chat(
        self,
        message: str,
        masked_screenshot_uri: str | None = None,
        conversation_history: list[dict] | None = None,
    ) -> str:
        """Send a message to the guide-only assistant.

        Args:
            message: User's text message (already PII-masked).
            masked_screenshot_uri: GCS URI of a redacted screenshot.
            conversation_history: Prior turns [{role, text}].

        Returns:
            Assistant's response text.
        """
        model = self._ensure_model()

        # Build content parts
        contents = []

        # Add SOP context if available
        if self._context_cache:
            preamble = GUIDE_CONTEXT_PREAMBLE.format(
                sop_context=self._context_cache
            )
            contents.append({"role": "user", "parts": [{"text": preamble}]})
            contents.append({
                "role": "model",
                "parts": [{"text": "理解しました。SOPの内容を参考にしてガイダンスを提供します。"}],
            })

        # Add conversation history
        if conversation_history:
            for turn in conversation_history:
                contents.append({
                    "role": turn["role"],
                    "parts": [{"text": turn["text"]}],
                })

        # Build current message parts
        parts: list[dict] = [{"text": message}]

        # Add screenshot if provided
        if masked_screenshot_uri:
            from vertexai.generative_models import Part as GeminiPart
            parts.append({
                "file_data": {
                    "mime_type": "image/png",
                    "file_uri": masked_screenshot_uri,
                },
            })

        contents.append({"role": "user", "parts": parts})

        try:
            response = model.generate_content(contents)
            return response.text
        except Exception as e:
            log.error("Gemini chat error: %s", e)
            return f"申し訳ありません。エラーが発生しました: {e}"

    def _ensure_nav_model(self) -> Any:
        if self._nav_model is None:
            from google.cloud import aiplatform
            from vertexai.generative_models import GenerativeModel

            aiplatform.init(
                project=settings.gcp_project,
                location=settings.gcp_location,
            )
            self._nav_model = GenerativeModel(
                settings.gemini_model,
                system_instruction=NAVIGATE_SYSTEM_PROMPT,
            )
        return self._nav_model

    async def navigate(
        self,
        message: str,
        screenshot_base64: str | None = None,
        dom_summary: str | None = None,
        current_url: str | None = None,
        conversation_history: list[dict] | None = None,
    ) -> dict:
        """Analyze current page state and return navigation actions.

        Args:
            message: User's question or request.
            screenshot_base64: Base64-encoded PNG of current browser view.
            dom_summary: Simplified DOM tree of the current page.
            current_url: The URL the user is currently on.
            conversation_history: Prior turns [{role, text}].

        Returns:
            Dict with response_text and actions list.
        """
        import base64
        import json as json_mod

        model = self._ensure_nav_model()

        contents = []

        # Add conversation history
        if conversation_history:
            for turn in conversation_history:
                contents.append({
                    "role": turn["role"],
                    "parts": [{"text": turn["text"]}],
                })

        # Build current message
        text_parts = [message]
        if current_url:
            text_parts.append(f"\n現在のURL: {current_url}")
        if dom_summary:
            text_parts.append(f"\nDOM構造:\n```\n{dom_summary[:8000]}\n```")

        parts: list[dict] = [{"text": "\n".join(text_parts)}]

        # Add screenshot if provided
        if screenshot_base64:
            parts.append({
                "inline_data": {
                    "mime_type": "image/png",
                    "data": screenshot_base64,
                },
            })

        contents.append({"role": "user", "parts": parts})

        try:
            response = model.generate_content(contents)
            response_text = response.text.strip()

            # Parse JSON response
            # Strip markdown code fences if present
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                lines = [l for l in lines if not l.startswith("```")]
                response_text = "\n".join(lines)

            result = json_mod.loads(response_text)
            return {
                "response_text": result.get("response_text", ""),
                "actions": result.get("actions", []),
            }
        except json_mod.JSONDecodeError:
            # AI returned non-JSON — treat as text-only response
            return {
                "response_text": response.text if 'response' in dir() else "解析エラー",
                "actions": [],
            }
        except Exception as e:
            log.error("Navigation error: %s", e)
            return {
                "response_text": f"エラーが発生しました: {e}",
                "actions": [],
            }

    async def load_sop_context(self, sop_text: str) -> None:
        """Load SOP context for the assistant."""
        self._context_cache = sop_text
        log.info("Loaded SOP context (%d chars)", len(sop_text))

    async def compare_screenshots(
        self,
        before_uri: str,
        after_uri: str,
        expected_action: str,
    ) -> str:
        """Compare two screenshots to verify a state change.

        Args:
            before_uri: GCS URI of the before screenshot.
            after_uri: GCS URI of the after screenshot.
            expected_action: Description of what the user was supposed to do.

        Returns:
            Verification result text.
        """
        model = self._ensure_model()

        prompt = (
            f"ユーザーは「{expected_action}」を実行しました。\n"
            f"操作前と操作後のスクリーンショットを比較して、"
            f"操作が正しく完了したか確認してください。\n"
            f"変化があった箇所を具体的に指摘してください。"
        )

        contents = [{
            "role": "user",
            "parts": [
                {"text": prompt},
                {"file_data": {"mime_type": "image/png", "file_uri": before_uri}},
                {"file_data": {"mime_type": "image/png", "file_uri": after_uri}},
            ],
        }]

        try:
            response = model.generate_content(contents)
            return response.text
        except Exception as e:
            log.error("Screenshot comparison error: %s", e)
            return f"比較中にエラーが発生しました: {e}"
