"""Two-tier evaluation: structural checks (deterministic) + semantic scoring (LLM-as-judge)."""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class EvalResult:
    """Result of a single evaluation."""
    passed: bool
    score: float  # 0.0 - 1.0
    checks: list[dict] = field(default_factory=list)
    reasoning: str = ""

    def summary(self) -> str:
        failed = [c for c in self.checks if not c["passed"]]
        if not failed:
            return f"PASS (score={self.score:.2f})"
        names = ", ".join(c["name"] for c in failed)
        return f"FAIL (score={self.score:.2f}): {names}"


# ─────────────────────────────────────────────────────────────────────
# Structural Evaluator (deterministic, fast)
# ─────────────────────────────────────────────────────────────────────

def _normalize_text(text: str) -> str:
    """Normalize Japanese/Korean text for fuzzy keyword matching.

    Strips filler words, maps pronunciation approximations back to originals,
    normalizes unicode, and lowercases.
    """
    # Strip common filler words and noise markers
    fillers = [
        "えーと", "えーっと", "あのー", "あの", "そのー", "まぁ", "なんか",
        "えー", "うーん", "ちょっと",
        "[咳]", "[雑音]", "[一時停止]", "[ノイズ]", "[電話の音]",
        "[기침]", "[잡음]", "[일시정지]",
    ]
    result = text
    for f in fillers:
        result = result.replace(f, "")
    # Map pronunciation approximations back to standard forms
    approx_map = {
        "エスケーユー": "SKU", "에스케이유": "SKU",
        "エスオー": "SO", "에스오": "SO",
        "ピーオー": "PO", "피오": "PO",
        "ピーディーエフ": "PDF", "피디에프": "PDF",
        "비쿤자": "Vikunja", "ビクンジャ": "Vikunja",
    }
    for approx, original in approx_map.items():
        result = result.replace(approx, original)
    # Normalize unicode (NFC)
    result = unicodedata.normalize("NFC", result)
    # Collapse whitespace
    result = re.sub(r"\s+", " ", result).strip()
    return result.lower()


# Keep old name as alias for compatibility
_normalize_ja = _normalize_text


