"""Tests for the Rakuten API Key Management service."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx

from helpers import make_sm_client


def _make_sm_response(data: dict) -> MagicMock:
    """Create a mock Secret Manager access_secret_version response."""
    resp = MagicMock()
    resp.payload.data = json.dumps(data).encode()
    return resp


class TestGetKeyStatus:
    async def test_with_renewed_at(self, rakuten_service):
        now = datetime.now(timezone.utc)
        renewed = (now - timedelta(days=50)).isoformat()
        rakuten_service._sm_client.access_secret_version.return_value = _make_sm_response({
            "renewed_at": renewed,
            "assigned_employees": ["Alice"],
        })

        status = await rakuten_service.get_key_status()
        assert status["renewed_at"] == renewed
        assert status["age_days"] == 50
        assert status["days_until_reminder"] == 30  # 80 - 50
        assert status["days_until_deadline"] == 40  # 90 - 50
        assert status["assigned_employees"] == ["Alice"]

    async def test_no_renewed_at(self, rakuten_service):
        rakuten_service._sm_client.access_secret_version.return_value = _make_sm_response({
            "assigned_employees": [],
        })
        status = await rakuten_service.get_key_status()
        assert status["renewed_at"] is None
        assert status["age_days"] is None

    async def test_error(self, rakuten_service):
        rakuten_service._sm_client.access_secret_version.side_effect = Exception("SM down")
        status = await rakuten_service.get_key_status()
        assert status["renewed_at"] is None


class TestSubmitNewKeys:
    @respx.mock
    async def test_full_cycle(self, rakuten_service):
        # Read existing secret (preserve assigned_employees)
        rakuten_service._sm_client.access_secret_version.side_effect = [
            _make_sm_response({"assigned_employees": ["Bob"]}),
            # For _update_inventree — read daemon-inventree secret
            _make_sm_response({
                "base_url": "https://portal.test",
                "api_token": "inv-token-123",
            }),
        ]

        # InvenTree PATCH calls
        respx.patch(url__regex=r".*/api/plugins/settings/ecommerce/.*").mock(
            return_value=httpx.Response(200, json={"value": "ok"})
        )
        # Vikunja: get tasks then mark done
        respx.get("https://vikunja.test/api/v1/projects/1/tasks").mock(
            return_value=httpx.Response(200, json=[
                {"id": 55, "title": "楽天APIキー更新リマインダー"},
            ])
        )
        respx.post("https://vikunja.test/api/v1/tasks/55").mock(
            return_value=httpx.Response(200, json={"id": 55, "done": True})
        )

        result = await rakuten_service.submit_new_keys("new-secret", "new-license", "tester")
        assert result["renewed_at"] is not None
        assert result["inventree_updated"] is True
        assert result["vikunja_task_closed"] is True
        # Verify SM write was called
        rakuten_service._sm_client.add_secret_version.assert_called()

    @respx.mock
    async def test_writes_to_gsm(self, rakuten_service):
        rakuten_service._sm_client.access_secret_version.side_effect = [
            _make_sm_response({}),
            Exception("No InvenTree creds"),
        ]
        result = await rakuten_service.submit_new_keys("s", "l", "user")
        assert result["renewed_at"] is not None
        rakuten_service._sm_client.add_secret_version.assert_called()


class TestUpdateAssignees:
    async def test_success(self, rakuten_service):
        rakuten_service._sm_client.access_secret_version.return_value = _make_sm_response({
            "service_secret": "x", "license_key": "y",
        })
        result = await rakuten_service.update_assignees(["Alice", "Bob"])
        assert result["assigned_employees"] == ["Alice", "Bob"]
        rakuten_service._sm_client.add_secret_version.assert_called()


class TestGetInstructions:
    def test_ja(self, rakuten_service):
        inst = rakuten_service.get_instructions("ja")
        assert "楽天" in inst["title"]
        assert len(inst["steps"]) == 6

    def test_ko(self, rakuten_service):
        inst = rakuten_service.get_instructions("ko")
        assert "라쿠텐" in inst["title"]

    def test_en(self, rakuten_service):
        inst = rakuten_service.get_instructions("en")
        assert "Rakuten" in inst["title"]

    def test_unknown_lang_fallback(self, rakuten_service):
        inst = rakuten_service.get_instructions("zh")
        assert "Rakuten" in inst["title"]  # Falls back to English


class TestUpdateInventree:
    @respx.mock
    async def test_success(self, rakuten_service):
        rakuten_service._sm_client.access_secret_version.return_value = _make_sm_response({
            "base_url": "https://portal.test",
            "api_token": "token123",
        })
        respx.patch(url__regex=r".*/api/plugins/settings/ecommerce/.*").mock(
            return_value=httpx.Response(200, json={"value": "ok"})
        )
        result = await rakuten_service._update_inventree("secret", "license")
        assert result is True

    async def test_no_creds(self, rakuten_service):
        rakuten_service._sm_client.access_secret_version.return_value = _make_sm_response({
            "base_url": "",
            "api_token": "",
        })
        result = await rakuten_service._update_inventree("s", "l")
        assert result is False

    async def test_api_error(self, rakuten_service):
        rakuten_service._sm_client.access_secret_version.side_effect = Exception("SM error")
        result = await rakuten_service._update_inventree("s", "l")
        assert result is False


class TestCloseVikunjaTask:
    @respx.mock
    async def test_found(self, rakuten_service):
        respx.get("https://vikunja.test/api/v1/projects/1/tasks").mock(
            return_value=httpx.Response(200, json=[
                {"id": 10, "title": "楽天APIキー更新"},
            ])
        )
        respx.post("https://vikunja.test/api/v1/tasks/10").mock(
            return_value=httpx.Response(200, json={"id": 10, "done": True})
        )
        result = await rakuten_service._close_vikunja_task()
        assert result is True

    @respx.mock
    async def test_not_found(self, rakuten_service):
        respx.get("https://vikunja.test/api/v1/projects/1/tasks").mock(
            return_value=httpx.Response(200, json=[
                {"id": 10, "title": "別のタスク"},
            ])
        )
        result = await rakuten_service._close_vikunja_task()
        assert result is False

    async def test_no_token(self):
        from rakuten.service import RakutenKeyService
        svc = RakutenKeyService()
        # vikunja_token is set to test value, but let's override
        with patch("rakuten.service.settings") as mock_settings:
            mock_settings.vikunja_token = ""
            mock_settings.vikunja_url = "https://vikunja.test"
            mock_settings.rakuten_vikunja_project_id = 1
            result = await svc._close_vikunja_task()
        assert result is False


class TestCheckAndRemind:
    @respx.mock
    async def test_too_early(self, rakuten_service):
        now = datetime.now(timezone.utc)
        renewed = (now - timedelta(days=30)).isoformat()
        rakuten_service._sm_client.access_secret_version.return_value = _make_sm_response({
            "renewed_at": renewed,
        })
        result = await rakuten_service.check_and_remind()
        assert result is None

    @respx.mock
    async def test_creates_task(self, rakuten_service):
        now = datetime.now(timezone.utc)
        renewed = (now - timedelta(days=85)).isoformat()
        rakuten_service._sm_client.access_secret_version.return_value = _make_sm_response({
            "renewed_at": renewed,
        })

        respx.get("https://vikunja.test/api/v1/projects/1/tasks").mock(
            return_value=httpx.Response(200, json=[])
        )
        respx.put("https://vikunja.test/api/v1/projects/1/tasks").mock(
            return_value=httpx.Response(201, json={"id": 100})
        )

        result = await rakuten_service.check_and_remind()
        assert result is not None
        assert result["task_created"] is True
        assert result["age_days"] == 85

    @respx.mock
    async def test_task_already_exists(self, rakuten_service):
        now = datetime.now(timezone.utc)
        renewed = (now - timedelta(days=85)).isoformat()
        rakuten_service._sm_client.access_secret_version.return_value = _make_sm_response({
            "renewed_at": renewed,
        })

        respx.get("https://vikunja.test/api/v1/projects/1/tasks").mock(
            return_value=httpx.Response(200, json=[
                {"id": 50, "title": "楽天APIキー更新リマインダー"},
            ])
        )
        result = await rakuten_service.check_and_remind()
        assert result is None

    async def test_no_age(self, rakuten_service):
        rakuten_service._sm_client.access_secret_version.return_value = _make_sm_response({})
        result = await rakuten_service.check_and_remind()
        assert result is None
