"""AI-powered Vikunja Task Manager — natural language task operations."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from config import settings

log = logging.getLogger(__name__)

TASK_SYSTEM_PROMPT = """あなたはVikunjaタスク管理のAIアシスタントです。

ユーザーの自然言語リクエストを解析し、以下の構造化されたアクションに変換してください。
韓国語の入力には韓国語で、日本語の入力には日本語でタスクのタイトルと説明を出力してください。

注意：ユーザー入力にはタイプミス、変換ミス（在こ→在庫、発装→発送）、カジュアルな表現、不完全な文が含まれる場合があります。
入力のノイズを補正し、正しい意図を推測してタスクを構造化してください。

## 出力形式（JSON）
{
  "action": "query" | "create" | "update" | "delete",
  "query_text": "検索テキスト（queryの場合）",
  "task": {
    "title": "タスクタイトル",
    "description": "説明",
    "project_id": null,
    "priority": 2,
    "due_date": "2026-03-01T00:00:00Z",
    "labels": [{"title": "ラベル名"}],
    "done": false
  },
  "task_id": null
}

## 優先度の基準（1〜4の整数）
- 1（低）: 特に急がない通常タスク
- 2（中）: 一般的な業務タスク（デフォルト）
- 3（高）: 期限が近い、または重要なタスク
- 4（緊急）: 即日対応が必要

## ルール
- queryアクション: Vikunja APIを検索し結果を返す
- createアクション: タスク情報を構造化し、ユーザー確認を必ず求める
- updateアクション: task_idとフィールド変更のみ
- deleteアクション: task_idが必要、ユーザー確認を必ず求める
- 不明な情報は null にして、ユーザーに確認を求める
- priorityは必ず1〜4の整数で設定（省略時は2）
- due_dateは言及されている場合、ISO 8601形式で出力
- 応答は必ずJSON形式で出力してください
"""


class TaskManagerService:
    """Natural language interface to Vikunja task management."""

    def __init__(self) -> None:
        self._model: Any = None
        self._http = httpx.AsyncClient(
            base_url=settings.vikunja_url,
            headers={"Authorization": f"Bearer {settings.vikunja_token}"},
            timeout=30.0,
        )

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
                system_instruction=TASK_SYSTEM_PROMPT,
            )
        return self._model

    async def process_request(self, user_message: str) -> dict:
        """Parse natural language and return structured task action.

        Returns:
            {
                "action": str,
                "parsed": dict (Gemini's structured output),
                "preview": str (human-readable preview),
                "requires_confirmation": bool,
            }
        """
        model = self._ensure_model()

        try:
            response = model.generate_content([{"role": "user", "parts": [{"text": user_message}]}])
            text = response.text.strip()

            # Extract JSON from response (handle markdown code blocks)
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            parsed = json.loads(text)
        except (json.JSONDecodeError, IndexError) as e:
            log.warning("Failed to parse Gemini task response: %s", e)
            return {
                "action": "error",
                "parsed": {},
                "preview": f"リクエストを解析できませんでした: {user_message}",
                "requires_confirmation": False,
            }

        action = parsed.get("action", "query")
        preview = self._build_preview(parsed)
        requires_confirmation = action in ("create", "update", "delete")

        return {
            "action": action,
            "parsed": parsed,
            "preview": preview,
            "requires_confirmation": requires_confirmation,
        }

    async def execute_action(self, parsed: dict) -> dict:
        """Execute a confirmed task action against the Vikunja API."""
        action = parsed.get("action", "query")

        if action == "query":
            return await self._query_tasks(parsed.get("query_text", ""))
        elif action == "create":
            return await self._create_task(parsed.get("task", {}))
        elif action == "update":
            return await self._update_task(
                parsed.get("task_id"),
                parsed.get("task", {}),
            )
        elif action == "delete":
            return await self._delete_task(parsed.get("task_id"))
        else:
            return {"error": f"Unknown action: {action}"}

    async def _query_tasks(self, query: str) -> dict:
        """Search tasks in Vikunja."""
        try:
            resp = await self._http.get(
                "/api/v1/tasks/all",
                params={"s": query, "per_page": 20},
            )
            resp.raise_for_status()
            tasks = resp.json()
            return {"tasks": tasks, "count": len(tasks)}
        except Exception as e:
            return {"error": str(e)}

    async def _create_task(self, task_data: dict) -> dict:
        """Create a task in Vikunja."""
        project_id = task_data.pop("project_id", None)
        if not project_id:
            return {"error": "project_id is required to create a task"}

        try:
            resp = await self._http.put(
                f"/api/v1/projects/{project_id}/tasks",
                json=task_data,
            )
            resp.raise_for_status()
            return {"created": resp.json()}
        except Exception as e:
            return {"error": str(e)}

    async def _update_task(self, task_id: int | None, updates: dict) -> dict:
        """Update a task in Vikunja."""
        if not task_id:
            return {"error": "task_id is required"}

        try:
            resp = await self._http.post(
                f"/api/v1/tasks/{task_id}",
                json=updates,
            )
            resp.raise_for_status()
            return {"updated": resp.json()}
        except Exception as e:
            return {"error": str(e)}

    async def _delete_task(self, task_id: int | None) -> dict:
        """Delete a task in Vikunja."""
        if not task_id:
            return {"error": "task_id is required"}

        try:
            resp = await self._http.delete(f"/api/v1/tasks/{task_id}")
            resp.raise_for_status()
            return {"deleted": True, "task_id": task_id}
        except Exception as e:
            return {"error": str(e)}

    def _build_preview(self, parsed: dict) -> str:
        """Build a human-readable preview of the action."""
        action = parsed.get("action", "query")
        task = parsed.get("task", {})

        if action == "query":
            return f"検索: {parsed.get('query_text', '')}"
        elif action == "create":
            title = task.get("title", "無題")
            p = task.get("priority") or 2
            priority = {1: "低", 2: "中", 3: "高", 4: "緊急"}.get(p, "中")
            due = task.get("due_date", "なし")
            return f"タスク作成:\n  タイトル: {title}\n  優先度: {priority}\n  期限: {due}"
        elif action == "update":
            tid = parsed.get("task_id", "?")
            changes = ", ".join(f"{k}={v}" for k, v in task.items() if v is not None)
            return f"タスク #{tid} 更新: {changes}"
        elif action == "delete":
            return f"タスク #{parsed.get('task_id', '?')} を削除"
        return str(parsed)
