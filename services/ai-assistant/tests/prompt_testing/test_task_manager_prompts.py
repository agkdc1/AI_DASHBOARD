"""Prompt quality tests for Task Manager NLP module.

Run with: RUN_PROMPT_TESTS=1 pytest tests/prompt_testing/test_task_manager_prompts.py -v
"""

from __future__ import annotations

import json

import pytest

from .conftest import load_test_scripts

TASK_SCRIPTS = load_test_scripts("task_manager")
SCRIPT_IDS = [s["id"] for s in TASK_SCRIPTS]


@pytest.mark.prompt_test
@pytest.mark.timeout(120)
@pytest.mark.parametrize("script", TASK_SCRIPTS, ids=SCRIPT_IDS)
async def test_task_structural(script, live_task_manager_service, structural_evaluator):
    """Structural check: correct action, task fields."""
    input_text = script["input"]
    expected = script["expected"]

    result = await live_task_manager_service.process_request(input_text)
    parsed = result.get("parsed", {})

    eval_result = structural_evaluator.evaluate(parsed, expected)
    assert eval_result.passed, (
        f"Script {script['id']} failed structural checks: {eval_result.summary()}\n"
        f"Action: {result.get('action')}, Parsed: {json.dumps(parsed, ensure_ascii=False, indent=2)}"
    )


@pytest.mark.prompt_test
@pytest.mark.slow
@pytest.mark.timeout(120)
@pytest.mark.parametrize("script", TASK_SCRIPTS, ids=SCRIPT_IDS)
async def test_task_semantic(script, live_task_manager_service, semantic_evaluator):
    """Semantic check: LLM-as-judge scores NLP parsing quality."""
    input_text = script["input"]

    result = await live_task_manager_service.process_request(input_text)
    output_text = json.dumps(result.get("parsed", {}), ensure_ascii=False, indent=2)

    expected_action = script["expected"].get("action", "create")
    expected_desc = (
        f"Parse natural language task request into structured action. "
        f"Expected action: '{expected_action}'. "
        f"Input: '{input_text}'. "
        f"Should correctly identify the action type and extract relevant task fields."
    )

    eval_result = semantic_evaluator.evaluate(
        input_text=input_text,
        output_text=output_text,
        expected_description=expected_desc,
    )
    assert eval_result.passed, (
        f"Script {script['id']} failed semantic eval (score={eval_result.score:.2f}): "
        f"{eval_result.reasoning}"
    )
