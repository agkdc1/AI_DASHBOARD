"""Weekly Evolution Loop — automated self-improvement cycle."""

from __future__ import annotations

import json
import logging
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import httpx

from config import settings

log = logging.getLogger(__name__)

ANALYSIS_PROMPT = """以下は今週のAIアシスタント利用ログ（マスク済み）です。

ログを分析して以下のレポートを作成してください：

1. **繰り返し発生した問題**: ユーザーが複数回試行した操作
2. **頻出パターン**: 同じ質問が繰り返された箇所
3. **SOPカバレッジの不足**: マニュアルに記載がなく回答できなかった領域
4. **改善提案**: 上記に基づく具体的な改善策

マークダウン形式で出力してください。

ログ:
{logs}
"""


class EvolutionService:
    """Weekly self-improvement: analyze logs, propose improvements, notify."""

    def __init__(self) -> None:
        self._model: Any = None

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

    async def run_weekly_analysis(self) -> dict:
        """Run the full weekly evolution cycle.

        1. Fetch masked logs from GCS
        2. Analyze with Gemini Pro
        3. Email proposal to superuser
        4. Create Vikunja review task

        Returns:
            {"proposal": str, "email_sent": bool, "task_created": bool}
        """
        # Step 1: Fetch logs
        logs = await self._fetch_weekly_logs()
        if not logs:
            return {"proposal": "ログがありません", "email_sent": False, "task_created": False}

        # Step 2: Analyze
        proposal = await self._analyze_logs(logs)

        # Step 3: Email
        email_sent = await self._send_email(proposal)

        # Step 4: Vikunja task
        task_created = await self._create_review_task(proposal)

        # Step 5: Archive
        await self._archive_proposal(proposal)

        return {
            "proposal": proposal,
            "email_sent": email_sent,
            "task_created": task_created,
        }

    async def _fetch_weekly_logs(self) -> str:
        """Fetch the past week's masked interaction logs from GCS."""
        try:
            from google.cloud import storage

            client = storage.Client(project=settings.gcp_project)
            bucket = client.bucket(settings.ai_logs_bucket)

            # List blobs from the past 7 days
            now = datetime.now(timezone.utc)
            week_ago = now - timedelta(days=7)
            logs = []

            for blob in bucket.list_blobs(prefix="interactions/"):
                if blob.time_created and blob.time_created >= week_ago:
                    content = blob.download_as_text()
                    logs.append(content)

            return "\n---\n".join(logs) if logs else ""
        except Exception as e:
            log.error("Failed to fetch weekly logs: %s", e)
            return ""

    async def _analyze_logs(self, logs: str) -> str:
        """Analyze logs with Gemini Pro and generate improvement proposal."""
        model = self._ensure_model()

        # Truncate logs if too long (Gemini context window)
        max_chars = 100_000
        if len(logs) > max_chars:
            logs = logs[:max_chars] + "\n... (truncated)"

        prompt = ANALYSIS_PROMPT.format(logs=logs)

        try:
            response = model.generate_content([{
                "role": "user",
                "parts": [{"text": prompt}],
            }])
            return response.text
        except Exception as e:
            log.error("Evolution analysis error: %s", e)
            return f"分析中にエラーが発生しました: {e}"

    async def _send_email(self, proposal: str) -> bool:
        """Email the improvement proposal to the superuser."""
        try:
            week_num = datetime.now(timezone.utc).isocalendar()[1]
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"AI改善提案 — 第{week_num}週"
            msg["From"] = "ai-assistant@your-domain.com"
            msg["To"] = settings.superuser_email

            msg.attach(MIMEText(proposal, "plain", "utf-8"))

            with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
                server.send_message(msg)

            log.info("Evolution proposal email sent to %s", settings.superuser_email)
            return True
        except Exception as e:
            log.warning("Failed to send evolution email: %s", e)
            return False

    async def _create_review_task(self, proposal: str) -> bool:
        """Create a Vikunja review task for the proposal."""
        try:
            week_num = datetime.now(timezone.utc).isocalendar()[1]
            async with httpx.AsyncClient(
                base_url=settings.vikunja_url,
                headers={"Authorization": f"Bearer {settings.vikunja_token}"},
                timeout=30.0,
            ) as client:
                # Create task in the first available project
                resp = await client.get("/api/v1/projects")
                resp.raise_for_status()
                projects = resp.json()
                if not projects:
                    log.warning("No Vikunja projects found for review task")
                    return False

                project_id = projects[0]["id"]
                task_data = {
                    "title": f"AI改善提案レビュー — 第{week_num}週",
                    "description": proposal[:10000],  # Vikunja limit
                }

                resp = await client.put(
                    f"/api/v1/projects/{project_id}/tasks",
                    json=task_data,
                )
                resp.raise_for_status()
                log.info("Created Vikunja review task in project %d", project_id)
                return True
        except Exception as e:
            log.warning("Failed to create review task: %s", e)
            return False

    async def _archive_proposal(self, proposal: str) -> None:
        """Archive the proposal in GCS."""
        try:
            from google.cloud import storage

            client = storage.Client(project=settings.gcp_project)
            bucket = client.bucket(settings.ai_logs_bucket)

            ts = datetime.now(timezone.utc).strftime("%Y-W%W")
            blob = bucket.blob(f"proposals/{ts}.md")
            blob.upload_from_string(proposal, content_type="text/markdown")
        except Exception as e:
            log.warning("Failed to archive proposal: %s", e)
