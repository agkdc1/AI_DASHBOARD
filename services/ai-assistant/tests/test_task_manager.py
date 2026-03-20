"""Tests for the AI-powered Task Manager service."""

import json
from unittest.mock import MagicMock

import httpx
import pytest
import respx

from helpers import make_gemini_model, make_gemini_response


class TestProcessRequest:
    async def test_create_action(self, task_manager_service):
        result = await task_manager_service.process_request("タスクを作成して")
        assert result["action"] == "create"
        assert result["requires_confirmation"] is True
        assert "parsed" in result
        assert "preview" in result

    async def test_query_action(self, task_manager_service):
        task_manager_service._model = make_gemini_model(
            '{"action":"query","query_text":"テスト"}'
        )
        result = await task_manager_service.process_request("タスクを検索して")
        assert result["action"] == "query"
        assert result["requires_confirmation"] is False

    async def test_update_action(self, task_manager_service):
        task_manager_service._model = make_gemini_model(
            '{"action":"update","task_id":42,"task":{"done":true}}'
        )
        result = await task_manager_service.process_request("タスク42を完了にして")
        assert result["action"] == "update"
        assert result["requires_confirmation"] is True

    async def test_delete_action(self, task_manager_service):
        task_manager_service._model = make_gemini_model(
            '{"action":"delete","task_id":42}'
        )
        result = await task_manager_service.process_request("タスク42を削除して")
        assert result["action"] == "delete"

    async def test_invalid_json(self, task_manager_service):
        task_manager_service._model = make_gemini_model("これはJSONではありません")
        result = await task_manager_service.process_request("あいまいなリクエスト")
        assert result["action"] == "error"
        assert result["requires_confirmation"] is False

    async def test_json_in_code_block(self, task_manager_service):
        task_manager_service._model = make_gemini_model(
            '```json\n{"action":"query","query_text":"テスト"}\n```'
        )
        result = await task_manager_service.process_request("タスク検索")
        assert result["action"] == "query"


class TestExecuteAction:
    @respx.mock
    async def test_query_tasks(self, task_manager_service):
        route = respx.get("https://vikunja.test/api/v1/tasks/all").mock(
            return_value=httpx.Response(200, json=[{"id": 1, "title": "Test"}])
        )
        result = await task_manager_service.execute_action(
            {"action": "query", "query_text": "test"}
        )
        assert "tasks" in result
        assert result["count"] == 1

    @respx.mock
    async def test_create_task(self, task_manager_service):
        route = respx.put("https://vikunja.test/api/v1/projects/1/tasks").mock(
            return_value=httpx.Response(201, json={"id": 99, "title": "新タスク"})
        )
        result = await task_manager_service.execute_action(
            {"action": "create", "task": {"title": "新タスク", "project_id": 1}}
        )
        assert "created" in result
        assert result["created"]["id"] == 99

    @respx.mock
    async def test_update_task(self, task_manager_service):
        route = respx.post("https://vikunja.test/api/v1/tasks/42").mock(
            return_value=httpx.Response(200, json={"id": 42, "done": True})
        )
        result = await task_manager_service.execute_action(
            {"action": "update", "task_id": 42, "task": {"done": True}}
        )
        assert "updated" in result

    @respx.mock
    async def test_delete_task(self, task_manager_service):
        route = respx.delete("https://vikunja.test/api/v1/tasks/42").mock(
            return_value=httpx.Response(204)
        )
        result = await task_manager_service.execute_action(
            {"action": "delete", "task_id": 42}
        )
        assert result["deleted"] is True

    async def test_create_missing_project_id(self, task_manager_service):
        result = await task_manager_service.execute_action(
            {"action": "create", "task": {"title": "No project"}}
        )
        assert "error" in result

    async def test_update_missing_task_id(self, task_manager_service):
        result = await task_manager_service.execute_action(
            {"action": "update", "task_id": None, "task": {"done": True}}
        )
        assert "error" in result

    async def test_delete_missing_task_id(self, task_manager_service):
        result = await task_manager_service.execute_action(
            {"action": "delete", "task_id": None}
        )
        assert "error" in result

    async def test_unknown_action(self, task_manager_service):
        result = await task_manager_service.execute_action({"action": "fly"})
        assert "error" in result


class TestBuildPreview:
    def test_query_preview(self, task_manager_service):
        preview = task_manager_service._build_preview(
            {"action": "query", "query_text": "テスト検索"}
        )
        assert "検索" in preview
        assert "テスト検索" in preview

    def test_create_preview(self, task_manager_service):
        preview = task_manager_service._build_preview(
            {"action": "create", "task": {"title": "新規タスク", "priority": 2}}
        )
        assert "タスク作成" in preview
        assert "新規タスク" in preview
        assert "中" in preview  # priority 2 = 中

    def test_update_preview(self, task_manager_service):
        preview = task_manager_service._build_preview(
            {"action": "update", "task_id": 5, "task": {"done": True}}
        )
        assert "#5" in preview

    def test_delete_preview(self, task_manager_service):
        preview = task_manager_service._build_preview(
            {"action": "delete", "task_id": 10}
        )
        assert "#10" in preview
        assert "削除" in preview
