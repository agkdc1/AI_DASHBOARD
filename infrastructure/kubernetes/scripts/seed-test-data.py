#!/usr/bin/env python3
"""Seed the test InvenTree instance with cosmetic product demo data.

Usage:
    python3 seed-test-data.py [--url URL] [--user USER] [--password PASSWORD]

Defaults:
    url:      https://test-api.your-domain.com
    user:     admin
    password: change-me
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import struct
import sys
import time
import zlib
from datetime import datetime

import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_URL = "https://test-api.your-domain.com"
DEFAULT_USER = "admin"
DEFAULT_PASSWORD = "change-me"

CATEGORIES = [
    {"name": "スキンケア", "description": "Skincare — toners, moisturizers, serums"},
    {"name": "メイクアップ", "description": "Makeup — foundation, lipstick, eyeshadow"},
    {"name": "ヘアケア", "description": "Haircare — shampoo, conditioner, treatment"},
    {"name": "ボディケア", "description": "Bodycare — body wash, lotion, sunscreen"},
    {"name": "ネイル", "description": "Nail — polish, remover, tools"},
]

# (name_ja, name_ko, description, IPN, category_index, stock_qty)
PARTS = [
    # Skincare (5)
    ("薬用化粧水", "약용 화장수", "敏感肌用薬用化粧水 200ml", "SB-SK-001", 0, 50),
    ("保湿クリーム", "보습 크림", "高保湿フェイスクリーム 50g", "SB-SK-002", 0, 35),
    ("美容液", "미용액", "ビタミンC美容液 30ml", "SB-SK-003", 0, 40),
    ("クレンジングオイル", "클렌징 오일", "メイク落としオイル 150ml", "SB-SK-004", 0, 25),
    ("日焼け止め SPF50", "자외선 차단제 SPF50", "UVカットミルク SPF50+ PA++++ 60ml", "SB-SK-005", 0, 60),
    # Makeup (5)
    ("リキッドファンデーション", "리퀴드 파운데이션", "カバー力高いリキッドファンデ 30ml", "SB-MK-001", 1, 30),
    ("口紅 ローズレッド", "립스틱 로즈레드", "マットリップスティック #201", "SB-MK-002", 1, 45),
    ("アイシャドウパレット", "아이섀도우 팔레트", "12色アイシャドウパレット", "SB-MK-003", 1, 20),
    ("マスカラ", "마스카라", "ウォータープルーフマスカラ ブラック", "SB-MK-004", 1, 55),
    ("チーク ピンク", "치크 핑크", "パウダーチーク #105 ピンク", "SB-MK-005", 1, 40),
    # Haircare (5)
    ("アミノ酸シャンプー", "아미노산 샴푸", "ダメージケアシャンプー 500ml", "SB-HC-001", 2, 70),
    ("トリートメント", "트리트먼트", "集中補修トリートメント 200g", "SB-HC-002", 2, 45),
    ("ヘアオイル", "헤어 오일", "椿オイルヘアセラム 100ml", "SB-HC-003", 2, 35),
    ("ヘアカラー ダークブラウン", "헤어 컬러 다크브라운", "白髪染めクリーム ダークブラウン", "SB-HC-004", 2, 25),
    ("スタイリングワックス", "스타일링 왁스", "ナチュラルマットワックス 80g", "SB-HC-005", 2, 30),
    # Bodycare (5)
    ("ボディソープ", "바디 소프", "オーガニックボディウォッシュ 500ml", "SB-BC-001", 3, 80),
    ("ボディローション", "바디 로션", "シアバターボディローション 300ml", "SB-BC-002", 3, 55),
    ("ハンドクリーム", "핸드크림", "ローズハンドクリーム 75g", "SB-BC-003", 3, 100),
    ("入浴剤 ラベンダー", "입욕제 라벤더", "アロマバスソルト ラベンダー 500g", "SB-BC-004", 3, 40),
    ("デオドラント", "데오도란트", "制汗デオドラントスティック 40g", "SB-BC-005", 3, 65),
    # Nail (5)
    ("ネイルポリッシュ レッド", "네일 폴리시 레드", "速乾ネイルカラー #301 レッド", "SB-NL-001", 4, 50),
    ("ネイルリムーバー", "네일 리무버", "アセトンフリー除光液 200ml", "SB-NL-002", 4, 35),
    ("ベースコート", "베이스 코트", "爪保護ベースコート 10ml", "SB-NL-003", 4, 40),
    ("トップコート", "톱 코트", "ジェル風トップコート 10ml", "SB-NL-004", 4, 30),
    ("キューティクルオイル", "큐티클 오일", "ネイルケアオイル 15ml", "SB-NL-005", 4, 25),
]

# Warehouse location tree: (name, parent_index or None)
# Index in this list used to reference parent
LOCATIONS = [
    ("倉庫", None),           # 0 - root
    ("A棚", 0),               # 1 - Skincare
    ("A-1", 1),               # 2 - Toners
    ("A-2", 1),               # 3 - Moisturizers
    ("A-3", 1),               # 4 - Serums
    ("B棚", 0),               # 5 - Makeup
    ("B-1", 5),               # 6 - Foundation
    ("B-2", 5),               # 7 - Lip products
    ("B-3", 5),               # 8 - Eye products
    ("C棚", 0),               # 9 - Hair/Body
    ("C-1", 9),               # 10 - Hair
    ("C-2", 9),               # 11 - Body
    ("D棚", 0),               # 12 - Nail
    ("D-1", 12),              # 13 - Nail products
    ("出荷エリア", 0),        # 14 - Shipping area
]

# Map part category index → leaf location index
CATEGORY_LOCATIONS = {
    0: [2, 3, 4],     # Skincare → A-1, A-2, A-3
    1: [6, 7, 8],     # Makeup → B-1, B-2, B-3
    2: [10],           # Hair → C-1
    3: [11],           # Body → C-2
    4: [13],           # Nail → D-1
}

CUSTOMERS = [
    {
        "name": "株式会社コスメショップ東京",
        "description": "Cosme Shop Tokyo — retail cosmetics",
        "is_customer": True,
        "is_supplier": False,
    },
    {
        "name": "ビューティーワールド大阪",
        "description": "Beauty World Osaka — wholesale beauty",
        "is_customer": True,
        "is_supplier": False,
    },
    {
        "name": "韓国美容株式会社",
        "description": "Korean Beauty Co. — K-beauty importer",
        "is_customer": True,
        "is_supplier": True,
    },
]

# Sales orders: (customer_index, reference, line_items[(part_index, quantity)])
today = datetime.now().strftime("%y%m%d")
SALES_ORDERS = [
    (0, "SO-0001", [(0, 3), (1, 2), (5, 1)]),
    (0, "SO-0002", [(2, 5), (3, 3), (6, 2), (10, 4), (15, 1)]),
    (1, "SO-0003", [(7, 2), (8, 3), (9, 1)]),
    (1, "SO-0004", [(11, 4), (12, 2)]),
    (2, "SO-0005", [(16, 3), (17, 2), (20, 5)]),
    (2, "SO-0006", [(0, 2), (1, 1), (5, 3), (6, 2), (10, 5), (15, 3), (16, 2), (20, 1), (22, 4), (24, 2)]),
]

# Colors per category for placeholder images
CATEGORY_COLORS = {
    0: (200, 220, 240),   # Light blue — skincare
    1: (240, 180, 180),   # Light pink — makeup
    2: (180, 220, 180),   # Light green — haircare
    3: (240, 220, 180),   # Light orange — bodycare
    4: (220, 180, 220),   # Light purple — nail
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class InvenTreeAPI:
    """Minimal InvenTree REST API client."""

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Token {token}",
            "Content-Type": "application/json",
        })

    def get(self, path: str, **kwargs) -> dict | list:
        resp = self.session.get(f"{self.base_url}{path}", **kwargs)
        if resp.status_code == 500:
            log.warning("GET %s returned 500, returning empty", path)
            return []
        resp.raise_for_status()
        return resp.json()

    def post(self, path: str, data: dict | None = None, **kwargs) -> dict:
        resp = self.session.post(f"{self.base_url}{path}", json=data, **kwargs)
        if not resp.ok:
            log.error("POST %s → %d: %s", path, resp.status_code, resp.text[:300])
        resp.raise_for_status()
        return resp.json()

    def patch_file(self, path: str, files: dict, data: dict | None = None) -> dict:
        headers = {"Authorization": self.session.headers["Authorization"]}
        resp = requests.patch(
            f"{self.base_url}{path}",
            headers=headers,
            files=files,
            data=data,
        )
        resp.raise_for_status()
        return resp.json()

    def patch(self, path: str, data: dict) -> dict:
        resp = self.session.patch(f"{self.base_url}{path}", json=data)
        resp.raise_for_status()
        return resp.json()


def make_placeholder_png(color: tuple[int, int, int], size: int = 200) -> bytes:
    """Generate a minimal solid-color PNG image in memory (no PIL needed)."""
    width = height = size

    def make_chunk(chunk_type: bytes, data: bytes) -> bytes:
        c = chunk_type + data
        crc = zlib.crc32(c) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + c + struct.pack(">I", crc)

    # IHDR
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr = make_chunk(b"IHDR", ihdr_data)

    # IDAT — raw pixel data
    raw_row = b"\x00" + bytes(color) * width  # filter byte + RGB pixels
    raw_data = raw_row * height
    compressed = zlib.compress(raw_data)
    idat = make_chunk(b"IDAT", compressed)

    # IEND
    iend = make_chunk(b"IEND", b"")

    return b"\x89PNG\r\n\x1a\n" + ihdr + idat + iend


def login_get_token(base_url: str, username: str, password: str) -> str:
    """Login to InvenTree and get an API token."""
    resp = requests.post(
        f"{base_url}/api/auth/login/",
        json={"username": username, "password": password},
    )
    if resp.status_code != 200:
        # Try alternative endpoint
        resp = requests.get(
            f"{base_url}/api/user/token/",
            auth=(username, password),
        )
    resp.raise_for_status()
    data = resp.json()
    token = data.get("key") or data.get("token")
    if not token:
        raise ValueError(f"No token in response: {data}")
    return token


# ---------------------------------------------------------------------------
# Seed functions
# ---------------------------------------------------------------------------

def seed_categories(api: InvenTreeAPI) -> dict[int, int]:
    """Create part categories. Returns {index: pk}."""
    mapping = {}
    for i, cat in enumerate(CATEGORIES):
        existing = api.get("/api/part/category/", params={"name": cat["name"]})
        if isinstance(existing, list) and existing:
            pk = existing[0]["pk"]
            log.info("Category exists: %s (pk=%d)", cat["name"], pk)
        else:
            result = api.post("/api/part/category/", {
                "name": cat["name"],
                "description": cat["description"],
            })
            pk = result["pk"]
            log.info("Created category: %s (pk=%d)", cat["name"], pk)
        mapping[i] = pk
    return mapping


def seed_locations(api: InvenTreeAPI) -> dict[int, int]:
    """Create stock locations. Returns {index: pk}."""
    mapping = {}
    for i, (name, parent_idx) in enumerate(LOCATIONS):
        parent_pk = mapping.get(parent_idx) if parent_idx is not None else None
        params = {"name": name}
        if parent_pk:
            params["parent"] = parent_pk
        existing = api.get("/api/stock/location/", params=params)
        if isinstance(existing, list) and existing:
            pk = existing[0]["pk"]
            log.info("Location exists: %s (pk=%d)", name, pk)
        else:
            data = {"name": name}
            if parent_pk:
                data["parent"] = parent_pk
            result = api.post("/api/stock/location/", data)
            pk = result["pk"]
            log.info("Created location: %s (pk=%d)", name, pk)
        mapping[i] = pk
    return mapping


def seed_parts(api: InvenTreeAPI, cat_map: dict[int, int]) -> dict[int, int]:
    """Create parts with placeholder images. Returns {index: pk}."""
    mapping = {}
    for i, (name_ja, name_ko, desc, ipn, cat_idx, _qty) in enumerate(PARTS):
        existing = api.get("/api/part/", params={"IPN": ipn})
        if isinstance(existing, dict):
            existing = existing.get("results", [])
        if existing:
            pk = existing[0]["pk"]
            log.info("Part exists: %s (pk=%d)", ipn, pk)
        else:
            result = api.post("/api/part/", {
                "name": name_ja,
                "description": f"{desc}\n{name_ko}",
                "IPN": ipn,
                "category": cat_map[cat_idx],
                "component": False,
                "purchaseable": True,
                "salable": True,
                "trackable": False,
                "active": True,
                "virtual": False,
            })
            pk = result["pk"]
            log.info("Created part: %s %s (pk=%d)", ipn, name_ja, pk)

            # Upload placeholder image
            color = CATEGORY_COLORS.get(cat_idx, (200, 200, 200))
            png_data = make_placeholder_png(color)
            try:
                api.patch_file(
                    f"/api/part/{pk}/",
                    files={"image": (f"{ipn}.png", io.BytesIO(png_data), "image/png")},
                )
                log.info("  Uploaded placeholder image for %s", ipn)
            except Exception as e:
                log.warning("  Image upload failed for %s: %s", ipn, e)

        mapping[i] = pk
    return mapping


def seed_stock(
    api: InvenTreeAPI,
    part_map: dict[int, int],
    loc_map: dict[int, int],
) -> None:
    """Create stock items for each part in appropriate locations."""
    for i, (_name_ja, _name_ko, _desc, ipn, cat_idx, qty) in enumerate(PARTS):
        locations = CATEGORY_LOCATIONS.get(cat_idx, [])
        if not locations:
            continue
        # Distribute stock across locations for this category
        loc_idx = locations[i % len(locations)]
        loc_pk = loc_map[loc_idx]
        part_pk = part_map[i]

        # Check existing stock
        existing = api.get("/api/stock/", params={"part": part_pk, "location": loc_pk})
        if isinstance(existing, dict):
            existing = existing.get("results", [])
        if existing:
            log.info("Stock exists for %s at location %d", ipn, loc_pk)
            continue

        api.post("/api/stock/", {
            "part": part_pk,
            "location": loc_pk,
            "quantity": qty,
        })
        log.info("Created stock: %s qty=%d at location pk=%d", ipn, qty, loc_pk)


def seed_customers(api: InvenTreeAPI) -> dict[int, int]:
    """Create customer companies. Returns {index: pk}."""
    mapping = {}
    for i, cust in enumerate(CUSTOMERS):
        existing = api.get("/api/company/", params={"name": cust["name"]})
        if isinstance(existing, dict):
            existing = existing.get("results", [])
        if existing:
            pk = existing[0]["pk"]
            log.info("Customer exists: %s (pk=%d)", cust["name"], pk)
        else:
            result = api.post("/api/company/", cust)
            pk = result["pk"]
            log.info("Created customer: %s (pk=%d)", cust["name"], pk)
        mapping[i] = pk
    return mapping


def seed_sales_orders(
    api: InvenTreeAPI,
    cust_map: dict[int, int],
    part_map: dict[int, int],
) -> None:
    """Create sales orders with line items."""
    for cust_idx, reference, lines in SALES_ORDERS:
        existing = api.get("/api/order/so/", params={"reference": reference})
        if isinstance(existing, dict):
            existing = existing.get("results", [])
        if existing:
            log.info("Sales order exists: %s", reference)
            continue

        # Generate company ID
        seq = int(reference.split("-")[-1])
        company_id = f"SB-{today}-{seq:04d}"

        result = api.post("/api/order/so/", {
            "customer": cust_map[cust_idx],
            "reference": reference,
            "description": f"テスト注文 {reference}",
            "status": 10,  # Pending
        })
        so_pk = result["pk"]
        log.info("Created sales order: %s (pk=%d)", reference, so_pk)

        # Set picking metadata via PATCH on the SO itself
        try:
            api.patch(f"/api/order/so/{so_pk}/", {
                "metadata": {"picking": {"company_id": company_id}},
            })
            log.info("  Set picking metadata: %s", company_id)
        except Exception as e:
            log.warning("  Metadata update failed: %s", e)

        # Add line items
        for part_idx, qty in lines:
            part_pk = part_map[part_idx]
            api.post("/api/order/so-line/", {
                "order": so_pk,
                "part": part_pk,
                "quantity": qty,
            })
            ipn = PARTS[part_idx][3]
            log.info("  Added line: %s qty=%d", ipn, qty)


def seed_users(api: InvenTreeAPI) -> None:
    """Create test users (warehouse worker and manager)."""
    test_users = [
        {"username": "warehouse", "password": "warehouse-test", "email": "warehouse@your-domain.com",
         "first_name": "倉庫", "last_name": "担当者"},
        {"username": "manager", "password": "manager-test", "email": "manager@your-domain.com",
         "first_name": "管理", "last_name": "マネージャー"},
    ]
    for user in test_users:
        try:
            api.post("/api/user/", user)
            log.info("Created user: %s", user["username"])
        except requests.HTTPError as e:
            if e.response.status_code in (400, 409):
                log.info("User exists: %s", user["username"])
            else:
                log.warning("User creation failed for %s: %s", user["username"], e)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Seed InvenTree test instance")
    parser.add_argument("--url", default=DEFAULT_URL, help="InvenTree base URL")
    parser.add_argument("--user", default=DEFAULT_USER, help="Admin username")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="Admin password")
    args = parser.parse_args()

    log.info("Connecting to %s as %s ...", args.url, args.user)

    # Get auth token
    token = login_get_token(args.url, args.user, args.password)
    log.info("Got API token: %s...", token[:8])

    api = InvenTreeAPI(args.url, token)

    # Seed in dependency order
    log.info("--- Seeding categories ---")
    cat_map = seed_categories(api)

    log.info("--- Seeding locations ---")
    loc_map = seed_locations(api)

    log.info("--- Seeding parts ---")
    part_map = seed_parts(api, cat_map)

    log.info("--- Seeding stock items ---")
    seed_stock(api, part_map, loc_map)

    log.info("--- Seeding customers ---")
    cust_map = seed_customers(api)

    log.info("--- Seeding sales orders ---")
    seed_sales_orders(api, cust_map, part_map)

    log.info("--- Seeding users ---")
    seed_users(api)

    log.info("=== Seed complete ===")
    log.info("  Categories: %d", len(cat_map))
    log.info("  Locations:  %d", len(loc_map))
    log.info("  Parts:      %d", len(part_map))
    log.info("  Customers:  %d", len(cust_map))
    log.info("  Orders:     %d", len(SALES_ORDERS))


if __name__ == "__main__":
    main()
