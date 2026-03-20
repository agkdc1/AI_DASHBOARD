"""Fixtures for prompt quality tests — live Gemini services, TTS, evaluation."""

from __future__ import annotations

import os
import sys

import pytest
import yaml

# ── Ensure ai_assistant/ is on sys.path ──
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RUN_PROMPT_TESTS = os.environ.get("RUN_PROMPT_TESTS", "0") == "1"

# When running prompt tests against live Gemini, override the mock project
# set by the parent conftest.py. Use object.__setattr__ to bypass Pydantic
# frozen model validation.
if RUN_PROMPT_TESTS:
    os.environ["AI_GCP_PROJECT"] = "your-gcp-project-id"
    os.environ["AI_GCP_LOCATION"] = "asia-northeast1"
    from config import settings
    object.__setattr__(settings, "gcp_project", "your-gcp-project-id")
    object.__setattr__(settings, "gcp_location", "asia-northeast1")


def pytest_collection_modifyitems(config, items):
    """Skip all prompt tests unless RUN_PROMPT_TESTS=1."""
    if RUN_PROMPT_TESTS:
        return

    skip_marker = pytest.mark.skip(reason="RUN_PROMPT_TESTS not set")
    for item in items:
        if "prompt_testing" in str(item.fspath):
            item.add_marker(skip_marker)


# ─────────────────────────────────────────────────────────────────────
# YAML test script loading
# ─────────────────────────────────────────────────────────────────────

TEST_DATA_DIR = os.path.join(os.path.dirname(__file__), "test_data")


def load_test_scripts(module: str) -> list[dict]:
    """Load all YAML test scripts for a module.

    Args:
        module: Subdirectory name (meeting, voice_request, call_request, assistant, task_manager).

    Returns:
        List of parsed YAML dicts.
    """
    scripts = []
    module_dir = os.path.join(TEST_DATA_DIR, module)
    if not os.path.isdir(module_dir):
        return scripts

    for path in sorted(os.listdir(module_dir)):
        if path.endswith((".yaml", ".yml")):
            with open(os.path.join(module_dir, path)) as f:
                data = yaml.safe_load(f)
                if data:
                    data["_file"] = path
                    scripts.append(data)
    return scripts


# ─────────────────────────────────────────────────────────────────────
# Live service fixtures (session-scoped)
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def live_meeting_service():
    """Live MeetingService with real Gemini model."""
    from meeting.service import MeetingService

    svc = MeetingService()
    svc._ensure_model()
    return svc


@pytest.fixture(scope="session")
def live_voice_service():
    """Live VoiceRequestService with real Gemini model."""
    from voice_request.service import VoiceRequestService

    svc = VoiceRequestService()
    svc._ensure_model()
    return svc


@pytest.fixture(scope="session")
def live_call_service():
    """Live CallRequestService with real Gemini model."""
    from call_request.service import CallRequestService

    svc = CallRequestService()
    svc._ensure_model()
    return svc


@pytest.fixture(scope="session")
def live_assistant_service():
    """Live AssistantService with real Gemini model."""
    from assistant.service import AssistantService

    svc = AssistantService()
    svc._ensure_model()
    return svc


@pytest.fixture(scope="session")
def live_task_manager_service():
    """Live TaskManagerService with real Gemini model."""
    from task_manager.service import TaskManagerService

    svc = TaskManagerService()
    svc._ensure_model()
    return svc


@pytest.fixture(scope="session")
def masking_service():
    """Real MaskingService (regex only — no external deps)."""
    from masking.service import MaskingService

    return MaskingService()


# ─────────────────────────────────────────────────────────────────────
# Evaluation fixtures (session-scoped)
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def structural_evaluator():
    """Structural (deterministic) evaluator."""
    from .evaluator import StructuralEvaluator

    return StructuralEvaluator()


@pytest.fixture(scope="session")
def semantic_evaluator():
    """Semantic (LLM-as-judge) evaluator — uses Gemini Flash."""
    from .evaluator import SemanticEvaluator

    return SemanticEvaluator()


@pytest.fixture(scope="session")
def prompt_tracker():
    """Pass rate tracker."""
    from .prompt_tracker import PromptTracker

    return PromptTracker()


# ─────────────────────────────────────────────────────────────────────
# TTS fixture (session-scoped, optional)
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def tts_generator():
    """GCP TTS audio generator with caching."""
    from .tts_generator import TTSGenerator

    return TTSGenerator(sample_rate=16000)
