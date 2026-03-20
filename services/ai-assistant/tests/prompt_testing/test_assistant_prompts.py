"""Prompt quality tests for Assistant (guide-only) module.

Run with: RUN_PROMPT_TESTS=1 pytest tests/prompt_testing/test_assistant_prompts.py -v
"""

from __future__ import annotations

import pytest

from .conftest import load_test_scripts

ASSISTANT_SCRIPTS = load_test_scripts("assistant")
SCRIPT_IDS = [s["id"] for s in ASSISTANT_SCRIPTS]


@pytest.mark.prompt_test
@pytest.mark.timeout(120)
@pytest.mark.parametrize("script", ASSISTANT_SCRIPTS, ids=SCRIPT_IDS)
async def test_assistant_structural(script, live_assistant_service, structural_evaluator):
    """Structural check: language, keywords, forbidden content, min length."""
    question = script["question"]
    expected = script["expected"]

    response_text = await live_assistant_service.chat(question)

    eval_result = structural_evaluator.evaluate(response_text, expected)
    assert eval_result.passed, (
        f"Script {script['id']} failed structural checks: {eval_result.summary()}\n"
        f"Response (first 200 chars): {response_text[:200]}"
    )


@pytest.mark.prompt_test
@pytest.mark.slow
@pytest.mark.timeout(120)
@pytest.mark.parametrize("script", ASSISTANT_SCRIPTS, ids=SCRIPT_IDS)
async def test_assistant_semantic(script, live_assistant_service, semantic_evaluator):
    """Semantic check: LLM-as-judge scores guidance quality."""
    question = script["question"]

    response_text = await live_assistant_service.chat(question)

    expected_desc = (
        f"Provide step-by-step operational guidance for: '{question}'. "
        f"Must contain any of: {script['expected'].get('must_contain_any', [])}. "
        f"Must NOT execute actions or claim to have done anything. "
        f"Language: {'Japanese' if script['expected'].get('language') == 'ja' else 'Korean'}."
    )

    eval_result = semantic_evaluator.evaluate(
        input_text=question,
        output_text=response_text,
        expected_description=expected_desc,
    )
    assert eval_result.passed, (
        f"Script {script['id']} failed semantic eval (score={eval_result.score:.2f}): "
        f"{eval_result.reasoning}"
    )
