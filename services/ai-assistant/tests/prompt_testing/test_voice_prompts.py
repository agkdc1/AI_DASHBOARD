"""Prompt quality tests for Voice Request module.

Run with: RUN_PROMPT_TESTS=1 pytest tests/prompt_testing/test_voice_prompts.py -v
"""

from __future__ import annotations

import json

import pytest

from .conftest import load_test_scripts

VOICE_SCRIPTS = load_test_scripts("voice_request")
SCRIPT_IDS = [s["id"] for s in VOICE_SCRIPTS]


@pytest.mark.prompt_test
@pytest.mark.timeout(120)
@pytest.mark.parametrize("script", VOICE_SCRIPTS, ids=SCRIPT_IDS)
async def test_voice_structural(script, live_voice_service, structural_evaluator):
    """Structural check: verify JSON keys, title keywords, priority, due_date."""
    text = script["text"]
    expected = script["expected"]

    result = await live_voice_service._analyze(text)

    eval_result = structural_evaluator.evaluate(result, expected)
    assert eval_result.passed, (
        f"Script {script['id']} failed structural checks: {eval_result.summary()}\n"
        f"Output: {json.dumps(result, ensure_ascii=False, indent=2)}"
    )


@pytest.mark.prompt_test
@pytest.mark.slow
@pytest.mark.timeout(120)
@pytest.mark.parametrize("script", VOICE_SCRIPTS, ids=SCRIPT_IDS)
async def test_voice_semantic(script, live_voice_service, semantic_evaluator):
    """Semantic check: LLM-as-judge scores output quality."""
    text = script["text"]

    result = await live_voice_service._analyze(text)
    output_text = json.dumps(result, ensure_ascii=False, indent=2)

    expected_desc = (
        f"Extract a task title, description, due_date, priority (1-4), and missing_details "
        f"from a voice work request. Title should relate to: {script['expected'].get('title_contains', [])}. "
        f"Priority should be in range {script['expected'].get('priority_range', [1, 4])}."
    )

    eval_result = semantic_evaluator.evaluate(
        input_text=text,
        output_text=output_text,
        expected_description=expected_desc,
    )
    assert eval_result.passed, (
        f"Script {script['id']} failed semantic eval (score={eval_result.score:.2f}): "
        f"{eval_result.reasoning}"
    )
