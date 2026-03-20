#!/usr/bin/env python3
"""Enhance YAML test scripts with Gemini-generated natural conversations.

Uses Gemini 2.5 Pro to rewrite templated transcripts into natural,
realistic Japanese/Korean business conversations with realistic noise:
filler words, self-corrections, background noise markers, pronunciation
approximations, and mumbled numbers.

Usage:
    GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json python enhance_test_data.py [--module MODULE] [--dry-run]

Requires: google-cloud-aiplatform, pyyaml
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import yaml

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

TEST_DATA_DIR = Path(__file__).parent / "test_data"

# Rate limiting: Gemini Pro has ~60 RPM for free tier
DELAY_BETWEEN_CALLS = 1.5  # seconds

# Shared noise instruction block injected into all enhancement prompts
NOISE_INSTRUCTIONS = """
## ノイズ・リアリティ要件（重要）
以下の要素を積極的に含めてリアルな音声認識テキストにしてください：

1. **フィラーワード**（最低5箇所）:
   - 日本語: えーと、あの、あのー、ちょっと、そのー、まぁ、なんか、えー、うーん
   - 韓国語: 음, 그, 어, 저기, 뭐, 이제, 그러니까, 아

2. **言い直し・自己訂正**（最低2箇所）:
   - 日本語: 「あ、違う、えーと…」「いや、そうじゃなくて…」「あ、ごめん、」
   - 韓国語: 「아니, 그게 아니라...」「아, 잠깐, 다시 말하면...」

3. **背景ノイズマーカー**（1-3箇所）:
   - [咳]、[雑音]、[一時停止]、[ノイズ]、[電話の音]
   - 韓国語: [기침], [잡음], [일시정지]

4. **発音近似・聞き間違い風**（1-2箇所）:
   - SKU→エスケーユー、SO→エスオー、PO→ピーオー、PDF→ピーディーエフ
   - 数字の曖昧表現: 「えーっと、3...いや5個だったかな」「30、いや、300個ぐらい」

5. **不完全な文・途切れ**（1箇所）:
   - 「それで、あの…なんだっけ…ああそうそう」
   - 文の途中で言い淀む
"""


def get_model(model_name: str = "gemini-2.5-pro"):
    """Initialize Vertex AI and return Gemini model."""
    from google.cloud import aiplatform
    from vertexai.generative_models import GenerativeModel

    project = os.environ.get("AI_GCP_PROJECT", "your-gcp-project-id")
    location = os.environ.get("AI_GCP_LOCATION", "asia-northeast1")

    aiplatform.init(project=project, location=location)
    log.info("Using model: %s", model_name)
    return GenerativeModel(model_name)


# Model selection per module: Pro for meeting/call (complex multi-speaker),
# Flash for assistant/task_manager/voice (simpler, faster)
MODULE_MODELS = {
    "meeting": "gemini-2.5-pro",
    "call": "gemini-2.5-pro",
    "voice": "gemini-2.5-flash",
    "task_manager": "gemini-2.5-flash",
    "assistant": "gemini-2.5-flash",
}


MEETING_ENHANCE_PROMPT = """あなたは日本の中小企業の会議シミュレーターです。
以下の会議テーマと期待される結果に基づいて、リアルな会議の文字起こしを生成してください。

## 要件
- 言語: {language}
- テーマ: {name}
- 個人名は必ず[REDACTED_NAME]で置き換える
- 住所は[REDACTED_ADDRESS]で置き換える
- 電話番号は[REDACTED_PHONE]で置き換える
- 会議参加者は2-4名
- 以下の要素を必ず含める：
  - アクションアイテム: {action_items_desc}
  - 決定事項: {decisions_desc}
  - ドキュメント更新: {doc_updates_desc}
- 自然な会話（相槌、質問、議論）を含める
- 500-800文字程度
""" + NOISE_INSTRUCTIONS + """
## 元のテンプレート（参考）
{original_transcript}

上記を踏まえ、ノイズを含むリアルな会議録を生成してください。文字起こしのみを出力してください。"""

VOICE_ENHANCE_PROMPT = """あなたは日本企業の従業員のシミュレーターです。
以下のテーマで、音声録音を想定した自然な業務依頼を生成してください。

