"""Meeting Mode — Audio-to-task pipeline with human approval gate."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from config import settings

log = logging.getLogger(__name__)

EXTRACT_PROMPT = """以下は会議の文字起こしです（個人情報はマスク済み）。

注意：この入力にはフィラーワード（えーと、あの、まぁ、음、그など）、言い直し、相槌、背景ノイズマーカー（[咳]、[雑音]、[一時停止]など）が含まれる可能性があります。
ノイズを無視し、本質的な内容のみを抽出してください。
不完全な発言は文脈から補完してください。

この議事録から以下を抽出してください：

1. **アクションアイテム**: 誰が何をいつまでにやるか
2. **決定事項**: 会議で決まったこと
3. **ドキュメント更新**: SOPやマニュアルに反映すべき変更

重要: 議事録と同じ言語で出力してください。韓国語の議事録には韓国語で、日本語の議事録には日本語で回答してください。

JSON形式で出力してください：
{{
  "action_items": [
    {{
      "title": "タスクタイトル",
      "assignee": "担当者名またはnull",
      "due_date": "期限またはnull",
      "description": "詳細"
    }}
  ],
  "decisions": [
    {{"summary": "決定事項の要約"}}
  ],
  "doc_updates": [
    {{"target_doc": "対象ドキュメント", "change": "変更内容"}}
  ]
}}

議事録:
{transcript}
"""


class MeetingService:
    """Audio-to-task pipeline: transcribe, mask, extract, approve, sync."""

    def __init__(self) -> None:
        self._model: Any = None
        # In-memory store for pending approval dashboards
        self._pending: dict[str, dict] = {}

    def _ensure_model(self) -> Any:
        if self._model is None:
            from google.cloud import aiplatform
            from vertexai.generative_models import GenerativeModel

            aiplatform.init(
                project=settings.gcp_project,
                location=settings.gcp_location,
            )
            self._model = GenerativeModel(settings.gemini_pro_model)
        return self._model

    async def transcribe_audio(self, audio_bytes: bytes, language: str = "ja-JP") -> str:
        """Transcribe audio to text using Google Cloud Speech-to-Text."""
        try:
            from google.cloud import speech

            client = speech.SpeechClient()
            audio = speech.RecognitionAudio(content=audio_bytes)
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=16000,
                language_code=language,
                alternative_language_codes=["ko-KR", "en-US"],
                enable_automatic_punctuation=True,
            )

            response = client.recognize(config=config, audio=audio)
            transcript = " ".join(
                result.alternatives[0].transcript
                for result in response.results
            )
            return transcript
        except Exception as e:
            log.error("Speech-to-text error: %s", e)
            raise

    async def process_meeting(
        self,
        audio_bytes: bytes,
        masking_service: Any,
    ) -> dict:
        """Full pipeline: transcribe → mask → extract → return approval dashboard.

        Returns:
            {
                "dashboard_id": str,
                "transcript_masked": str,
                "action_items": [...],
                "decisions": [...],
                "doc_updates": [...],
            }
        """
        # Step 1: Transcribe
        raw_transcript = await self.transcribe_audio(audio_bytes)

        # Step 2: Mask PII
        masked_transcript, detections = masking_service.mask_text(raw_transcript)

        # Step 3: Extract action items via Gemini
        extracted = await self._extract_items(masked_transcript)

        # Step 4: Create approval dashboard
        dashboard_id = str(uuid.uuid4())
        dashboard = {
            "dashboard_id": dashboard_id,
            "transcript_masked": masked_transcript,
            "action_items": extracted.get("action_items", []),
            "decisions": extracted.get("decisions", []),
            "doc_updates": extracted.get("doc_updates", []),
            "pii_detections": len(detections),
        }

        # Store for later approval
        self._pending[dashboard_id] = dashboard

        return dashboard

    async def _extract_items(self, masked_transcript: str) -> dict:
        """Use Gemini to extract action items and decisions from transcript."""
        model = self._ensure_model()

        prompt = EXTRACT_PROMPT.format(transcript=masked_transcript)

        try:
            response = model.generate_content([{
                "role": "user",
                "parts": [{"text": prompt}],
            }])
            text = response.text.strip()

            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            return json.loads(text)
        except Exception as e:
            log.error("Meeting extraction error: %s", e)
            return {"action_items": [], "decisions": [], "doc_updates": []}

    def get_dashboard(self, dashboard_id: str) -> dict | None:
        """Get a pending approval dashboard."""
        return self._pending.get(dashboard_id)

    async def approve_items(
        self,
        dashboard_id: str,
        approved_action_indices: list[int],
        approved_doc_indices: list[int],
        project_id: int,
    ) -> dict:
        """Approve selected items and sync to Vikunja.

        Args:
            dashboard_id: The dashboard ID from process_meeting.
            approved_action_indices: Indices of approved action items.
            approved_doc_indices: Indices of approved doc updates.
            project_id: Vikunja project to create tasks in.

        Returns:
            {"tasks_created": int, "docs_queued": int}
        """
        dashboard = self._pending.get(dashboard_id)
        if not dashboard:
            return {"error": "Dashboard not found"}

        import httpx

        tasks_created = 0
        async with httpx.AsyncClient(
            base_url=settings.vikunja_url,
            headers={"Authorization": f"Bearer {settings.vikunja_token}"},
            timeout=30.0,
        ) as client:
            for idx in approved_action_indices:
                if idx < len(dashboard["action_items"]):
                    item = dashboard["action_items"][idx]
                    task_data = {
                        "title": item.get("title", "会議アクションアイテム"),
                        "description": item.get("description", ""),
                    }
                    if item.get("due_date"):
                        task_data["due_date"] = item["due_date"]

                    try:
                        resp = await client.put(
                            f"/api/v1/projects/{project_id}/tasks",
                            json=task_data,
                        )
                        resp.raise_for_status()
                        tasks_created += 1
                    except Exception as e:
                        log.error("Failed to create task: %s", e)

        # Remove from pending
        del self._pending[dashboard_id]

        return {
            "tasks_created": tasks_created,
            "docs_queued": len(approved_doc_indices),
        }
