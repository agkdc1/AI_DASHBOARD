"""Prompt quality tests for Call Request module.

Run with: RUN_PROMPT_TESTS=1 pytest tests/prompt_testing/test_call_prompts.py -v
"""

from __future__ import annotations

import json

import pytest

from .conftest import load_test_scripts

CALL_SCRIPTS = load_test_scripts("call_request")
SCRIPT_IDS = [s["id"] for s in CALL_SCRIPTS]


@pytest.mark.prompt_test
@pytest.mark.timeout(120)
@pytest.mark.parametrize("script", CALL_SCRIPTS, ids=SCRIPT_IDS)
async def test_call_structural(script, live_call_service, structural_evaluator):
    """Structural check: verify JSON keys, title, priority, decisions."""
    text = script["text"]
    expected = script["expected"]

    result = await live_call_service._analyze(text)

    eval_result = structural_evaluator.evaluate(result, expected)
    assert eval_result.passed, (
        f"Script {script['id']} failed structural checks: {eval_result.summary()}\n"
        f"Output: {json.dumps(result, ensure_ascii=False, indent=2)}"
    )


@pytest.mark.prompt_test
@pytest.mark.slow
@pytest.mark.timeout(120)
@pytest.mark.parametrize("script", CALL_SCRIPTS, ids=SCRIPT_IDS)
async def test_call_semantic(script, live_call_service, semantic_evaluator):
    """Semantic check: LLM-as-judge scores output quality."""
    text = script["text"]

    result = await live_call_service._analyze(text)
    output_text = json.dumps(result, ensure_ascii=False, indent=2)

    expected_desc = (
        f"Extract a task title, description, due_date, priority (1-4), and decisions list "
        f"from a business phone call. Title should relate to: {script['expected'].get('title_contains', [])}. "
        f"Should include decisions: {script['expected'].get('has_decisions', True)}."
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