class StructuralEvaluator:
    """Deterministic checks on Gemini output against expected constraints."""

    def evaluate(self, output: Any, expected: dict) -> EvalResult:
        """Run all applicable structural checks.

        Args:
            output: Parsed JSON output from Gemini (dict) or raw text (str).
            expected: Expected constraints from YAML test script.

        Returns:
            EvalResult with individual check results.
        """
        checks = []

        if isinstance(output, str):
            try:
                output_dict = json.loads(output)
            except (json.JSONDecodeError, TypeError):
                output_dict = None
            output_text = output
        elif isinstance(output, dict):
            output_dict = output
            output_text = json.dumps(output, ensure_ascii=False)
        else:
            output_dict = None
            output_text = str(output)

        # valid_json_keys
        if "valid_json_keys" in expected and output_dict is not None:
            required_keys = expected["valid_json_keys"]
            missing = [k for k in required_keys if k not in output_dict]
            checks.append({
                "name": "valid_json_keys",
                "passed": len(missing) == 0,
                "detail": f"missing keys: {missing}" if missing else "all keys present",
            })

        # title_contains (with normalization for noisy input)
        if "title_contains" in expected and output_dict is not None:
            title = output_dict.get("title", "")
            keywords = expected["title_contains"]
            title_norm = _normalize_ja(title)
            found = any(kw.lower() in title.lower() or _normalize_ja(kw) in title_norm for kw in keywords)
            checks.append({
                "name": "title_contains",
                "passed": found,
                "detail": f"title='{title}', expected any of {keywords}",
            })

        # must_contain_any (with normalization for noisy input)
        if "must_contain_any" in expected:
            keywords = expected["must_contain_any"]
            output_norm = _normalize_text(output_text)
            found = any(
                kw.lower() in output_text.lower() or _normalize_text(kw) in output_norm
                for kw in keywords
            )
            checks.append({
                "name": "must_contain_any",
                "passed": found,
                "detail": f"expected any of {keywords}",
            })

        # must_not_contain
        if "must_not_contain" in expected:
            forbidden = expected["must_not_contain"]
            violations = [f for f in forbidden if f in output_text]
            checks.append({
                "name": "must_not_contain",
                "passed": len(violations) == 0,
                "detail": f"found forbidden: {violations}" if violations else "clean",
            })

        # priority_range (check nested task.priority if top-level not found)
        if "priority_range" in expected and output_dict is not None:
            priority = output_dict.get("priority")
            if priority is None and "task" in output_dict:
                priority = output_dict["task"].get("priority")
            lo, hi = expected["priority_range"]
            checks.append({
                "name": "priority_range",
                "passed": priority is not None and lo <= priority <= hi,
                "detail": f"priority={priority}, expected [{lo}, {hi}]",
            })

        # due_date_present (check nested task.due_date if top-level not found)
        if "due_date_present" in expected and output_dict is not None:
            due_date = output_dict.get("due_date")
            if due_date is None and "task" in output_dict:
                due_date = output_dict["task"].get("due_date")
            has_due = due_date is not None
            checks.append({
                "name": "due_date_present",
                "passed": has_due == expected["due_date_present"],
                "detail": f"due_date={'present' if has_due else 'absent'}, expected={'present' if expected['due_date_present'] else 'absent'}",
            })

        # language detection
        if "language" in expected:
            lang = expected["language"]
            if lang == "ja":
                has_lang = bool(re.search(r"[\u3040-\u309f\u30a0-\u30ff]", output_text))
            elif lang == "ko":
                has_lang = bool(re.search(r"[\uac00-\ud7af]", output_text))
            else:
                has_lang = True  # Skip for other languages
            checks.append({
                "name": "language",
                "passed": has_lang,
                "detail": f"expected {lang} characters in output",
            })

        # min_length
        if "min_length" in expected:
            checks.append({
                "name": "min_length",
                "passed": len(output_text) >= expected["min_length"],
                "detail": f"length={len(output_text)}, min={expected['min_length']}",
            })

        # min_count (for list fields like action_items, decisions)
        if "action_items" in expected and output_dict is not None:
            ai_expected = expected["action_items"]
            items = output_dict.get("action_items", [])
            if "min_count" in ai_expected:
                checks.append({
                    "name": "action_items_count",
                    "passed": len(items) >= ai_expected["min_count"],
                    "detail": f"count={len(items)}, min={ai_expected['min_count']}",
                })

        if "decisions" in expected and output_dict is not None:
            dec_expected = expected["decisions"]
            items = output_dict.get("decisions", [])
            if "min_count" in dec_expected:
                checks.append({
                    "name": "decisions_count",
                    "passed": len(items) >= dec_expected["min_count"],
                    "detail": f"count={len(items)}, min={dec_expected['min_count']}",
                })
            if "contains_keywords" in dec_expected:
                text = json.dumps(items, ensure_ascii=False)
                found = any(kw in text for kw in dec_expected["contains_keywords"])
                checks.append({
                    "name": "decisions_keywords",
                    "passed": found,
                    "detail": f"expected any of {dec_expected['contains_keywords']}",
                })

        if "doc_updates" in expected and output_dict is not None:
            du_expected = expected["doc_updates"]
            items = output_dict.get("doc_updates", [])
            if "min_count" in du_expected:
                checks.append({
                    "name": "doc_updates_count",
                    "passed": len(items) >= du_expected["min_count"],
                    "detail": f"count={len(items)}, min={du_expected['min_count']}",
                })

        # action check (task manager)
        if "action" in expected and output_dict is not None:
            parsed_action = output_dict.get("action")
            checks.append({
                "name": "action",
                "passed": parsed_action == expected["action"],
                "detail": f"action='{parsed_action}', expected='{expected['action']}'",
            })

        # task_title_contains (with normalization for noisy input)
        if "task_title_contains" in expected and output_dict is not None:
            task = output_dict.get("task", output_dict)
            title = task.get("title", "")
            keywords = expected["task_title_contains"]
            title_norm = _normalize_text(title)
            found = any(
                kw.lower() in title.lower() or _normalize_text(kw) in title_norm
                for kw in keywords
            )
            checks.append({
                "name": "task_title_contains",
                "passed": found,
                "detail": f"title='{title}', expected any of {keywords}",
            })

        # has_due_date (task manager)
        if "has_due_date" in expected and output_dict is not None:
            task = output_dict.get("task", output_dict)
            has_due = task.get("due_date") is not None
            checks.append({
                "name": "has_due_date",
                "passed": has_due == expected["has_due_date"],
                "detail": f"due_date={'present' if has_due else 'absent'}",
            })

        # decisions key present (call request)
        if "has_decisions" in expected and output_dict is not None:
            has_dec = "decisions" in output_dict and isinstance(output_dict["decisions"], list)
            checks.append({
                "name": "has_decisions",
                "passed": has_dec == expected["has_decisions"],
                "detail": f"decisions={'present' if has_dec else 'absent'}",
            })

        # Score: fraction of passed checks
        if checks:
            passed_count = sum(1 for c in checks if c["passed"])
            score = passed_count / len(checks)
        else:
            score = 1.0

        return EvalResult(
            passed=all(c["passed"] for c in checks),
            score=score,
            checks=checks,
        )


