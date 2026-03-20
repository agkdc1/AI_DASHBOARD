"""Japanese PII detection patterns."""

import re

# Japanese phone numbers: 0X-XXXX-XXXX, 0XX-XXX-XXXX, etc.
PHONE_PATTERN = re.compile(
    r"0\d{1,4}[-\s]?\d{1,4}[-\s]?\d{3,4}"
)

# Japanese postal codes: 〒123-4567 or 123-4567
POSTAL_PATTERN = re.compile(
    r"〒?\s?\d{3}[-\s]?\d{4}"
)

# Japanese addresses: prefectures (都道府県) + city/ward
PREFECTURE_PATTERN = re.compile(
    r"(?:東京都|北海道|(?:京都|大阪)府|.{2,3}県)"
    r"(?:[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]+"
    r"(?:市|区|町|村|郡))"
    r"[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\d\-－]+"
)

# Email addresses
EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)

# Credit card numbers (basic pattern)
CREDIT_CARD_PATTERN = re.compile(
    r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b"
)

# Tracking numbers
YAMATO_TRACKING = re.compile(r"\b\d{12}\b")  # 12-digit
JAPAN_POST_TRACKING = re.compile(r"\b[A-Z]{2}\d{9}[A-Z]{2}\b")  # EMS format

# Japanese names (common surname kanji patterns — heuristic)
# This is a simplified approach using common 2-3 char surname patterns
COMMON_SURNAMES = [
    "佐藤", "鈴木", "高橋", "田中", "伊藤", "渡辺", "山本", "中村", "小林",
    "加藤", "吉田", "山田", "佐々木", "松本", "井上", "木村", "林", "斎藤",
    "清水", "山崎", "阿部", "森", "池田", "橋本", "山口", "石川", "前田",
    "藤田", "小川", "岡田", "後藤", "長谷川", "石井", "村上", "近藤", "坂本",
    "遠藤", "藤井", "青木", "福田", "三浦", "西村", "太田", "松田", "原田",
    "岡本", "中島", "藤原", "小野", "中野", "田村", "竹内", "金子", "和田",
    "中山", "石田", "上田", "森田", "原", "柴田", "酒井", "工藤", "横山",
]

# Build a regex alternation for surname detection
_surname_alt = "|".join(re.escape(s) for s in COMMON_SURNAMES)
# Match surname + 1-2 chars (given name) with optional separator
JAPANESE_NAME_PATTERN = re.compile(
    rf"(?:{_surname_alt})[\s　]?[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]{{1,3}}"
)

# All patterns with their replacement labels
PII_PATTERNS = [
    (PHONE_PATTERN, "[REDACTED_PHONE]"),
    (EMAIL_PATTERN, "[REDACTED_EMAIL]"),
    (CREDIT_CARD_PATTERN, "[REDACTED_CARD]"),
    (POSTAL_PATTERN, "[REDACTED_POSTAL]"),
    (PREFECTURE_PATTERN, "[REDACTED_ADDRESS]"),
    (YAMATO_TRACKING, "[REDACTED_TRACKING]"),
    (JAPAN_POST_TRACKING, "[REDACTED_TRACKING]"),
    (JAPANESE_NAME_PATTERN, "[REDACTED_NAME]"),
]
