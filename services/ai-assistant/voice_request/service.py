"""Voice Request — audio-to-task pipeline for work requests."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

import httpx

from config import settings

log = logging.getLogger(__name__)

ANALYSIS_PROMPT = """以下は業務依頼の音声の文字起こしです（個人情報はマスク済み）。
本日の日付: {today}

注意：この入力にはフィラーワード（えーと、あの、음、그など）、言い直し、背景ノイズマーカー（[咳]、[雑音]など）が含まれる可能性があります。
ノイズを無視し、本質的な内容のみを抽出してください。
数字や日付の言い間違いは文脈から正しい値を推測してください。

この依頼から以下を抽出してください：

1. **タスクタイトル**: 簡潔な依頼内容
2. **説明**: 詳細な依頼内容
3. **期限**: 言及されている場合、ISO 8601形式で出力。「今日中」「本日中」→本日の23:59、「明日まで」→翌日の17:00、「来週月曜」→次の月曜日。相対的な日付は本日の日付を基準に変換すること。
4. **優先度**: 1（低）〜4（緊急）
5. **不足情報**: 依頼を完了するために不足している情報

韓国語の依頼には韓国語で、日本語の依頼には日本語でタイトルと説明を出力してください。

JSON形式で出力：
{{
  "title": "...",
  "description": "...",
  "due_date": "... or null",
  "priority": 2,
  "missing_details": ["..."]
}}

文字起こし:
{transcript}
"""


class VoiceRequestService:
    """Process voice recordings into structured task requests."""

    def __init__(self) -> None:
        self._model: Any = None
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

    async def transcribe_audio(self, audio_bytes: bytes, lang: str = "ja-JP") -> str:
        """Transcribe audio via Google Speech-to-Text."""
        from google.cloud import speech

        client = speech.SpeechClient()
        audio = speech.RecognitionAudio(content=audio_bytes)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            language_code=lang,
            alternative_language_codes=["ko-KR", "en-US"],
            enable_automatic_punctuation=True,
        )
        response = client.recognize(config=config, audio=audio)
        return " ".join(
            r.alternatives[0].transcript for r in response.results
        )

    async def process_voice(
        self,
        audio_bytes: bytes,
        caller_email: str,
        target_email: str,
        lang: str = "ja-JP",
        masking_service: Any = None,
    ) -> dict:
        """Full pipeline: transcribe -> mask -> analyze -> return preview."""
        # Transcribe
        raw_transcript = await self.transcribe_audio(audio_bytes, lang)

        # PII mask
        masked_transcript = raw_transcript
        if masking_service:
            masked_transcript, _ = masking_service.mask_text(raw_transcript)

        # Gemini analysis
        analysis = await self._analyze(masked_transcript)

        request_id = str(uuid.uuid4())
        preview = {
            "request_id": request_id,
            "transcript_masked": masked_transcript,
            "caller_email": caller_email,
            "target_email": target_email,
            **analysis,
        }
        self._pending[request_id] = preview
        return preview

    async def _analyze(self, transcript: str) -> dict:
        from datetime import date
        model = self._ensure_model()
        prompt = ANALYSIS_PROMPT.format(transcript=transcript, today=date.today().isoformat())

        try:
            response = model.generate_content([{"role": "user", "parts": [{"text": prompt}]}])
            text = response.text.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            return json.loads(text)
        except Exception as e:
            log.error("Voice request analysis failed: %s", e)
            return {
                "title": "音声依頼",
                "description": transcript,
                "due_date": None,
                "priority": 2,
                "missing_details": [],
            }

    def get_pending(self, request_id: str) -> dict | None:
        return self._pending.get(request_id)

    async def confirm_and_create(self, request_id: str, project_id: int) -> dict:
        """Create Vikunja task from confirmed voice request."""
        preview = self._pending.pop(request_id, None)
        if not preview:
            return {"error": "Request not found"}

        task_data = {
            "title": preview.get("title", "音声依頼"),
            "description": preview.get("description", ""),
            "priority": preview.get("priority", 2),
        }
        if preview.get("due_date"):
            task_data["due_date"] = preview["due_date"]

        try:
            async with httpx.AsyncClient(
                base_url=settings.vikunja_url,
                headers={"Authorization": f"Bearer {settings.vikunja_token}"},
                timeout=30.0,
            ) as client:
                resp = await client.put(
                    f"/api/v1/projects/{project_id}/tasks",
                    json=task_data,
                )
                resp.raise_for_status()
                return {"task_created": True, "task_id": resp.json().get("id")}
        except Exception as e:
            log.error("Failed to create Vikunja task: %s", e)
            return {"error": str(e)}
