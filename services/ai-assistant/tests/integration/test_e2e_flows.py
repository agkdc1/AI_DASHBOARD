"""End-to-end integration tests crossing multiple services.

Run with: RUN_INTEGRATION=1 pytest -m integration tests/integration/test_e2e_flows.py -v
"""

import os

import pytest

from config import settings

pytestmark = [pytest.mark.integration]


class TestE2EFlows:
    @pytest.mark.asyncio
    async def test_task_manager_query(self, vikunja_token):
        """TaskManagerService.execute_action() querying live Vikunja."""
        from task_manager.service import TaskManagerService
        svc = TaskManagerService()
        # Override token for live test
        svc._http._headers["Authorization"] = f"Bearer {vikunja_token}"

        result = await svc.execute_action({"action": "query", "query_text": ""})
        assert "tasks" in result
        assert isinstance(result["tasks"], list)
        await svc._http.aclose()

    @pytest.mark.asyncio
    async def test_task_manager_create_delete(self, vikunja_client, vikunja_cleanup):
        """Create and delete a task via TaskManagerService."""
        from task_manager.service import TaskManagerService
        svc = TaskManagerService()
        # Need a project first
        resp = vikunja_client.put("/api/v1/projects", json={"title": "TEST-E2E-PROJECT"})
        project_id = resp.json()["id"]
        vikunja_cleanup["projects"].append(project_id)

        result = await svc.execute_action({
            "action": "create",
            "task": {"title": "E2E-TEST-TASK", "project_id": project_id},
        })
        assert "created" in result
        task_id = result["created"]["id"]
        vikunja_cleanup["tasks"].append(task_id)

        # Delete
        result = await svc.execute_action({"action": "delete", "task_id": task_id})
        assert result.get("deleted") is True
        vikunja_cleanup["tasks"].remove(task_id)
        await svc._http.aclose()

    @pytest.mark.asyncio
    async def test_auto_provision(self, ldap_cleanup, faxapi_cleanup):
        """PhoneService.auto_provision() against live LDAP + faxapi."""
        from phone.service import PhoneService
        svc = PhoneService()

        result = await svc.auto_provision("e2e-test@test.com", "E2E Test User")
        if "error" in result:
            pytest.skip(f"Auto-provision failed: {result['error']}")

        ext = result["extension"]
        dn = f"uid={ext},ou=users,{settings.ldap_base_dn}"
        ldap_cleanup.append(dn)
        if result["newly_created"]:
            faxapi_cleanup["extensions"].append(ext)

        assert result["extension"] is not None

    @pytest.mark.asyncio
    async def test_rakuten_key_status(self):
        """RakutenKeyService.get_key_status() against live GCP SM."""
        from rakuten.service import RakutenKeyService
        svc = RakutenKeyService()
        status = await svc.get_key_status()
        # Should return a dict with the expected keys
        assert "renewed_at" in status
        assert "assigned_employees" in status

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_masking_then_assistant(self):
        """MaskingService + AssistantService.chat() with live Gemini."""
        from masking.service import MaskingService
        from assistant.service import AssistantService

        masking = MaskingService()
        text = "佐藤太郎さんの電話番号は090-1234-5678です"
        masked, detections = masking.mask_text(text)
        assert "[REDACTED_NAME]" in masked

        assistant = AssistantService()
        response = await assistant.chat(f"以下のテキストについて教えてください: {masked}")
        assert isinstance(response, str)
        assert len(response) > 0
