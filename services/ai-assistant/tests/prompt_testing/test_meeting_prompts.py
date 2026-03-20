"""Prompt quality tests for Meeting module — structural + semantic evaluation.

Run with: RUN_PROMPT_TESTS=1 pytest tests/prompt_testing/test_meeting_prompts.py -v
"""

from __future__ import annotations

import json

import pytest

from .conftest import load_test_scripts

MEETING_SCRIPTS = load_test_scripts("meeting")
SCRIPT_IDS = [s["id"] for s in MEETING_SCRIPTS]


@pytest.mark.prompt_test
@pytest.mark.timeout(120)
@pytest.mark.parametrize("script", MEETING_SCRIPTS, ids=SCRIPT_IDS)
async def test_meeting_structural(script, live_meeting_service, structural_evaluator):
    """Structural check: verify extracted JSON has required keys and counts."""
    transcript = script["transcript"]
    expected = script["expected"]

    result = await live_meeting_service._extract_items(transcript)

    eval_result = structural_evaluator.evaluate(result, expected)
    assert eval_result.passed, (
        f"Script {script['id']} failed structural checks: {eval_result.summary()}\n"
        f"Output: {json.dumps(result, ensure_ascii=False, indent=2)}"
    )


@pytest.mark.prompt_test
@pytest.mark.slow
@pytest.mark.timeout(120)
@pytest.mark.parametrize("script", MEETING_SCRIPTS, ids=SCRIPT_IDS)
async def test_meeting_semantic(script, live_meeting_service, semantic_evaluator):
    """Semantic check: LLM-as-judge scores output quality."""
    transcript = script["transcript"]

    result = await live_meeting_service._extract_items(transcript)
    output_text = json.dumps(result, ensure_ascii=False, indent=2)

    expected_desc = (
        f"Extract action items, decisions, and document updates from a meeting transcript. "
        f"Expected: action_items (min {script['expected'].get('action_items', {}).get('min_count', 1)}), "
        f"decisions with keywords {script['expected'].get('decisions', {}).get('contains_keywords', [])}, "
        f"doc_updates (min {script['expected'].get('doc_updates', {}).get('min_count', 0)})."
    )

    eval_result = semantic_evaluator.evaluate(
        input_text=transcript,
        output_text=output_text,
        expected_description=expected_desc,
    )
    assert eval_result.passed, (
        f"Script {script['id']} failed semantic eval (score={eval_result.score:.2f}): "
        f"{eval_result.reasoning}"
    )
