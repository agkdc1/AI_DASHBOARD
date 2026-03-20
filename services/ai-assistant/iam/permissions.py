"""Permission definitions and role constants for the IAM system."""

CATEGORIES = {
    "inventory": {"label_en": "Inventory", "label_ja": "在庫管理", "label_ko": "재고관리"},
    "orders": {"label_en": "Orders", "label_ja": "受注管理", "label_ko": "주문관리"},
    "tasks": {"label_en": "Tasks", "label_ja": "タスク", "label_ko": "태스크"},
    "wiki": {"label_en": "Wiki", "label_ja": "Wiki", "label_ko": "Wiki"},
    "features": {"label_en": "Features", "label_ja": "機能", "label_ko": "기능"},
    "seating": {"label_en": "Seating", "label_ja": "座席", "label_ko": "좌석"},
    "admin": {"label_en": "Admin", "label_ja": "管理", "label_ko": "관리"},
}

PERMISSIONS = {
    "inventory.view": {
        "label_en": "View inventory", "label_ja": "在庫閲覧", "label_ko": "재고 보기",
        "category": "inventory",
    },
    "inventory.edit": {
        "label_en": "Edit inventory", "label_ja": "在庫編集", "label_ko": "재고 편집",
        "category": "inventory",
    },
    "orders.view": {
        "label_en": "View orders", "label_ja": "受注閲覧", "label_ko": "주문 보기",
        "category": "orders",
    },
    "orders.edit": {
        "label_en": "Edit orders", "label_ja": "受注編集", "label_ko": "주문 편집",
        "category": "orders",
    },
    "tasks.view_own": {
        "label_en": "View own tasks", "label_ja": "自分のタスク閲覧", "label_ko": "내 태스크 보기",
        "category": "tasks",
    },
    "tasks.edit_own": {
        "label_en": "Edit own tasks", "label_ja": "自分のタスク編集", "label_ko": "내 태스크 편집",
        "category": "tasks",
    },
    "tasks.view_others": {
        "label_en": "View others' tasks", "label_ja": "他のタスク閲覧", "label_ko": "타인 태스크 보기",
        "category": "tasks",
    },
    "tasks.edit_others": {
        "label_en": "Edit others' tasks", "label_ja": "他のタスク編集", "label_ko": "타인 태스크 편집",
        "category": "tasks",
    },
    "wiki.view": {
        "label_en": "View wiki", "label_ja": "Wiki閲覧", "label_ko": "Wiki 보기",
        "category": "wiki",
    },
    "wiki.edit": {
        "label_en": "Edit wiki", "label_ja": "Wiki編集", "label_ko": "Wiki 편집",
        "category": "wiki",
    },
    "picking.access": {
        "label_en": "Picking list", "label_ja": "ピッキングリスト", "label_ko": "피킹 리스트",
        "category": "features",
    },
    "voice_request.access": {
        "label_en": "Voice requests", "label_ja": "音声リクエスト", "label_ko": "음성 요청",
        "category": "features",
    },
    "call_request.access": {
        "label_en": "Call requests", "label_ja": "通話リクエスト", "label_ko": "통화 요청",
        "category": "features",
    },
    "fax_review.access": {
        "label_en": "Fax review", "label_ja": "FAX確認", "label_ko": "팩스 검토",
        "category": "features",
    },
    "seating.checkin": {
        "label_en": "Seat check-in", "label_ja": "座席チェックイン", "label_ko": "좌석 체크인",
        "category": "seating",
    },
    "seating.admin": {
        "label_en": "Seating admin", "label_ja": "座席管理", "label_ko": "좌석 관리",
        "category": "admin",
    },
    "phone.admin": {
        "label_en": "Phone admin", "label_ja": "電話管理", "label_ko": "전화 관리",
        "category": "admin",
    },
    "staff.manage": {
        "label_en": "Staff management", "label_ja": "スタッフ管理", "label_ko": "직원 관리",
        "category": "admin",
    },
    "rakuten.manage": {
        "label_en": "Rakuten keys", "label_ja": "楽天キー管理", "label_ko": "라쿠텐 키 관리",
        "category": "admin",
    },
}

ROLES = ("superuser", "admin", "phone_admin", "staff")

ROLE_GUARANTEED: dict[str, list[str]] = {
    "admin": ["staff.manage", "phone.admin"],
    "phone_admin": ["phone.admin"],
}