# ─────────────────────────────────────────────────────────────────────
# Semantic Evaluator (Gemini Flash as judge)
# ─────────────────────────────────────────────────────────────────────

JUDGE_PROMPT = """You are evaluating an AI assistant's output for quality. Rate the output on these criteria:

1. **Accuracy**: Does the output correctly extract/identify the key information from the input?
2. **Completeness**: Does the output cover all important aspects mentioned in the input?
3. **Relevance**: Is the output focused on the task and free of irrelevant information?

## Input (what was given to the AI)
{input_text}

## Expected behavior
{expected_description}

## AI Output (what the AI produced)
{output_text}

## Instructions
Rate the output from 0.0 (completely wrong) to 1.0 (perfect). Respond ONLY with a JSON object:
{{"score": 0.85, "reasoning": "Brief explanation of the score."}}
"""

PASS_THRESHOLD = 0.55


class SemanticEvaluator:
    """Use Gemini Flash as a judge to score prompt output quality."""

    def __init__(self, model: Any = None) -> None:
        self._model = model

    def _ensure_model(self) -> Any:
        if self._model is None:
            from google.cloud import aiplatform
            from vertexai.generative_models import GenerativeModel

            aiplatform.init(
                project="your-gcp-project-id",
                location="asia-northeast1",
            )
            self._model = GenerativeModel("gemini-2.5-flash")
        return self._model

    def evaluate(
        self,
        input_text: str,
        output_text: str,
        expected_description: str,
    ) -> EvalResult:
        """Score output quality using LLM-as-judge.

        Args:
            input_text: Original input given to the AI.
            output_text: AI's raw output.
            expected_description: Human description of what good output looks like.

        Returns:
            EvalResult with semantic score and reasoning.
        """
        model = self._ensure_model()

        prompt = JUDGE_PROMPT.format(
            input_text=input_text,
            expected_description=expected_description,
            output_text=output_text,
        )

        try:
            response = model.generate_content([{"role": "user", "parts": [{"text": prompt}]}])
            text = response.text.strip()

            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            result = json.loads(text)
            score = float(result.get("score", 0.0))
            reasoning = result.get("reasoning", "")

            return EvalResult(
                passed=score >= PASS_THRESHOLD,
                score=score,
                reasoning=reasoning,
            )
        except Exception as e:
            log.error("Semantic evaluation failed: %s", e)
            return EvalResult(
                passed=False,
                score=0.0,
                reasoning=f"Evaluation error: {e}",
            )