## 要件
- 言語: {language}
- テーマ: {name}
- 個人名は[REDACTED_NAME]、住所は[REDACTED_ADDRESS]、電話番号は[REDACTED_PHONE]で置き換え
- 1人の話者による口頭での依頼
- 以下のキーワードを自然に含める: {keywords}
- 100-250文字程度
- 期限の言及: {has_due_date}
""" + NOISE_INSTRUCTIONS + """
## 元のテンプレート（参考）
{original_text}

上記を踏まえ、ノイズを含むリアルな音声依頼の文字起こしを生成してください。テキストのみ出力してください。"""

CALL_ENHANCE_PROMPT = """あなたは日本企業の社員間の電話通話のシミュレーターです。
以下のテーマで、リアルな業務通話の文字起こしを生成してください。

## 要件
- 言語: {language}
- テーマ: {name}
- 2人の会話（発信者と受信者）
- 個人名は[REDACTED_NAME]、住所は[REDACTED_ADDRESS]、電話番号は[REDACTED_PHONE]で置き換え
- 通話特有の表現（「もしもし」「お疲れ様です」「では」「失礼します」）を含む
- 以下のキーワードを自然に含める: {keywords}
- 決定事項を含む: {has_decisions}
- 200-400文字程度

### 電話通話特有のノイズ
- 電話回線の途切れ: 「あ、ちょっと聞こえにくい...」「もう一度お願いします」
- エコー/遅延による重複: 「はい、はい」
""" + NOISE_INSTRUCTIONS + """
## 元のテンプレート（参考）
{original_text}

上記を踏まえ、ノイズを含むリアルな電話通話の文字起こしを生成してください。テキストのみ出力してください。"""

TASK_MANAGER_ENHANCE_PROMPT = """あなたは日本企業の従業員のシミュレーターです。
以下のタスク管理リクエストを、実際にチャットで入力するようなカジュアルなテキストに書き換えてください。

## 要件
- 言語: {language}
- テーマ: {name}
- 以下のキーワードを含める: {keywords}
- アクション: {action}

## ノイズ要件
1. **タイプミス・変換ミス**（1-2箇所）: 在こ→在庫、発装→発送、化員→課員
2. **カジュアルな表現**: 口語体で書く（「お願いします」→「お願い」「頼む」）
3. **不完全な文**: 「あ、あと期限は明日で」のように思いつきで追加
4. **句読点の欠如**: 読点を省略して一文で書く
5. 韓国語の場合: 맞춤법ミス、略語使用

## 元のテンプレート
{original_text}

上記を踏まえ、よりリアルなチャット入力を生成してください。テキストのみ出力してください。"""

ASSISTANT_ENHANCE_PROMPT = """あなたは日本企業の従業員のシミュレーターです。
以下のAIアシスタントへの質問を、実際にチャットで入力するようなカジュアルなテキストに書き換えてください。

## 要件
- 言語: {language}
- テーマ: {name}
- 以下のキーワードを含める: {keywords}

## ノイズ要件
1. **タイプミス・変換ミス**（1箇所）: 手受→手順、在こ→在庫
2. **カジュアルな表現**: 敬語を省略したりフランクに質問
3. **曖昧な表現**: 「あれってどうやるんだっけ」「〇〇の件」
4. 韓国語の場合: 略語、打ち間違い

## 元のテンプレート
{original_text}

