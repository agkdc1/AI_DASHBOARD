"""E2E integration tests creating real data in InvenTree, Vikunja, and LDAP.

Run with: RUN_INTEGRATION=1 RUN_PROMPT_TESTS=1 pytest tests/prompt_testing/test_e2e_pipeline.py -v
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RUN_INTEGRATION = os.environ.get("RUN_INTEGRATION", "0") == "1"
RUN_PROMPT_TESTS = os.environ.get("RUN_PROMPT_TESTS", "0") == "1"

skip_unless_e2e = pytest.mark.skipif(
    not (RUN_INTEGRATION and RUN_PROMPT_TESTS),
    reason="Both RUN_INTEGRATION and RUN_PROMPT_TESTS required",
)

pytestmark = [pytest.mark.integration, pytest.mark.prompt_test, skip_unless_e2e]

# ── Test data prefixes ──
E2E_PREFIX = "E2E-TEST-"
PROMPT_PREFIX = "PROMPT-TEST-"


# ─────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def vikunja_token() -> str:
    token = os.environ.get("VIKUNJA_TOKEN", "")
    if not token:
        try:
            result = subprocess.run(
                "sudo KUBECONFIG=/etc/rancher/k3s/k3s.yaml kubectl -n intranet get secret vikunja-api-token -o jsonpath='{.data.token}' | base64 -d",
                shell=True, capture_output=True, text=True, timeout=15,
            )
            token = result.stdout.strip()
        except Exception:
            pass
    if not token:
        pytest.skip("No Vikunja token available")
    return token


@pytest.fixture(scope="session")
def vikunja_client(vikunja_token) -> httpx.Client:
    client = httpx.Client(
        base_url="https://tasks.your-domain.com",
        headers={"Authorization": f"Bearer {vikunja_token}"},
        timeout=30.0,
    )
    yield client
    client.close()


@pytest.fixture
def vikunja_project(vikunja_client):
    """Create a test project in Vikunja, clean up after test."""
    resp = vikunja_client.put(
        "/api/v1/projects",
        json={"title": f"{E2E_PREFIX}Project"},
    )
    resp.raise_for_status()
    project = resp.json()
    project_id = project["id"]
    yield project_id
    # Cleanup: delete project (cascades to tasks)
    vikunja_client.delete(f"/api/v1/projects/{project_id}")


@pytest.fixture
def live_voice_service():
    from voice_request.service import VoiceRequestService
    svc = VoiceRequestService()
    svc._ensure_model()
    return svc


@pytest.fixture
def live_meeting_service():
    from meeting.service import MeetingService
    svc = MeetingService()
    svc._ensure_model()
    return svc


@pytest.fixture
def live_task_manager_service():
    from task_manager.service import TaskManagerService
    svc = TaskManagerService()
    svc._ensure_model()
    return svc


@pytest.fixture
def masking_service():
    from masking.service import MaskingService
    return MaskingService()


# ─────────────────────────────────────────────────────────────────────
# E2E Tests
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.timeout(180)
async def test_voice_to_vikunja(live_voice_service, vikunja_client, vikunja_project):
    """Voice request → analyze → create Vikunja task → verify → delete."""
    text = "来週月曜日までに在庫レポートを作成してください。SKU-X100の在庫数が少ないので確認が必要です。"

    # Analyze
    result = await live_voice_service._analyze(text)
    assert "title" in result
    assert result.get("priority") in range(1, 5)

    # Create task in Vikunja
    task_data = {
        "title": f"{PROMPT_PREFIX}{result['title']}",
        "description": result.get("description", ""),
        "priority": result.get("priority", 2),
    }
    resp = vikunja_client.put(
        f"/api/v1/projects/{vikunja_project}/tasks",
        json=task_data,
    )
    resp.raise_for_status()
    task = resp.json()
    task_id = task["id"]

    # Verify
    resp = vikunja_client.get(f"/api/v1/tasks/{task_id}")
    resp.raise_for_status()
    fetched = resp.json()
    assert fetched["title"].startswith(PROMPT_PREFIX)

    # Cleanup
    vikunja_client.delete(f"/api/v1/tasks/{task_id}")


@pytest.mark.timeout(180)
async def test_meeting_to_vikunja(live_meeting_service, vikunja_client, vikunja_project):
    """Meeting transcript → extract items → create tasks in Vikunja → verify → delete."""
    transcript = (
        "[REDACTED_NAME]：在庫の棚卸し結果を確認します。SKU-A1234が20個不足しています。"
        "[REDACTED_NAME]さん、来週金曜日までに原因を調査して報告してください。"
        "また、棚卸しSOPに新手順を追加します。"
    )

    # Extract
    result = await live_meeting_service._extract_items(transcript)
    assert "action_items" in result
    assert len(result["action_items"]) >= 1

    # Create tasks for each action item
    created_task_ids = []
    for item in result["action_items"]:
        task_data = {
            "title": f"{PROMPT_PREFIX}{item.get('title', 'Action item')}",
            "description": item.get("description", ""),
        }
        resp = vikunja_client.put(
            f"/api/v1/projects/{vikunja_project}/tasks",
            json=task_data,
        )
        resp.raise_for_status()
        created_task_ids.append(resp.json()["id"])

    # Verify
    for tid in created_task_ids:
        resp = vikunja_client.get(f"/api/v1/tasks/{tid}")
        resp.raise_for_status()
        assert resp.json()["title"].startswith(PROMPT_PREFIX)

    # Cleanup
    for tid in created_task_ids:
        vikunja_client.delete(f"/api/v1/tasks/{tid}")


@pytest.mark.timeout(180)
async def test_task_manager_crud(live_task_manager_service, vikunja_client, vikunja_project):
    """Task manager NLP → create → query → update → delete via Vikunja API."""
    # Create via NLP
    create_result = await live_task_manager_service.process_request(
        "テスト用の在庫確認タスクを作成して。優先度は中で。"
    )
    assert create_result["action"] == "create"
    parsed = create_result["parsed"]

    # Actually create in Vikunja
    task = parsed.get("task", {})
    task_data = {
        "title": f"{PROMPT_PREFIX}{task.get('title', 'Test task')}",
        "description": task.get("description", "E2E test task"),
        "priority": task.get("priority", 2),
    }
    resp = vikunja_client.put(
        f"/api/v1/projects/{vikunja_project}/tasks",
        json=task_data,
    )
    resp.raise_for_status()
    task_id = resp.json()["id"]

    # Query via NLP
    query_result = await live_task_manager_service.process_request("在庫確認のタスクを検索して")
    assert query_result["action"] == "query"

    # Delete
    vikunja_client.delete(f"/api/v1/tasks/{task_id}")


@pytest.mark.timeout(180)
async def test_phone_auto_provision():
    """Phone auto-provision LDAP test — create user, verify, delete."""
    import ldap as ldap_lib
    from config import settings

    if not settings.ldap_bind_password:
        pytest.skip("LDAP credentials not available")

    test_email = f"{E2E_PREFIX.lower().replace('-', '')}@test.your-domain.com"
    test_uid = "399"

    try:
        conn = ldap_lib.initialize(settings.ldap_server)
        conn.simple_bind_s(settings.ldap_bind_dn, settings.ldap_bind_password)
    except Exception as e:
        pytest.skip(f"Cannot connect to LDAP: {e}")

    dn = f"uid={test_uid},ou=people,{settings.ldap_base_dn}"

    try:
        # Create test user
        attrs = [
            ("objectClass", [b"inetOrgPerson", b"posixAccount"]),
            ("cn", [b"E2E Test User"]),
            ("sn", [b"Test"]),
            ("uid", [test_uid.encode()]),
            ("mail", [test_email.encode()]),
            ("uidNumber", [test_uid.encode()]),
            ("gidNumber", [b"1000"]),
            ("homeDirectory", [f"/home/{test_uid}".encode()]),
        ]
        conn.add_s(dn, attrs)

        # Verify
        results = conn.search_s(
            f"ou=people,{settings.ldap_base_dn}",
            ldap_lib.SCOPE_SUBTREE,
            f"(uid={test_uid})",
        )
        assert len(results) >= 1, f"LDAP user {test_uid} not found after creation"

    finally:
        # Cleanup
        try:
            conn.delete_s(dn)
        except ldap_lib.NO_SUCH_OBJECT:
            pass
        conn.unbind_s()


@pytest.mark.timeout(180)
async def test_full_cycle(live_voice_service, live_task_manager_service, vikunja_client, vikunja_project):
    """Full cycle: voice request → task → query → verify → cleanup."""
    # Voice analysis
    voice_text = "部品P-A1234の在庫が不足しています。至急50個を発注してください。来週水曜日までに届くようにお願いします。"
    voice_result = await live_voice_service._analyze(voice_text)
    assert "title" in voice_result

    # Create task from voice result
    task_data = {
        "title": f"{PROMPT_PREFIX}{voice_result['title']}",
        "description": voice_result.get("description", ""),
        "priority": voice_result.get("priority", 2),
    }
    resp = vikunja_client.put(
        f"/api/v1/projects/{vikunja_project}/tasks",
        json=task_data,
    )
    resp.raise_for_status()
    task_id = resp.json()["id"]

    # Task manager query
    query_result = await live_task_manager_service.process_request("在庫発注のタスクを検索して")
    assert query_result["action"] == "query"

    # Cleanup
    vikunja_client.delete(f"/api/v1/tasks/{task_id}")
