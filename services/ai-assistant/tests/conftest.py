"""Shared fixtures for AI assistant unit tests."""

import os
import sys

import pytest

# ── Ensure ai_assistant/ is on sys.path so `from config import settings` works ──
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── Ensure tests/ is on sys.path so `from helpers import ...` works ──
sys.path.insert(0, os.path.dirname(__file__))

# ── Override settings via env BEFORE importing anything that reads config ──
os.environ.setdefault("AI_GCP_PROJECT", "test-project")
os.environ.setdefault("AI_VIKUNJA_URL", "https://vikunja.test")
os.environ.setdefault("AI_VIKUNJA_TOKEN", "test-vikunja-token")
os.environ.setdefault("AI_LDAP_SERVER", "ldap://localhost:389")
os.environ.setdefault("AI_LDAP_BASE_DN", "dc=test,dc=local")
os.environ.setdefault("AI_LDAP_BIND_DN", "cn=admin,dc=test,dc=local")
os.environ.setdefault("AI_LDAP_BIND_PASSWORD", "testpass")
os.environ.setdefault("AI_FAXAPI_URL", "http://faxapi.test:8010")
os.environ.setdefault("AI_SMTP_HOST", "localhost")
os.environ.setdefault("AI_SMTP_PORT", "2525")
os.environ.setdefault("AI_SUPERUSER_EMAIL", "test@test.com")

from helpers import (
    make_gemini_model,
    make_ldap_conn,
    make_sm_client,
)


# ─────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def masking_service():
    """Real MaskingService (regex only — no external deps for mask_text)."""
    from masking.service import MaskingService
    return MaskingService()


@pytest.fixture
def assistant_service():
    """AssistantService with mock Gemini model."""
    from assistant.service import AssistantService
    svc = AssistantService()
    svc._model = make_gemini_model("テストガイダンス応答です。")
    return svc


@pytest.fixture
def task_manager_service():
    """TaskManagerService with mock Gemini model."""
    from task_manager.service import TaskManagerService
    svc = TaskManagerService()
    svc._model = make_gemini_model('{"action":"create","task":{"title":"テストタスク","project_id":1,"priority":2}}')
    return svc


@pytest.fixture
def meeting_service():
    """MeetingService with mock Gemini model."""
    from meeting.service import MeetingService
    svc = MeetingService()
    svc._model = make_gemini_model(
        '{"action_items":[{"title":"テストアクション","assignee":null,"due_date":null,"description":"テスト"}],'
        '"decisions":[{"summary":"テスト決定"}],'
        '"doc_updates":[{"target_doc":"SOP","change":"テスト更新"}]}'
    )
    return svc


@pytest.fixture
def evolution_service():
    """EvolutionService with mock Gemini model."""
    from evolution.service import EvolutionService
    svc = EvolutionService()
    svc._model = make_gemini_model("# 改善提案\n\n- テスト提案です。")
    return svc


@pytest.fixture
def phone_service():
    """PhoneService with mock LDAP connection."""
    from phone.service import PhoneService
    svc = PhoneService()
    svc._conn = make_ldap_conn()
    return svc


@pytest.fixture
def rakuten_service():
    """RakutenKeyService with mock SM client."""
    from rakuten.service import RakutenKeyService
    svc = RakutenKeyService()
    svc._sm_client = make_sm_client()
    return svc


@pytest.fixture
def voice_request_service():
    """VoiceRequestService with mock Gemini model."""
    from voice_request.service import VoiceRequestService
    svc = VoiceRequestService()
    svc._model = make_gemini_model(
        '{"title":"テスト依頼","description":"テスト説明","due_date":null,"priority":2,"missing_details":[]}'
    )
    return svc


@pytest.fixture
def call_request_service():
    """CallRequestService with mock Gemini model."""
    from call_request.service import CallRequestService
    svc = CallRequestService()
    svc._model = make_gemini_model(
        '{"title":"通話タスク","description":"通話内容","due_date":null,"priority":2,"decisions":["テスト決定"]}'
    )
    return svc