上記を踏まえ、よりリアルなチャット入力を生成してください。テキストのみ出力してください。"""


def enhance_meeting_scripts(model, dry_run: bool = False) -> int:
    """Enhance meeting transcripts with natural conversations."""
    meeting_dir = TEST_DATA_DIR / "meeting"
    count = 0

    for path in sorted(meeting_dir.glob("*.yaml")):
        with open(path) as f:
            data = yaml.safe_load(f)

        expected = data.get("expected", {})
        ai = expected.get("action_items", {})
        dec = expected.get("decisions", {})
        doc = expected.get("doc_updates", {})

        lang_desc = {
            "ja-JP": "日本語のみ",
            "ko-KR": "韓国語のみ",
            "mixed": "日本語と韓国語の混合（バイリンガル会議）",
        }.get(data.get("language", "ja-JP"), "日本語")

        prompt = MEETING_ENHANCE_PROMPT.format(
            language=lang_desc,
            name=data.get("name", "Business meeting"),
            action_items_desc=f"最低{ai.get('min_count', 1)}件",
            decisions_desc=f"最低{dec.get('min_count', 1)}件, キーワード: {dec.get('contains_keywords', [])}",
            doc_updates_desc=f"最低{doc.get('min_count', 0)}件",
            original_transcript=data.get("transcript", ""),
        )

        if dry_run:
            log.info("DRY RUN: Would enhance %s", path.name)
            count += 1
            continue

        try:
            response = model.generate_content([{"role": "user", "parts": [{"text": prompt}]}])
            new_transcript = response.text.strip()
            # Remove markdown code blocks if present
            if new_transcript.startswith("```"):
                new_transcript = new_transcript.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            data["transcript"] = new_transcript
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

            log.info("Enhanced: %s (%d chars)", path.name, len(new_transcript))
            count += 1
            time.sleep(DELAY_BETWEEN_CALLS)
        except Exception as e:
            log.error("Failed to enhance %s: %s", path.name, e)
            time.sleep(DELAY_BETWEEN_CALLS * 2)

    return count


def enhance_voice_scripts(model, dry_run: bool = False) -> int:
    """Enhance voice request texts with natural speech."""
    voice_dir = TEST_DATA_DIR / "voice_request"
    count = 0

    for path in sorted(voice_dir.glob("*.yaml")):
        with open(path) as f:
            data = yaml.safe_load(f)

        expected = data.get("expected", {})
        lang_desc = "日本語" if data.get("language") == "ja-JP" else "韓国語"

        prompt = VOICE_ENHANCE_PROMPT.format(
            language=lang_desc,
            name=data.get("name", "Voice request"),
            keywords=expected.get("title_contains", []),
            has_due_date="はい" if expected.get("due_date_present") else "いいえ",
            original_text=data.get("text", ""),
        )

        if dry_run:
            log.info("DRY RUN: Would enhance %s", path.name)
            count += 1
            continue

        try:
            response = model.generate_content([{"role": "user", "parts": [{"text": prompt}]}])
            new_text = response.text.strip()
            if new_text.startswith("```"):
                new_text = new_text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            data["text"] = new_text
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

            log.info("Enhanced: %s (%d chars)", path.name, len(new_text))
            count += 1
            time.sleep(DELAY_BETWEEN_CALLS)
        except Exception as e:
            log.error("Failed to enhance %s: %s", path.name, e)
            time.sleep(DELAY_BETWEEN_CALLS * 2)

    return count


def enhance_call_scripts(model, dry_run: bool = False) -> int:
    """Enhance call transcripts with natural phone conversations."""
    call_dir = TEST_DATA_DIR / "call_request"
    count = 0

    for path in sorted(call_dir.glob("*.yaml")):
        with open(path) as f:
            data = yaml.safe_load(f)

        expected = data.get("expected", {})
        lang_desc = "日本語" if data.get("language") == "ja-JP" else "韓国語"

        prompt = CALL_ENHANCE_PROMPT.format(
            language=lang_desc,
            name=data.get("name", "Call request"),
            keywords=expected.get("title_contains", []),
            has_decisions="はい" if expected.get("has_decisions") else "いいえ",
            original_text=data.get("text", ""),
        )

        if dry_run:
            log.info("DRY RUN: Would enhance %s", path.name)
            count += 1
            continue

        try:
            response = model.generate_content([{"role": "user", "parts": [{"text": prompt}]}])
            new_text = response.text.strip()
            if new_text.startswith("```"):
                new_text = new_text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            data["text"] = new_text
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

            log.info("Enhanced: %s (%d chars)", path.name, len(new_text))
            count += 1
            time.sleep(DELAY_BETWEEN_CALLS)
        except Exception as e:
            log.error("Failed to enhance %s: %s", path.name, e)
            time.sleep(DELAY_BETWEEN_CALLS * 2)

    return count


def enhance_task_manager_scripts(model, dry_run: bool = False) -> int:
    """Enhance task manager inputs with casual/noisy text."""
    tm_dir = TEST_DATA_DIR / "task_manager"
    count = 0

    for path in sorted(tm_dir.glob("*.yaml")):
        with open(path) as f:
            data = yaml.safe_load(f)

        expected = data.get("expected", {})
        lang_desc = "日本語" if data.get("language") == "ja-JP" else "韓国語"

        prompt = TASK_MANAGER_ENHANCE_PROMPT.format(
            language=lang_desc,
            name=data.get("name", "Task request"),
            keywords=expected.get("task_title_contains", []),
            action=expected.get("action", "create"),
            original_text=data.get("text", ""),
        )

        if dry_run:
            log.info("DRY RUN: Would enhance %s", path.name)
            count += 1
            continue

        try:
            response = model.generate_content([{"role": "user", "parts": [{"text": prompt}]}])
            new_text = response.text.strip()
            if new_text.startswith("```"):
                new_text = new_text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            data["text"] = new_text
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

            log.info("Enhanced: %s (%d chars)", path.name, len(new_text))
            count += 1
            time.sleep(DELAY_BETWEEN_CALLS)
        except Exception as e:
            log.error("Failed to enhance %s: %s", path.name, e)
            time.sleep(DELAY_BETWEEN_CALLS * 2)

    return count


def enhance_assistant_scripts(model, dry_run: bool = False) -> int:
    """Enhance assistant inputs with casual/noisy text."""
    ast_dir = TEST_DATA_DIR / "assistant"
    count = 0

    for path in sorted(ast_dir.glob("*.yaml")):
        with open(path) as f:
            data = yaml.safe_load(f)

        expected = data.get("expected", {})
        lang_desc = "日本語" if data.get("language") == "ja-JP" else "韓国語"

        prompt = ASSISTANT_ENHANCE_PROMPT.format(
            language=lang_desc,
            name=data.get("name", "Assistant query"),
            keywords=expected.get("title_contains", expected.get("must_contain_any", [])),
            original_text=data.get("text", ""),
        )

        if dry_run:
            log.info("DRY RUN: Would enhance %s", path.name)
            count += 1
            continue

        try:
            response = model.generate_content([{"role": "user", "parts": [{"text": prompt}]}])
            new_text = response.text.strip()
            if new_text.startswith("```"):
                new_text = new_text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            data["text"] = new_text
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

            log.info("Enhanced: %s (%d chars)", path.name, len(new_text))
            count += 1
            time.sleep(DELAY_BETWEEN_CALLS)
        except Exception as e:
            log.error("Failed to enhance %s: %s", path.name, e)
            time.sleep(DELAY_BETWEEN_CALLS * 2)

    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Enhance test data with Gemini-generated natural conversations")
    parser.add_argument("--module", choices=["meeting", "voice", "call", "task_manager", "assistant", "all"],
                       default="all", help="Which module to enhance")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    args = parser.parse_args()

    # Cache models by name to avoid re-initializing
    _model_cache: dict = {}

    def _get_module_model(module: str):
        if args.dry_run:
            return None
        model_name = MODULE_MODELS.get(module, "gemini-2.5-flash")
        if model_name not in _model_cache:
            _model_cache[model_name] = get_model(model_name)
        return _model_cache[model_name]

    total = 0
    if args.module in ("meeting", "all"):
        log.info("=== Enhancing meeting scripts ===")
        total += enhance_meeting_scripts(_get_module_model("meeting"), args.dry_run)

    if args.module in ("voice", "all"):
        log.info("=== Enhancing voice request scripts ===")
        total += enhance_voice_scripts(_get_module_model("voice"), args.dry_run)

    if args.module in ("call", "all"):
        log.info("=== Enhancing call request scripts ===")
        total += enhance_call_scripts(_get_module_model("call"), args.dry_run)

    if args.module in ("task_manager", "all"):
        log.info("=== Enhancing task manager scripts ===")
        total += enhance_task_manager_scripts(_get_module_model("task_manager"), args.dry_run)

    if args.module in ("assistant", "all"):
        log.info("=== Enhancing assistant scripts ===")
        total += enhance_assistant_scripts(_get_module_model("assistant"), args.dry_run)

    log.info("Done! Enhanced %d scripts total.", total)


if __name__ == "__main__":
    main()
