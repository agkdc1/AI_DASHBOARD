#!/usr/bin/env python3
"""Generate ~370 YAML test scripts for all 5 Gemini-facing modules.

Usage:
    python generate_test_data.py

Outputs YAML files to test_data/ subdirectories.
Distribution: shipping(30%), inventory(25%), orders(20%), general(15%), IT(10%)
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

OUTPUT_DIR = Path(__file__).parent / "test_data"


def write_yaml(module: str, filename: str, data: dict) -> None:
    path = OUTPUT_DIR / module / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


# ─────────────────────────────────────────────────────────────────────
# MEETING scripts (20 total: 10 JA, 3 KR, 7 mixed)
# ─────────────────────────────────────────────────────────────────────

def generate_meeting_scripts() -> None:
    # 10 Japanese meetings
    ja_meetings = [
        {
            "id": "meeting_ja_001", "name": "Inventory review meeting",
            "transcript": "[REDACTED_NAME]：今日は在庫の棚卸し結果を確認しましょう。先月末の在庫数と実際の数量に差異が5件ありました。特にSKU-A1234の部品が20個不足しています。[REDACTED_NAME]さん、来週金曜日までに原因を調査して報告してください。また、棚卸しのSOPに新しいバーコードスキャン手順を追加する必要があります。",
            "expected": {
                "action_items": {"min_count": 1},
                "decisions": {"min_count": 1, "contains_keywords": ["在庫", "棚卸し", "SKU"]},
                "doc_updates": {"min_count": 1},
            },
        },
        {
            "id": "meeting_ja_002", "name": "Shipping process meeting",
            "transcript": "[REDACTED_NAME]：ヤマト運輸の集荷時間が変更になりました。今後は15時が締め切りです。[REDACTED_NAME]さん、送り状テンプレートを更新してください。来週水曜日までにお願いします。また、佐川急便との契約更新について、[REDACTED_NAME]さんが来月15日までに見積もりを取ることになりました。",
            "expected": {
                "action_items": {"min_count": 2},
                "decisions": {"min_count": 1, "contains_keywords": ["集荷", "15時", "ヤマト"]},
                "doc_updates": {"min_count": 1},
            },
        },
        {
            "id": "meeting_ja_003", "name": "Rakuten order review",
            "transcript": "[REDACTED_NAME]：楽天の注文処理フローを見直します。先週のクレーム3件はすべて出荷遅延が原因でした。対策として、注文確認メールの自動送信を導入します。[REDACTED_NAME]さん、APIの設定を来週月曜日までに完了してください。価格改定についても議論し、5%値上げで合意しました。",
            "expected": {
                "action_items": {"min_count": 1},
                "decisions": {"min_count": 1, "contains_keywords": ["楽天", "注文", "値上げ"]},
                "doc_updates": {"min_count": 0},
            },
        },
        {
            "id": "meeting_ja_004", "name": "IT infrastructure review",
            "transcript": "[REDACTED_NAME]：サーバーのディスク使用率が85%に達しています。来月までにストレージを拡張する必要があります。[REDACTED_NAME]さん、見積もりを今週中に取ってください。また、バックアップスケジュールを毎日から毎時に変更することを決定しました。運用マニュアルの更新が必要です。",
            "expected": {
                "action_items": {"min_count": 1},
                "decisions": {"min_count": 1, "contains_keywords": ["バックアップ", "ストレージ"]},
                "doc_updates": {"min_count": 1},
            },
        },
        {
            "id": "meeting_ja_005", "name": "New product launch planning",
            "transcript": "[REDACTED_NAME]：新商品NP-2026の発売準備について。在庫管理システムに新しいカテゴリーを作成する必要があります。[REDACTED_NAME]さん、InvenTreeの設定を来週金曜日までにお願いします。商品写真の撮影は[REDACTED_NAME]さんが担当で、今月末までに完了予定です。価格は3,500円で確定しました。",
            "expected": {
                "action_items": {"min_count": 2},
                "decisions": {"min_count": 1, "contains_keywords": ["新商品", "NP-2026", "3,500"]},
                "doc_updates": {"min_count": 0},
            },
        },
        {
            "id": "meeting_ja_006", "name": "Quarterly supplier review",
            "transcript": "[REDACTED_NAME]：今四半期のサプライヤー評価を行います。A社の納期遵守率は95%で良好です。B社は80%に低下しています。B社への改善要求書を[REDACTED_NAME]さんが来週までに作成してください。また、新規サプライヤーC社の見積もりを検討し、試験発注を行うことに決定しました。サプライヤー管理SOPにC社の情報を追加してください。",
            "expected": {
                "action_items": {"min_count": 2},
                "decisions": {"min_count": 1, "contains_keywords": ["サプライヤー", "C社", "試験発注"]},
                "doc_updates": {"min_count": 1},
            },
        },
        {
            "id": "meeting_ja_007", "name": "Warehouse layout optimization",
            "transcript": "[REDACTED_NAME]：倉庫のレイアウト変更について。A棟の出荷エリアを拡大し、B棟に検品スペースを新設します。[REDACTED_NAME]さん、レイアウト図面を来月5日までに作成してください。作業手順書の全面改訂が必要になります。移動は来月20日の休業日に実施する予定です。",
            "expected": {
                "action_items": {"min_count": 1},
                "decisions": {"min_count": 1, "contains_keywords": ["レイアウト", "倉庫", "A棟"]},
                "doc_updates": {"min_count": 1},
            },
        },
        {
            "id": "meeting_ja_008", "name": "Return processing review",
            "transcript": "[REDACTED_NAME]：返品処理のフローを効率化します。現在平均3日かかっている処理を1日以内に短縮します。InvenTreeのステータス変更を自動化する方針で合意しました。[REDACTED_NAME]さん、プラグインの開発を今月末までに完了してください。返品理由コードの新しいマスターデータも作成が必要です。",
            "expected": {
                "action_items": {"min_count": 1},
                "decisions": {"min_count": 1, "contains_keywords": ["返品", "自動化", "1日以内"]},
                "doc_updates": {"min_count": 0},
            },
        },
        {
            "id": "meeting_ja_009", "name": "Safety and compliance meeting",
            "transcript": "[REDACTED_NAME]：安全衛生委員会の報告です。先月のヒヤリハットが2件ありました。フォークリフト作業エリアの表示を更新します。[REDACTED_NAME]さん、安全マニュアルの改訂を来週末までにお願いします。避難経路図も新レイアウトに合わせて更新する必要があります。次回の避難訓練は来月15日に実施します。",
            "expected": {
                "action_items": {"min_count": 1},
                "decisions": {"min_count": 1, "contains_keywords": ["安全", "避難", "フォークリフト"]},
                "doc_updates": {"min_count": 1},
            },
        },
        {
            "id": "meeting_ja_010", "name": "Customer service improvement",
            "transcript": "[REDACTED_NAME]：カスタマーサービスの応答時間を改善します。現在平均2時間の応答を30分以内にする目標を設定しました。FAQデータベースを構築して、よくある質問への回答を自動化します。[REDACTED_NAME]さん、FAQ一覧を来週水曜日までに作成してください。対応マニュアルの「よくある質問」セクションも更新が必要です。",
            "expected": {
                "action_items": {"min_count": 1},
                "decisions": {"min_count": 1, "contains_keywords": ["応答時間", "FAQ", "30分"]},
                "doc_updates": {"min_count": 1},
            },
        },
    ]

    for m in ja_meetings:
        write_yaml("meeting", f"{m['id']}.yaml", {
            "id": m["id"],
            "name": m["name"],
            "language": "ja-JP",
            "transcript": m["transcript"],
            "expected": m["expected"],
        })

    # 3 Korean meetings
    kr_meetings = [
        {
            "id": "meeting_kr_001", "name": "재고 점검 회의",
            "transcript": "[REDACTED_NAME]：오늘은 재고 실사 결과를 확인하겠습니다. 지난달 말 재고 수량과 실제 수량에 차이가 3건 있었습니다. 특히 SKU-B5678 부품이 15개 부족합니다. [REDACTED_NAME]씨, 다음주 금요일까지 원인을 조사해서 보고해 주세요. 또한 재고 실사 매뉴얼에 새로운 바코드 스캔 절차를 추가해야 합니다.",
            "expected": {
                "action_items": {"min_count": 1},
                "decisions": {"min_count": 1, "contains_keywords": ["재고", "SKU", "실사"]},
                "doc_updates": {"min_count": 1},
            },
        },
        {
            "id": "meeting_kr_002", "name": "배송 프로세스 회의",
            "transcript": "[REDACTED_NAME]：택배 집하 시간이 변경되었습니다. 앞으로 오후 4시가 마감입니다. [REDACTED_NAME]씨, 운송장 템플릿을 업데이트해 주세요. 다음주 수요일까지 부탁합니다. 또한 새로운 배송 업체와의 계약에 대해 [REDACTED_NAME]씨가 다음달 10일까지 견적을 받기로 했습니다.",
            "expected": {
                "action_items": {"min_count": 2},
                "decisions": {"min_count": 1, "contains_keywords": ["집하", "4시", "배송"]},
                "doc_updates": {"min_count": 1},
            },
        },
        {
            "id": "meeting_kr_003", "name": "주문 처리 개선 회의",
            "transcript": "[REDACTED_NAME]：라쿠텐 주문 처리 흐름을 검토합니다. 지난주 클레임 2건은 모두 출하 지연이 원인이었습니다. 대책으로 주문 확인 메일의 자동 발송을 도입합니다. [REDACTED_NAME]씨, API 설정을 다음주 월요일까지 완료해 주세요.",
            "expected": {
                "action_items": {"min_count": 1},
                "decisions": {"min_count": 1, "contains_keywords": ["라쿠텐", "주문", "자동"]},
                "doc_updates": {"min_count": 0},
            },
        },
    ]

    for m in kr_meetings:
        write_yaml("meeting", f"{m['id']}.yaml", {
            "id": m["id"],
            "name": m["name"],
            "language": "ko-KR",
            "transcript": m["transcript"],
            "expected": m["expected"],
        })

    # 7 Mixed meetings (JA+KR speakers)
    mixed_meetings = [
        {
            "id": "meeting_mix_001", "name": "Cross-team shipping coordination",
            "transcript": "[REDACTED_NAME]：本日の出荷調整会議を始めます。来週の大型出荷について確認します。\n[REDACTED_NAME]：네, 다음주 화요일에 대량 출하가 예정되어 있습니다. 약 200건입니다.\n[REDACTED_NAME]：200件ですね。ヤマト運輸に追加の集荷を依頼する必要があります。[REDACTED_NAME]さん、今週中に手配をお願いします。\n[REDACTED_NAME]：알겠습니다. 금요일까지 배송 스케줄을 확정하겠습니다.\n[REDACTED_NAME]：出荷手順書に大型出荷時の追加手順を記載しましょう。",
            "expected": {
                "action_items": {"min_count": 1},
                "decisions": {"min_count": 1, "contains_keywords": ["出荷", "200", "출하"]},
                "doc_updates": {"min_count": 1},
            },
        },
        {
            "id": "meeting_mix_002", "name": "Inventory count discrepancy review",
            "transcript": "[REDACTED_NAME]：재고 차이에 대해 논의하겠습니다.\n[REDACTED_NAME]：はい、先月のデータを見ると、カテゴリーCで10%の誤差があります。\n[REDACTED_NAME]：카테고리 C의 오차가 크네요. 원인을 조사해야 합니다.\n[REDACTED_NAME]：[REDACTED_NAME]さんと[REDACTED_NAME]さんで来週までに現物確認をお願いします。\n[REDACTED_NAME]：네, 다음주 목요일까지 결과를 보고하겠습니다. 재고 관리 매뉴얼도 업데이트가 필요합니다.",
            "expected": {
                "action_items": {"min_count": 1},
                "decisions": {"min_count": 1, "contains_keywords": ["カテゴリー", "재고", "10%"]},
                "doc_updates": {"min_count": 1},
            },
        },
        {
            "id": "meeting_mix_003", "name": "New marketplace onboarding",
            "transcript": "[REDACTED_NAME]：新しいマーケットプレイスへの出店について。Yahoo!ショッピングに出店することが決まりました。\n[REDACTED_NAME]：야후 쇼핑 입점 일정은 어떻게 되나요？\n[REDACTED_NAME]：来月15日を目標にしています。[REDACTED_NAME]さん、商品データの準備を来週金曜日までにお願いします。\n[REDACTED_NAME]：상품 데이터 준비하겠습니다. 야후 쇼핑 출품 매뉴얼도 만들어야 합니다.",
            "expected": {
                "action_items": {"min_count": 1},
                "decisions": {"min_count": 1, "contains_keywords": ["Yahoo", "마켓플레이스", "出店"]},
                "doc_updates": {"min_count": 1},
            },
        },
        {
            "id": "meeting_mix_004", "name": "Quality control improvements",
            "transcript": "[REDACTED_NAME]：品質管理の改善について議論します。先月の不良品率は0.5%でした。\n[REDACTED_NAME]：0.5%는 목표치보다 높습니다. 개선이 필요합니다.\n[REDACTED_NAME]：検品基準を厳格化して、0.3%以下を目標にします。\n[REDACTED_NAME]：검품 체크리스트를 업데이트하겠습니다. 다음주 수요일까지 완료하겠습니다.\n[REDACTED_NAME]：品質管理マニュアルの改訂もお願いします。",
            "expected": {
                "action_items": {"min_count": 1},
                "decisions": {"min_count": 1, "contains_keywords": ["品質", "불량", "0.3%"]},
                "doc_updates": {"min_count": 1},
            },
        },
        {
            "id": "meeting_mix_005", "name": "System migration planning",
            "transcript": "[REDACTED_NAME]：시스템 마이그레이션 계획에 대해 논의합니다.\n[REDACTED_NAME]：K8sクラスターへの移行は来月から開始する予定です。\n[REDACTED_NAME]：마이그레이션 일정을 구체적으로 정해야 합니다.\n[REDACTED_NAME]：まず、テスト環境を今月末までに構築します。[REDACTED_NAME]さん、テスト計画書を来週までに作成してください。\n[REDACTED_NAME]：운영 매뉴얼도 새 시스템에 맞게 업데이트해야 합니다.",
            "expected": {
                "action_items": {"min_count": 1},
                "decisions": {"min_count": 1, "contains_keywords": ["マイグレーション", "K8s", "테스트"]},
                "doc_updates": {"min_count": 1},
            },
        },
        {
            "id": "meeting_mix_006", "name": "Customer complaint analysis",
            "transcript": "[REDACTED_NAME]：今月のクレーム分析を行います。合計8件のクレームがありました。\n[REDACTED_NAME]：8건 중 5건이 배송 관련이고, 3건이 상품 품질 관련입니다.\n[REDACTED_NAME]：配送関連の対策として、出荷前チェックリストを導入します。\n[REDACTED_NAME]：체크리스트 초안을 다음주까지 준비하겠습니다.\n[REDACTED_NAME]：クレーム対応手順書も改訂が必要です。エスカレーション基準を明確にしましょう。",
            "expected": {
                "action_items": {"min_count": 1},
                "decisions": {"min_count": 1, "contains_keywords": ["クレーム", "배송", "チェックリスト"]},
                "doc_updates": {"min_count": 1},
            },
        },
        {
            "id": "meeting_mix_007", "name": "Annual planning kickoff",
            "transcript": "[REDACTED_NAME]：来年度の事業計画のキックオフミーティングです。\n[REDACTED_NAME]：내년 매출 목표는 전년 대비 120%입니다.\n[REDACTED_NAME]：売上目標達成のために、3つの施策を実施します。新商品投入、マーケットプレイス拡大、業務効率化です。\n[REDACTED_NAME]：각 시책의 상세 계획을 다음달 10일까지 작성해 주세요.\n[REDACTED_NAME]：年度計画の文書を作成し、全社に共有する必要があります。",
            "expected": {
                "action_items": {"min_count": 1},
                "decisions": {"min_count": 1, "contains_keywords": ["事業計画", "120%", "매출"]},
                "doc_updates": {"min_count": 1},
            },
        },
    ]

    for m in mixed_meetings:
        write_yaml("meeting", f"{m['id']}.yaml", {
            "id": m["id"],
            "name": m["name"],
            "language": "mixed",
            "transcript": m["transcript"],
            "expected": m["expected"],
        })


# ─────────────────────────────────────────────────────────────────────
# VOICE REQUEST scripts (100 total: 60 JA, 40 KR)
# ─────────────────────────────────────────────────────────────────────

def generate_voice_scripts() -> None:
    # ── Japanese templates ──
    ja_shipping = [
        ("注文番号SO-{so}の商品を今日中に発送してください。ヤマト運輸の着払いでお願いします。", ["SO-{so}", "発送"], True, [3, 4]),
        ("SO-{so}の出荷準備ができました。送り状を印刷して、{hour}時の集荷に間に合わせてください。", ["SO-{so}", "送り状"], True, [2, 3]),
        ("[REDACTED_NAME]様宛ての商品を佐川急便で発送してください。追跡番号は後で連絡します。", ["発送", "佐川"], False, [2, 3]),
        ("返品商品RMA-{rma}を受け取りました。検品して在庫に戻してください。", ["RMA-{rma}", "返品"], False, [2, 3]),
        ("本日の出荷リストを確認して、未出荷の注文があれば報告してください。", ["出荷", "未出荷"], True, [2, 3]),
        ("急ぎでSO-{so}を発送してください。お客様からクレームが来ています。", ["SO-{so}", "発送"], True, [4, 4]),
    ]

    ja_inventory = [
        ("部品P-{part}の在庫が残り{qty}個になりました。発注をお願いします。", ["P-{part}", "在庫"], True, [2, 3]),
        ("倉庫Aの棚卸しを来週月曜日までに完了してください。", ["棚卸し"], True, [2, 3]),
        ("SKU-{sku}のロット番号{lot}に不良が見つかりました。出荷を停止してください。", ["SKU-{sku}", "不良"], False, [4, 4]),
        ("新しい部品カテゴリー「電子部品-コネクタ」をInvenTreeに追加してください。", ["カテゴリー", "InvenTree"], False, [1, 2]),
        ("在庫移動：A棟からB棟へ、P-{part}を{qty}個移動してください。", ["在庫移動", "P-{part}"], False, [2, 3]),
    ]

    ja_orders = [
        ("楽天から新規注文{order}件が入っています。確認して処理を開始してください。", ["楽天", "注文"], True, [3, 4]),
        ("Amazon注文{order}の支払い確認が取れました。出荷準備をお願いします。", ["Amazon", "注文"], False, [2, 3]),
        ("Qoo10の注文SO-{so}をキャンセル処理してください。お客様都合です。", ["Qoo10", "キャンセル"], False, [2, 3]),
        ("Yahoo注文の処理状況を確認して、遅延しているものがあれば教えてください。", ["Yahoo", "注文"], True, [2, 3]),
    ]

    ja_general = [
        ("明日の朝礼で使う資料を準備してください。売上データと在庫サマリーが必要です。", ["資料", "売上"], True, [2, 3]),
        ("新入社員の[REDACTED_NAME]さんのアカウント設定をお願いします。メールとInvenTreeのアクセス権が必要です。", ["アカウント", "設定"], True, [2, 3]),
        ("来月の出張スケジュールを調整してください。[REDACTED_ADDRESS]の取引先を訪問予定です。", ["出張", "スケジュール"], True, [1, 2]),
    ]

    ja_it = [
        ("プリンターの紙詰まりが頻発しています。メンテナンスを手配してください。", ["プリンター", "メンテナンス"], True, [2, 3]),
        ("バックアップの確認をお願いします。昨夜のジョブが失敗しているようです。", ["バックアップ", "確認"], True, [3, 4]),
    ]

    # Parameters for variation
    sos = ["2024-1234", "2024-5678", "2025-0001", "2025-0123", "2026-0456", "2026-0789"]
    parts = ["A1234", "B5678", "C9012", "D3456", "E7890"]
    skus = ["X100", "Y200", "Z300", "W400", "V500"]
    rmas = ["001", "002", "003", "004"]
    lots = ["L20260101", "L20260215", "L20260301"]
    qtys = ["5", "10", "20", "50", "100"]
    hours = ["14", "15", "16"]
    orders = ["3", "5", "8", "12"]

    idx = 1
    for template_list, category in [
        (ja_shipping, "shipping"),
        (ja_inventory, "inventory"),
        (ja_orders, "orders"),
        (ja_general, "general"),
        (ja_it, "it"),
    ]:
        for tpl, keywords, has_due, pri_range in template_list:
            # Generate 2-3 variations per template
            for var_idx in range(min(3, max(2, 60 // (len(ja_shipping) + len(ja_inventory) + len(ja_orders) + len(ja_general) + len(ja_it))))):
                text = tpl.format(
                    so=sos[var_idx % len(sos)],
                    part=parts[var_idx % len(parts)],
                    sku=skus[var_idx % len(skus)],
                    rma=rmas[var_idx % len(rmas)],
                    lot=lots[var_idx % len(lots)],
                    qty=qtys[var_idx % len(qtys)],
                    hour=hours[var_idx % len(hours)],
                    order=orders[var_idx % len(orders)],
                )
                resolved_kw = [k.format(
                    so=sos[var_idx % len(sos)],
                    part=parts[var_idx % len(parts)],
                    sku=skus[var_idx % len(skus)],
                    rma=rmas[var_idx % len(rmas)],
                ) for k in keywords]

                write_yaml("voice_request", f"voice_ja_{idx:03d}.yaml", {
                    "id": f"voice_ja_{idx:03d}",
                    "name": f"JA voice {category} #{idx}",
                    "language": "ja-JP",
                    "text": text,
                    "expected": {
                        "valid_json_keys": ["title", "description", "due_date", "priority", "missing_details"],
                        "title_contains": resolved_kw,
                        "due_date_present": has_due,
                        "priority_range": pri_range,
                    },
                })
                idx += 1
                if idx > 60:
                    break
            if idx > 60:
                break
        if idx > 60:
            break

    # ── Korean templates ──
    kr_shipping = [
        ("주문번호 SO-{so} 상품을 오늘 중으로 발송해 주세요. 야마토 운수 착불로 부탁합니다.", ["SO-{so}", "발송"], True, [3, 4]),
        ("SO-{so} 출하 준비가 완료되었습니다. 운송장을 출력해 주세요.", ["SO-{so}", "운송장"], True, [2, 3]),
        ("[REDACTED_NAME]님 앞으로 상품을 사가와 택배로 발송해 주세요.", ["발송", "사가와"], False, [2, 3]),
        ("반품 상품 RMA-{rma}을 수령했습니다. 검품 후 재고에 반영해 주세요.", ["RMA-{rma}", "반품"], False, [2, 3]),
        ("오늘 출하 목록을 확인하고, 미출하 주문이 있으면 보고해 주세요.", ["출하", "미출하"], True, [2, 3]),
        ("급하게 SO-{so}를 발송해 주세요. 고객 클레임이 들어왔습니다.", ["SO-{so}", "발송"], True, [4, 4]),
    ]

    kr_inventory = [
        ("부품 P-{part} 재고가 {qty}개 남았습니다. 발주를 부탁합니다.", ["P-{part}", "재고"], True, [2, 3]),
        ("창고 A의 재고 실사를 다음주 월요일까지 완료해 주세요.", ["재고 실사"], True, [2, 3]),
        ("SKU-{sku} 로트번호 {lot}에서 불량이 발견되었습니다. 출하를 중지해 주세요.", ["SKU-{sku}", "불량"], False, [4, 4]),
        ("새로운 부품 카테고리 '전자부품-커넥터'를 InvenTree에 추가해 주세요.", ["카테고리", "InvenTree"], False, [1, 2]),
    ]

    kr_orders = [
        ("라쿠텐에서 신규 주문 {order}건이 들어왔습니다. 확인하고 처리를 시작해 주세요.", ["라쿠텐", "주문"], True, [3, 4]),
        ("아마존 주문의 결제 확인이 되었습니다. 출하 준비를 부탁합니다.", ["아마존", "출하"], False, [2, 3]),
    ]

    kr_general = [
        ("내일 조회에서 사용할 자료를 준비해 주세요. 매출 데이터와 재고 요약이 필요합니다.", ["자료", "매출"], True, [2, 3]),
        ("신입사원 [REDACTED_NAME]씨의 계정 설정을 부탁합니다. 이메일과 InvenTree 접근 권한이 필요합니다.", ["계정", "설정"], True, [2, 3]),
    ]

    kr_it = [
        ("프린터 용지 걸림이 자주 발생합니다. 정비를 요청해 주세요.", ["프린터", "정비"], True, [2, 3]),
        ("백업 확인을 부탁합니다. 어젯밤 작업이 실패한 것 같습니다.", ["백업", "확인"], True, [3, 4]),
    ]

    kr_idx = 1
    for template_list, category in [
        (kr_shipping, "shipping"),
        (kr_inventory, "inventory"),
        (kr_orders, "orders"),
        (kr_general, "general"),
        (kr_it, "it"),
    ]:
        for tpl, keywords, has_due, pri_range in template_list:
            for var_idx in range(min(3, max(2, 40 // (len(kr_shipping) + len(kr_inventory) + len(kr_orders) + len(kr_general) + len(kr_it))))):
                text = tpl.format(
                    so=sos[var_idx % len(sos)],
                    part=parts[var_idx % len(parts)],
                    sku=skus[var_idx % len(skus)],
                    rma=rmas[var_idx % len(rmas)],
                    lot=lots[var_idx % len(lots)],
                    qty=qtys[var_idx % len(qtys)],
                    order=orders[var_idx % len(orders)],
                )
                resolved_kw = [k.format(
                    so=sos[var_idx % len(sos)],
                    part=parts[var_idx % len(parts)],
                    sku=skus[var_idx % len(skus)],
                    rma=rmas[var_idx % len(rmas)],
                ) for k in keywords]

                write_yaml("voice_request", f"voice_kr_{kr_idx:03d}.yaml", {
                    "id": f"voice_kr_{kr_idx:03d}",
                    "name": f"KR voice {category} #{kr_idx}",
                    "language": "ko-KR",
                    "text": text,
                    "expected": {
                        "valid_json_keys": ["title", "description", "due_date", "priority", "missing_details"],
                        "title_contains": resolved_kw,
                        "due_date_present": has_due,
                        "priority_range": pri_range,
                    },
                })
                kr_idx += 1
                if kr_idx > 40:
                    break
            if kr_idx > 40:
                break
        if kr_idx > 40:
            break


# ─────────────────────────────────────────────────────────────────────
# CALL REQUEST scripts (100 total: 60 JA, 40 KR)
# ─────────────────────────────────────────────────────────────────────

def generate_call_scripts() -> None:
    ja_call_transcripts = [
        ("もしもし、[REDACTED_NAME]です。注文SO-{so}の件でお電話しました。この注文、今日中に出荷できますか？はい、了解しました。では15時の集荷に間に合わせてください。送り先は[REDACTED_ADDRESS]です。よろしくお願いします。", ["SO-{so}", "出荷"], True, [3, 4], True),
        ("お疲れ様です。在庫の件なんですが、部品P-{part}の在庫が少なくなっています。残り{qty}個です。来週までに{qty2}個追加発注をお願いしたいのですが。はい、わかりました。では発注書を作成してください。", ["P-{part}", "在庫"], True, [2, 3], True),
        ("[REDACTED_NAME]さん、楽天の注文処理について相談があります。最近クレームが増えているので、処理フローを見直したいと思います。来週のミーティングで議論しましょう。事前に現状の問題点をまとめておいてください。", ["楽天", "注文"], True, [2, 3], True),
        ("はい、[REDACTED_NAME]です。返品の件でご連絡です。RMA-{rma}の商品を確認しましたが、外装に損傷がありました。返金処理を進めてよろしいでしょうか。はい、では返金処理を行います。報告書も作成してください。", ["RMA-{rma}", "返品"], True, [2, 3], True),
        ("お世話になっております。サーバーのメンテナンスについてですが、来週の土曜日に実施する予定です。その間、システムが数時間停止します。事前にユーザーへの通知をお願いします。", ["メンテナンス", "サーバー"], True, [2, 3], True),
        ("もしもし、送り状の件です。本日の出荷分で3件のエラーが出ています。住所不備が原因のようです。確認して修正をお願いします。急ぎで対応してください。", ["送り状", "エラー"], True, [3, 4], True),
        ("お疲れ様です。新商品NP-{np}の在庫登録について。InvenTreeに新カテゴリーを作成して、初回ロット{qty}個を登録してください。来週月曜の朝までにお願いします。", ["NP-{np}", "在庫登録"], True, [2, 3], True),
        ("[REDACTED_NAME]さん、フォークリフトの定期点検の件です。来月の初めに業者が来ます。事前に点検リストを確認して、故障箇所があれば報告してください。", ["フォークリフト", "点検"], True, [1, 2], True),
        ("緊急です。SKU-{sku}の不良品が出荷されてしまいました。すぐに出荷停止して、お客様に連絡してください。代替品の手配もお願いします。", ["SKU-{sku}", "不良品"], False, [4, 4], True),
        ("来月の棚卸しスケジュールの件です。A棟は月曜、B棟は火曜で進めます。担当者の割り当てを来週金曜日までに決めてください。棚卸しマニュアルの更新も必要です。", ["棚卸し", "スケジュール"], True, [2, 3], True),
    ]

    kr_call_transcripts = [
        ("여보세요, [REDACTED_NAME]입니다. 주문 SO-{so} 건으로 전화드렸습니다. 이 주문 오늘 중으로 출하 가능한가요? 네, 알겠습니다. 그러면 오후 3시 집하에 맞춰 주세요.", ["SO-{so}", "출하"], True, [3, 4], True),
        ("수고하십니다. 재고 건인데요, 부품 P-{part} 재고가 줄어들고 있습니다. 남은 수량이 {qty}개입니다. 다음주까지 추가 발주를 부탁드립니다.", ["P-{part}", "재고"], True, [2, 3], True),
        ("[REDACTED_NAME]씨, 라쿠텐 주문 처리에 대해 상담이 있습니다. 최근 클레임이 늘어나고 있어서 처리 흐름을 재검토하고 싶습니다. 다음주 미팅에서 논의합시다.", ["라쿠텐", "주문"], True, [2, 3], True),
        ("네, [REDACTED_NAME]입니다. 반품 건으로 연락드립니다. RMA-{rma} 상품을 확인했는데 외장에 손상이 있었습니다. 환불 처리를 진행해도 될까요? 네, 그러면 환불 처리하겠습니다.", ["RMA-{rma}", "반품"], True, [2, 3], True),
        ("서버 유지보수 건인데요, 다음주 토요일에 실시할 예정입니다. 그 동안 시스템이 몇 시간 정지됩니다. 사용자에게 사전 공지를 부탁드립니다.", ["유지보수", "서버"], True, [2, 3], True),
        ("여보세요, 운송장 건입니다. 오늘 출하분에서 2건의 오류가 발생했습니다. 주소 불비가 원인인 것 같습니다. 확인하고 수정을 부탁합니다.", ["운송장", "오류"], True, [3, 4], True),
        ("신상품 NP-{np}의 재고 등록에 대해서요. InvenTree에 새 카테고리를 만들고 초회 로트 {qty}개를 등록해 주세요.", ["NP-{np}", "재고 등록"], True, [2, 3], True),
        ("긴급입니다. SKU-{sku} 불량품이 출하되었습니다. 즉시 출하를 중지하고 고객에게 연락해 주세요. 대체품 수배도 부탁합니다.", ["SKU-{sku}", "불량품"], False, [4, 4], True),
    ]

    sos = ["2024-1234", "2024-5678", "2025-0001", "2025-0123", "2026-0456", "2026-0789"]
    parts = ["A1234", "B5678", "C9012", "D3456", "E7890"]
    skus = ["X100", "Y200", "Z300", "W400"]
    rmas = ["001", "002", "003"]
    nps = ["2026", "2027", "2028"]
    qtys = ["10", "20", "50"]
    qty2s = ["50", "100", "200"]

    # Generate JA calls
    idx = 1
    for tpl, keywords, has_due, pri_range, has_decisions in ja_call_transcripts:
        for var_idx in range(min(6, max(2, 60 // len(ja_call_transcripts)))):
            text = tpl.format(
                so=sos[var_idx % len(sos)],
                part=parts[var_idx % len(parts)],
                sku=skus[var_idx % len(skus)],
                rma=rmas[var_idx % len(rmas)],
                np=nps[var_idx % len(nps)],
                qty=qtys[var_idx % len(qtys)],
                qty2=qty2s[var_idx % len(qty2s)],
            )
            resolved_kw = [k.format(
                so=sos[var_idx % len(sos)],
                part=parts[var_idx % len(parts)],
                sku=skus[var_idx % len(skus)],
                rma=rmas[var_idx % len(rmas)],
                np=nps[var_idx % len(nps)],
            ) for k in keywords]

            write_yaml("call_request", f"call_ja_{idx:03d}.yaml", {
                "id": f"call_ja_{idx:03d}",
                "name": f"JA call #{idx}",
                "language": "ja-JP",
                "text": text,
                "expected": {
                    "valid_json_keys": ["title", "description", "due_date", "priority", "decisions"],
                    "title_contains": resolved_kw,
                    "due_date_present": has_due,
                    "priority_range": pri_range,
                    "has_decisions": has_decisions,
                },
            })
            idx += 1
            if idx > 60:
                break
        if idx > 60:
            break

    # Generate KR calls
    kr_idx = 1
    for tpl, keywords, has_due, pri_range, has_decisions in kr_call_transcripts:
        for var_idx in range(min(5, max(2, 40 // len(kr_call_transcripts)))):
            text = tpl.format(
                so=sos[var_idx % len(sos)],
                part=parts[var_idx % len(parts)],
                sku=skus[var_idx % len(skus)],
                rma=rmas[var_idx % len(rmas)],
                np=nps[var_idx % len(nps)],
                qty=qtys[var_idx % len(qtys)],
            )
            resolved_kw = [k.format(
                so=sos[var_idx % len(sos)],
                part=parts[var_idx % len(parts)],
                sku=skus[var_idx % len(skus)],
                rma=rmas[var_idx % len(rmas)],
                np=nps[var_idx % len(nps)],
            ) for k in keywords]

            write_yaml("call_request", f"call_kr_{kr_idx:03d}.yaml", {
                "id": f"call_kr_{kr_idx:03d}",
                "name": f"KR call #{kr_idx}",
                "language": "ko-KR",
                "text": text,
                "expected": {
                    "valid_json_keys": ["title", "description", "due_date", "priority", "decisions"],
                    "title_contains": resolved_kw,
                    "due_date_present": has_due,
                    "priority_range": pri_range,
                    "has_decisions": has_decisions,
                },
            })
            kr_idx += 1
            if kr_idx > 40:
                break
        if kr_idx > 40:
            break


# ─────────────────────────────────────────────────────────────────────
# ASSISTANT scripts (100 total: 60 JA, 40 KR)
# ─────────────────────────────────────────────────────────────────────

def generate_assistant_scripts() -> None:
    ja_questions = [
        # InvenTree (15)
        ("InvenTreeで部品を検索するにはどうすればいいですか？", "ja", ["検索", "部品", "フィルター"], ["実行しました", "削除しました"], 50),
        ("InvenTreeで新しい部品を登録する手順を教えてください。", "ja", ["登録", "部品", "カテゴリー"], ["実行しました"], 80),
        ("在庫の棚卸し作業をInvenTreeで行う方法を教えてください。", "ja", ["棚卸し", "在庫", "カウント"], ["実行しました"], 80),
        ("InvenTreeで発注書を作成する方法は？", "ja", ["発注", "注文", "サプライヤー"], ["実行しました"], 60),
        ("InvenTreeの在庫移動はどうやりますか？", "ja", ["在庫", "移動", "ロケーション"], ["実行しました"], 50),
        ("部品カテゴリーの追加方法を教えてください。", "ja", ["カテゴリー", "追加", "設定"], ["実行しました"], 50),
        ("InvenTreeのラベル印刷の設定方法は？", "ja", ["ラベル", "印刷", "設定"], ["実行しました"], 50),
        ("InvenTreeでBOM（部品表）を作成する方法を教えてください。", "ja", ["BOM", "部品表", "構成"], ["実行しました"], 60),
        # Shipping (10)
        ("ヤマト運輸の送り状を作成する方法を教えてください。", "ja", ["ヤマト", "送り状", "作成"], ["実行しました"], 60),
        ("佐川急便の集荷依頼の手順は？", "ja", ["佐川", "集荷", "依頼"], ["実行しました"], 50),
        ("送り状の印刷でエラーが出ます。どうすればいいですか？", "ja", ["送り状", "印刷", "エラー"], ["実行しました"], 50),
        ("着払い伝票の作成方法を教えてください。", "ja", ["着払い", "伝票", "作成"], ["実行しました"], 50),
        # Vikunja (8)
        ("Vikunjaでタスクを作成する方法を教えてください。", "ja", ["Vikunja", "タスク", "作成"], ["実行しました"], 50),
        ("Vikunjaでプロジェクトの進捗を確認する方法は？", "ja", ["Vikunja", "プロジェクト", "進捗"], ["実行しました"], 50),
        ("タスクに期限を設定する方法を教えてください。", "ja", ["期限", "設定", "タスク"], ["実行しました"], 50),
        ("Vikunjaでラベルを使ってタスクを分類する方法は？", "ja", ["ラベル", "分類", "タスク"], ["実行しました"], 50),
        # Outline (5)
        ("Outlineでドキュメントを検索する方法は？", "ja", ["Outline", "ドキュメント", "検索"], ["実行しました"], 50),
        ("Outlineで新しいドキュメントを作成するにはどうしますか？", "ja", ["Outline", "ドキュメント", "作成"], ["実行しました"], 50),
        ("SOPマニュアルの更新方法を教えてください。", "ja", ["SOP", "マニュアル", "更新"], ["実行しました"], 50),
        # Rakuten (5)
        ("楽天の受注処理フローを教えてください。", "ja", ["楽天", "受注", "処理"], ["実行しました"], 60),
        ("楽天のAPIキーの更新手順は？", "ja", ["楽天", "API", "キー", "更新"], ["実行しました"], 50),
        ("楽天の注文で住所不備のエラーが出たときの対処法は？", "ja", ["楽天", "住所", "エラー"], ["実行しました"], 50),
        # General (7)
        ("新入社員のアカウント設定手順を教えてください。", "ja", ["アカウント", "設定", "手順"], ["実行しました"], 60),
        ("パスワードのリセット方法を教えてください。", "ja", ["パスワード", "リセット"], ["実行しました"], 50),
        ("共有フォルダへのアクセス方法は？", "ja", ["共有", "フォルダ", "アクセス"], ["実行しました"], 50),
        ("電話の内線番号の設定方法は？", "ja", ["電話", "内線", "設定"], ["実行しました"], 50),
        ("VPNの接続方法を教えてください。", "ja", ["VPN", "接続"], ["実行しました"], 50),
        ("請求書の作成手順を教えてください。", "ja", ["請求書", "作成", "手順"], ["実行しました"], 60),
        ("メールの署名を変更する方法は？", "ja", ["メール", "署名", "変更"], ["実行しました"], 50),
    ]

    kr_questions = [
        # InvenTree (10)
        ("InvenTree에서 부품을 검색하려면 어떻게 하나요?", "ko", ["검색", "부품", "필터"], ["실행했습니다", "삭제했습니다"], 50),
        ("InvenTree에서 새로운 부품을 등록하는 절차를 알려주세요.", "ko", ["등록", "부품", "카테고리"], ["실행했습니다"], 80),
        ("InvenTree에서 재고 실사를 하는 방법을 알려주세요.", "ko", ["재고 실사", "카운트"], ["실행했습니다"], 80),
        ("InvenTree에서 발주서를 작성하는 방법은?", "ko", ["발주", "주문"], ["실행했습니다"], 60),
        ("InvenTree에서 재고 이동은 어떻게 하나요?", "ko", ["재고", "이동", "위치"], ["실행했습니다"], 50),
        ("부품 카테고리 추가 방법을 알려주세요.", "ko", ["카테고리", "추가"], ["실행했습니다"], 50),
        ("InvenTree에서 라벨 인쇄 설정 방법은?", "ko", ["라벨", "인쇄", "설정"], ["실행했습니다"], 50),
        ("InvenTree에서 BOM(부품표)을 만드는 방법을 알려주세요.", "ko", ["BOM", "부품표"], ["실행했습니다"], 60),
        # Shipping (6)
        ("야마토 운수 운송장을 만드는 방법을 알려주세요.", "ko", ["야마토", "운송장"], ["실행했습니다"], 60),
        ("사가와 택배 집하 의뢰 절차는?", "ko", ["사가와", "집하"], ["실행했습니다"], 50),
        ("운송장 인쇄에서 오류가 납니다. 어떻게 하면 되나요?", "ko", ["운송장", "인쇄", "오류"], ["실행했습니다"], 50),
        ("착불 전표 작성 방법을 알려주세요.", "ko", ["착불", "전표"], ["실행했습니다"], 50),
        # Vikunja (5)
        ("Vikunja에서 작업을 만드는 방법을 알려주세요.", "ko", ["Vikunja", "작업", "만들기"], ["실행했습니다"], 50),
        ("Vikunja에서 프로젝트 진행 상황을 확인하는 방법은?", "ko", ["Vikunja", "프로젝트", "진행"], ["실행했습니다"], 50),
        ("작업에 마감일을 설정하는 방법을 알려주세요.", "ko", ["마감일", "설정"], ["실행했습니다"], 50),
        # Outline (3)
        ("Outline에서 문서를 검색하는 방법은?", "ko", ["Outline", "문서", "검색"], ["실행했습니다"], 50),
        ("Outline에서 새 문서를 만들려면 어떻게 하나요?", "ko", ["Outline", "문서", "만들기"], ["실행했습니다"], 50),
        ("SOP 매뉴얼 업데이트 방법을 알려주세요.", "ko", ["SOP", "매뉴얼", "업데이트"], ["실행했습니다"], 50),
        # Rakuten (4)
        ("라쿠텐 수주 처리 흐름을 알려주세요.", "ko", ["라쿠텐", "수주", "처리"], ["실행했습니다"], 60),
        ("라쿠텐 API 키 갱신 절차는?", "ko", ["라쿠텐", "API", "키"], ["실행했습니다"], 50),
        # General (5)
        ("신입사원 계정 설정 절차를 알려주세요.", "ko", ["계정", "설정", "절차"], ["실행했습니다"], 60),
        ("비밀번호 재설정 방법을 알려주세요.", "ko", ["비밀번호", "재설정"], ["실행했습니다"], 50),
        ("공유 폴더에 접근하는 방법은?", "ko", ["공유", "폴더", "접근"], ["실행했습니다"], 50),
        ("전화 내선번호 설정 방법은?", "ko", ["전화", "내선"], ["실행했습니다"], 50),
        ("VPN 연결 방법을 알려주세요.", "ko", ["VPN", "연결"], ["실행했습니다"], 50),
    ]

    # Generate JA scripts (60 — use duplicates with slight rephrasing suffix)
    idx = 1
    for q, lang, must_contain, must_not, min_len in ja_questions:
        write_yaml("assistant", f"asst_ja_{idx:03d}.yaml", {
            "id": f"asst_ja_{idx:03d}",
            "name": f"JA assistant #{idx}",
            "language": "ja-JP",
            "question": q,
            "expected": {
                "language": lang,
                "must_contain_any": must_contain,
                "must_not_contain": must_not,
                "min_length": min_len,
            },
        })
        idx += 1

    # Add rephrased variants to reach 60
    rephrase_suffix_ja = [
        "具体的な手順をステップで教えてください。",
        "初心者向けに簡単に説明してください。",
    ]
    base_idx = idx
    for q, lang, must_contain, must_not, min_len in ja_questions:
        for suffix in rephrase_suffix_ja:
            if idx > 60:
                break
            write_yaml("assistant", f"asst_ja_{idx:03d}.yaml", {
                "id": f"asst_ja_{idx:03d}",
                "name": f"JA assistant #{idx}",
                "language": "ja-JP",
                "question": q.rstrip("？?。") + "。" + suffix,
                "expected": {
                    "language": lang,
                    "must_contain_any": must_contain,
                    "must_not_contain": must_not,
                    "min_length": min_len,
                },
            })
            idx += 1
        if idx > 60:
            break

    # Generate KR scripts (40)
    kr_idx = 1
    for q, lang, must_contain, must_not, min_len in kr_questions:
        write_yaml("assistant", f"asst_kr_{kr_idx:03d}.yaml", {
            "id": f"asst_kr_{kr_idx:03d}",
            "name": f"KR assistant #{kr_idx}",
            "language": "ko-KR",
            "question": q,
            "expected": {
                "language": lang,
                "must_contain_any": must_contain,
                "must_not_contain": must_not,
                "min_length": min_len,
            },
        })
        kr_idx += 1

    # Add rephrased variants to reach 40
    rephrase_suffix_kr = [
        "구체적인 절차를 단계별로 알려주세요.",
        "초보자도 알기 쉽게 설명해 주세요.",
    ]
    for q, lang, must_contain, must_not, min_len in kr_questions:
        for suffix in rephrase_suffix_kr:
            if kr_idx > 40:
                break
            write_yaml("assistant", f"asst_kr_{kr_idx:03d}.yaml", {
                "id": f"asst_kr_{kr_idx:03d}",
                "name": f"KR assistant #{kr_idx}",
                "language": "ko-KR",
                "question": q.rstrip("?？。") + ". " + suffix,
                "expected": {
                    "language": lang,
                    "must_contain_any": must_contain,
                    "must_not_contain": must_not,
                    "min_length": min_len,
                },
            })
            kr_idx += 1
        if kr_idx > 40:
            break


# ─────────────────────────────────────────────────────────────────────
# TASK MANAGER scripts (50 total: 30 JA, 20 KR)
# ─────────────────────────────────────────────────────────────────────

def generate_task_manager_scripts() -> None:
    ja_tasks = [
        # Create (12)
        ("来週月曜日までに在庫レポートを作成して", "create", ["在庫", "レポート"], True, [2, 3]),
        ("今日中にSO-2024-1234の出荷作業を完了するタスクを作って", "create", ["SO-2024-1234", "出荷"], True, [3, 4]),
        ("楽天の注文処理フロー改善タスクを登録して。優先度は高で。", "create", ["楽天", "注文", "改善"], False, [3, 3]),
        ("新商品NP-2026の商品登録タスクを作成して。来月15日が期限です。", "create", ["NP-2026", "商品登録"], True, [2, 3]),
        ("倉庫Aの棚卸し準備タスクを作ってください", "create", ["棚卸し", "倉庫"], False, [2, 3]),
        ("サプライヤーB社への改善要求書を来週金曜日までに作成するタスク", "create", ["サプライヤー", "改善"], True, [2, 3]),
        ("バックアップシステムの確認タスクを作って。急ぎで。", "create", ["バックアップ", "確認"], False, [3, 4]),
        ("新入社員のアカウント設定タスクを登録して。今週中に完了。", "create", ["アカウント", "設定"], True, [2, 3]),
        ("返品処理プラグインの開発タスク。今月末まで。", "create", ["返品", "プラグイン"], True, [2, 3]),
        ("品質管理チェックリストの更新タスクを作成して", "create", ["品質管理", "チェックリスト"], False, [2, 3]),
        ("送り状テンプレートの更新タスクを作って。来週水曜まで。", "create", ["送り状", "テンプレート"], True, [2, 3]),
        ("FAQデータベースの構築タスクを登録。来週中。", "create", ["FAQ", "データベース"], True, [1, 2]),
        # Query (8)
        ("今週の未完了タスクを見せて", "query", [], False, [0, 0]),
        ("出荷関連のタスクを検索して", "query", [], False, [0, 0]),
        ("優先度が高いタスクを教えて", "query", [], False, [0, 0]),
        ("期限切れのタスクはある？", "query", [], False, [0, 0]),
        ("楽天関連のタスク一覧を表示して", "query", [], False, [0, 0]),
        ("在庫管理のタスクを検索して", "query", [], False, [0, 0]),
        ("[REDACTED_NAME]さんに割り当てられたタスクを見せて", "query", [], False, [0, 0]),
        ("今月末が期限のタスクを探して", "query", [], False, [0, 0]),
        # Update (5)
        ("タスク#123の優先度を高に変更して", "update", [], False, [0, 0]),
        ("タスク#456の期限を来週金曜日に延長して", "update", [], False, [0, 0]),
        ("タスク#789を完了にして", "update", [], False, [0, 0]),
        ("タスク#101の説明を「出荷停止対応」に更新して", "update", [], False, [0, 0]),
        ("タスク#202にラベル「急ぎ」を追加して", "update", [], False, [0, 0]),
        # Delete (5)
        ("タスク#333を削除して", "delete", [], False, [0, 0]),
        ("タスク#444を削除してください", "delete", [], False, [0, 0]),
        ("タスク#555はもう不要なので削除して", "delete", [], False, [0, 0]),
        ("タスク#666をキャンセルして", "delete", [], False, [0, 0]),
        ("タスク#777を消して", "delete", [], False, [0, 0]),
    ]

    kr_tasks = [
        # Create (8)
        ("다음주 월요일까지 재고 보고서를 작성하는 작업을 만들어 주세요", "create", ["재고", "보고서"], True, [2, 3]),
        ("오늘 중으로 SO-2024-5678 출하 작업을 완료하는 태스크를 만들어 주세요", "create", ["SO-2024-5678", "출하"], True, [3, 4]),
        ("라쿠텐 주문 처리 개선 태스크를 등록해 주세요. 우선순위 높음.", "create", ["라쿠텐", "주문", "개선"], False, [3, 3]),
        ("신상품 NP-2026 등록 태스크를 만들어 주세요. 다음달 15일이 마감입니다.", "create", ["NP-2026", "등록"], True, [2, 3]),
        ("창고 A 재고 실사 준비 태스크를 만들어 주세요", "create", ["재고 실사", "창고"], False, [2, 3]),
        ("백업 시스템 확인 태스크를 만들어 주세요. 긴급입니다.", "create", ["백업", "확인"], False, [3, 4]),
        ("신입사원 계정 설정 태스크를 등록해 주세요. 이번주 내 완료.", "create", ["계정", "설정"], True, [2, 3]),
        ("품질 관리 체크리스트 업데이트 태스크를 만들어 주세요", "create", ["품질 관리", "체크리스트"], False, [2, 3]),
        # Query (5)
        ("이번주 미완료 태스크를 보여 주세요", "query", [], False, [0, 0]),
        ("출하 관련 태스크를 검색해 주세요", "query", [], False, [0, 0]),
        ("우선순위 높은 태스크를 알려 주세요", "query", [], False, [0, 0]),
        ("마감일이 지난 태스크가 있나요?", "query", [], False, [0, 0]),
        ("라쿠텐 관련 태스크 목록을 보여 주세요", "query", [], False, [0, 0]),
        # Update (4)
        ("태스크 #123의 우선순위를 높음으로 변경해 주세요", "update", [], False, [0, 0]),
        ("태스크 #456의 마감일을 다음주 금요일로 연장해 주세요", "update", [], False, [0, 0]),
        ("태스크 #789를 완료로 처리해 주세요", "update", [], False, [0, 0]),
        ("태스크 #101의 설명을 '출하 중지 대응'으로 업데이트해 주세요", "update", [], False, [0, 0]),
        # Delete (3)
        ("태스크 #333을 삭제해 주세요", "delete", [], False, [0, 0]),
        ("태스크 #444는 더 이상 필요 없으니 삭제해 주세요", "delete", [], False, [0, 0]),
        ("태스크 #555를 취소해 주세요", "delete", [], False, [0, 0]),
    ]

    idx = 1
    for input_text, action, title_kw, has_due, pri_range in ja_tasks:
        data = {
            "id": f"task_ja_{idx:03d}",
            "name": f"JA task #{idx}",
            "language": "ja-JP",
            "input": input_text,
            "expected": {"action": action},
        }
        if title_kw:
            data["expected"]["task_title_contains"] = title_kw
        if has_due:
            data["expected"]["has_due_date"] = has_due
        if pri_range != [0, 0]:
            data["expected"]["priority_range"] = pri_range
        write_yaml("task_manager", f"task_ja_{idx:03d}.yaml", data)
        idx += 1

    kr_idx = 1
    for input_text, action, title_kw, has_due, pri_range in kr_tasks:
        data = {
            "id": f"task_kr_{kr_idx:03d}",
            "name": f"KR task #{kr_idx}",
            "language": "ko-KR",
            "input": input_text,
            "expected": {"action": action},
        }
        if title_kw:
            data["expected"]["task_title_contains"] = title_kw
        if has_due:
            data["expected"]["has_due_date"] = has_due
        if pri_range != [0, 0]:
            data["expected"]["priority_range"] = pri_range
        write_yaml("task_manager", f"task_kr_{kr_idx:03d}.yaml", data)
        kr_idx += 1


# ─────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────

def main() -> None:
    print("Generating test data...")
    generate_meeting_scripts()
    print(f"  Meeting: {len(list((OUTPUT_DIR / 'meeting').glob('*.yaml')))} scripts")
    generate_voice_scripts()
    print(f"  Voice request: {len(list((OUTPUT_DIR / 'voice_request').glob('*.yaml')))} scripts")
    generate_call_scripts()
    print(f"  Call request: {len(list((OUTPUT_DIR / 'call_request').glob('*.yaml')))} scripts")
    generate_assistant_scripts()
    print(f"  Assistant: {len(list((OUTPUT_DIR / 'assistant').glob('*.yaml')))} scripts")
    generate_task_manager_scripts()
    print(f"  Task manager: {len(list((OUTPUT_DIR / 'task_manager').glob('*.yaml')))} scripts")

    total = sum(
        len(list((OUTPUT_DIR / d).glob("*.yaml")))
        for d in ["meeting", "voice_request", "call_request", "assistant", "task_manager"]
    )
    print(f"\nTotal: {total} test scripts generated")


if __name__ == "__main__":
    main()
