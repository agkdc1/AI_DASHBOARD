"""Call Request — originate call, record, transcribe, create task."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

import httpx

from config import settings

log = logging.getLogger(__name__)

CALL_ANALYSIS_PROMPT = """以下は業務通話の文字起こしです（個人情報はマスク済み）。
本日の日付: {today}

注意：この入力にはフィラーワード（えーと、あの、もしもし、음、그など）、言い直し、背景ノイズマーカー（[咳]、[雑音]、[電話の音]など）、電話回線の途切れが含まれる可能性があります。
ノイズを無視し、本質的な内容のみを抽出してください。
数字や日付の言い間違い・聞き返しは文脈から正しい値を推測してください。

この通話から以下を抽出してください：

1. **タスクタイトル**: 通話で決まった主要タスク。製品コード・注文番号・管理番号があれば必ずタイトルに含めること。
2. **説明**: 詳細内容
3. **期限**: 具体的な日時の言及がある場合のみISO 8601形式で出力。「今日中」「本日中」→本日の23:59、「明日まで」→翌日の17:00、「来週月曜」→次の月曜日、「다음 주 월요일」→次の月曜日、「다음 주 토요일」→次の土曜日。相対的な日付は本日の日付を基準に変換すること。「すぐに」「바로」「즉시」など、具体的な日付を伴わない緊急表現のみの場合はnullにすること。
4. **優先度**: 1（低）〜4（緊急）。不良品・欠陥品・出荷停止などの品質問題は4（緊急）にすること。
5. **決定事項**: 通話で合意した内容

韓国語の通話には韓国語で、日本語の通話には日本語でタイトルと説明と決定事項を出力してください。

JSON形式で出力：
{{
  "title": "...",
  "description": "...",
  "due_date": "... or null",
  "priority": 2,
  "decisions": ["..."]
}}

文字起こし:
{transcript}
"""


class CallRequestService:
    """Originate calls, record, transcribe, and create tasks."""

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

    async def initiate_call(self, caller_ext: str, target_ext: str) -> dict:
        """Originate a recorded call via faxapi."""
        call_id = str(uuid.uuid4())[:8]

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.faxapi_url}/calls/originate",
                json={
                    "caller_extension": caller_ext,
                    "target_extension": target_ext,
                    "call_id": call_id,
                },
            )
            if resp.status_code not in (200, 201):
                log.error("Call origination failed: %s", resp.text)
                return {"error": f"Origination failed: {resp.text}"}

        self._pending[call_id] = {
            "call_id": call_id,
            "caller_ext": caller_ext,
            "target_ext": target_ext,
            "status": "ringing",
        }
        return {"call_id": call_id, "status": "ringing"}

    async def get_call_status(self, call_id: str) -> dict:
        """Check call status via faxapi."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{settings.faxapi_url}/calls/{call_id}/status"
                )
                if resp.status_code == 200:
                    return resp.json()
        except Exception as e:
            log.warning("Status check failed for %s: %s", call_id, e)

        return self._pending.get(call_id, {"error": "Call not found"})

    async def analyze_recording(
        self,
        call_id: str,
        caller_email: str,
        target_email: str,
        masking_service: Any = None,
    ) -> dict:
        """Download recording, transcribe, mask, analyze."""
        # Download recording from faxapi
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.get(
                    f"{settings.faxapi_url}/calls/{call_id}/recording"
                )
                resp.raise_for_status()
                audio_bytes = resp.content
        except Exception as e:
            log.error("Recording download failed for %s: %s", call_id, e)
            return {"error": f"Recording not available: {e}"}

        # Transcribe
        raw_transcript = await self._transcribe(audio_bytes)

        # PII mask
        masked_transcript = raw_transcript
        if masking_service:
            masked_transcript, _ = masking_service.mask_text(raw_transcript)

        # Analyze
        analysis = await self._analyze(masked_transcript)

        preview = {
            "call_id": call_id,
            "transcript_masked": masked_transcript,
            "caller_email": caller_email,
            "target_email": target_email,
            **analysis,
        }
        self._pending[call_id] = preview
        return preview

    async def _transcribe(self, audio_bytes: bytes) -> str:
        from google.cloud import speech

        client = speech.SpeechClient()
        audio = speech.RecognitionAudio(content=audio_bytes)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=8000,  # Asterisk default
            language_code="ja-JP",
            alternative_language_codes=["ko-KR", "en-US"],
            enable_automatic_punctuation=True,
        )
        response = client.recognize(config=config, audio=audio)
        return " ".join(
            r.alternatives[0].transcript for r in response.results
        )

    async def _analyze(self, transcript: str) -> dict:
        from datetime import date
        model = self._ensure_model()
        prompt = CALL_ANALYSIS_PROMPT.format(transcript=transcript, today=date.today().isoformat())

        try:
            response = model.generate_content([{"role": "user", "parts": [{"text": prompt}]}])
            text = response.text.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            return json.loads(text)
        except Exception as e:
            log.error("Call analysis failed: %s", e)
            return {
                "title": "通話依頼",
                "description": transcript,
                "due_date": None,
                "priority": 2,
                "decisions": [],
            }

    async def confirm_and_create(self, call_id: str, project_id: int) -> dict:
        """Create Vikunja task from analyzed call."""
        preview = self._pending.pop(call_id, None)
        if not preview:
            return {"error": "Call not found"}

        task_data = {
            "title": preview.get("title", "通話依頼"),
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
