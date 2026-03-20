"""Rakuten API key management service — manual refresh with Vikunja reminders."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from config import settings

log = logging.getLogger(__name__)

_API_KEYS_SECRET = "rakuten-api-keys"
_INVENTREE_SECRET = "daemon-inventree"
_INVENTREE_SETTING_URL = "/api/plugins/settings/ecommerce/{key}/"

INSTRUCTIONS = {
    "ja": {
        "title": "楽天APIキー更新手順",
        "steps": [
            "RMS にログイン: https://glogin.rms.rakuten.co.jp/",
            "左メニュー「APIキー管理」を開く",
            "「更新」ボタンをクリック",
            "確認ダイアログで「OK」を押す",
            "新しい serviceSecret と licenseKey をコピー",
            "このページの入力欄に貼り付けて送信",
        ],
        "link": "https://navi-manual.rms.rakuten.co.jp/auth-api",
    },
    "ko": {
        "title": "라쿠텐 API 키 갱신 절차",
        "steps": [
            "RMS 로그인: https://glogin.rms.rakuten.co.jp/",
            "좌측 메뉴 'API키 관리' 열기",
            "'갱신' 버튼 클릭",
            "확인 다이얼로그에서 'OK' 클릭",
            "새로운 serviceSecret과 licenseKey 복사",
            "이 페이지 입력란에 붙여넣기 후 전송",
        ],
        "link": "https://navi-manual.rms.rakuten.co.jp/auth-api",
    },
    "en": {
        "title": "Rakuten API Key Renewal Procedure",
        "steps": [
            "Log in to RMS: https://glogin.rms.rakuten.co.jp/",
            "Open 'API Key Management' from the left menu",
            "Click the 'Renew' button",
            "Click 'OK' on the confirmation dialog",
            "Copy the new serviceSecret and licenseKey",
            "Paste them into the input fields on this page and submit",
        ],
        "link": "https://navi-manual.rms.rakuten.co.jp/auth-api",
    },
}


class RakutenKeyService:
    """Manages Rakuten API key lifecycle — status, submission, reminders."""

    def __init__(self) -> None:
        self._sm_client: Any = None

    def _ensure_sm(self) -> Any:
        if self._sm_client is None:
            from google.cloud import secretmanager
            self._sm_client = secretmanager.SecretManagerServiceClient()
        return self._sm_client

    def _read_secret(self, secret_id: str) -> dict:
        client = self._ensure_sm()
        name = f"projects/{settings.gcp_project}/secrets/{secret_id}/versions/latest"
        resp = client.access_secret_version(request={"name": name})
        return json.loads(resp.payload.data.decode("utf-8"))

    def _write_secret(self, secret_id: str, data: dict) -> None:
        client = self._ensure_sm()
        parent = f"projects/{settings.gcp_project}/secrets/{secret_id}"
        payload = json.dumps(data).encode("utf-8")
        try:
            client.add_secret_version(
                request={"parent": parent, "payload": {"data": payload}}
            )
        except Exception:
            client.create_secret(
                request={
                    "parent": f"projects/{settings.gcp_project}",
                    "secret_id": secret_id,
                    "secret": {"replication": {"automatic": {}}},
                }
            )
            client.add_secret_version(
                request={"parent": parent, "payload": {"data": payload}}
            )

    async def get_key_status(self) -> dict:
        """Return current API key age and reminder info."""
        try:
            data = self._read_secret(_API_KEYS_SECRET)
        except Exception as e:
            log.warning("Could not read Rakuten API keys: %s", e)
            return {
                "renewed_at": None,
                "age_days": None,
                "days_until_reminder": None,
                "days_until_deadline": None,
                "assigned_employees": data.get("assigned_employees", []) if 'data' in dir() else [],
            }

        renewed_at_str = data.get("renewed_at")
        assigned = data.get("assigned_employees", [])

        if not renewed_at_str:
            return {
                "renewed_at": None,
                "age_days": None,
                "days_until_reminder": None,
                "days_until_deadline": None,
                "assigned_employees": assigned,
            }

        renewed_at = datetime.fromisoformat(renewed_at_str)
        age_days = (datetime.now(timezone.utc) - renewed_at).days

        return {
            "renewed_at": renewed_at_str,
            "age_days": age_days,
            "days_until_reminder": max(0, settings.rakuten_reminder_days - age_days),
            "days_until_deadline": max(0, settings.rakuten_deadline_days - age_days),
            "assigned_employees": assigned,
        }

    async def submit_new_keys(
        self, service_secret: str, license_key: str, submitted_by: str
    ) -> dict:
        """Write new keys to GCP SM and update InvenTree plugin settings."""
        now = datetime.now(timezone.utc).isoformat()

        # Preserve assigned_employees from existing secret
        try:
            existing = self._read_secret(_API_KEYS_SECRET)
            assigned = existing.get("assigned_employees", [])
        except Exception:
            assigned = []

        # Write to GCP SM
        self._write_secret(_API_KEYS_SECRET, {
            "service_secret": service_secret,
            "license_key": license_key,
            "renewed_at": now,
            "submitted_by": submitted_by,
            "assigned_employees": assigned,
        })
        log.info("Rakuten API keys updated by %s", submitted_by)

        # Update InvenTree plugin settings
        inventree_updated = await self._update_inventree(service_secret, license_key)

        # Mark active Vikunja task as done
        vikunja_closed = await self._close_vikunja_task()

        return {
            "renewed_at": now,
            "inventree_updated": inventree_updated,
            "vikunja_task_closed": vikunja_closed,
        }

    async def update_assignees(self, employees: list[str]) -> dict:
        """Set the list of employees responsible for renewal."""
        try:
            data = self._read_secret(_API_KEYS_SECRET)
        except Exception:
            data = {}

        data["assigned_employees"] = employees
        self._write_secret(_API_KEYS_SECRET, data)
        return {"assigned_employees": employees}

    def get_instructions(self, lang: str = "ja") -> dict:
        return INSTRUCTIONS.get(lang, INSTRUCTIONS["en"])

    async def _update_inventree(self, service_secret: str, license_key: str) -> bool:
        """Push renewed keys to InvenTree ecommerce plugin settings."""
        try:
            creds = self._read_secret(_INVENTREE_SECRET)
            base_url = creds.get("base_url", "")
            api_token = creds.get("api_token", "")
            if not base_url or not api_token:
                log.info("InvenTree credentials not configured, skipping")
                return False
        except Exception as e:
            log.warning("Could not read InvenTree creds: %s", e)
            return False

        settings_map = {
            "RAKUTEN_SERVICE_SECRET": service_secret,
            "RAKUTEN_LICENSE_KEY": license_key,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            for key, value in settings_map.items():
                url = f"{base_url.rstrip('/')}{_INVENTREE_SETTING_URL.format(key=key)}"
                resp = await client.patch(
                    url,
                    json={"value": value},
                    headers={"Authorization": f"Token {api_token}"},
                )
                if resp.status_code not in (200, 201):
                    log.error("InvenTree setting %s update failed: %s", key, resp.text)
                    return False
                log.info("Updated InvenTree setting: %s", key)

        return True

    async def _close_vikunja_task(self) -> bool:
        """Find and close the active Rakuten renewal task in Vikunja."""
        if not settings.vikunja_token:
            return False

        try:
            async with httpx.AsyncClient(
                base_url=settings.vikunja_url,
                headers={"Authorization": f"Bearer {settings.vikunja_token}"},
                timeout=30.0,
            ) as client:
                # Search for open tasks with the renewal title
                resp = await client.get(
                    f"/api/v1/projects/{settings.rakuten_vikunja_project_id}/tasks",
                    params={"filter": "done=false"},
                )
                if resp.status_code != 200:
                    return False

                for task in resp.json():
                    if "楽天APIキー更新" in task.get("title", ""):
                        await client.post(
                            f"/api/v1/tasks/{task['id']}",
                            json={"done": True},
                        )
                        log.info("Closed Vikunja task: %s", task["title"])
                        return True
        except Exception as e:
            log.warning("Could not close Vikunja task: %s", e)

        return False

    async def check_and_remind(self) -> dict | None:
        """Check key age and create Vikunja reminder if needed.

        Returns reminder info if created, None otherwise.
        """
        status = await self.get_key_status()
        if status["age_days"] is None:
            return None

        if status["age_days"] < settings.rakuten_reminder_days:
            return None

        # Check if a task already exists
        if not settings.vikunja_token:
            return None

        try:
            async with httpx.AsyncClient(
                base_url=settings.vikunja_url,
                headers={"Authorization": f"Bearer {settings.vikunja_token}"},
                timeout=30.0,
            ) as client:
                resp = await client.get(
                    f"/api/v1/projects/{settings.rakuten_vikunja_project_id}/tasks",
                    params={"filter": "done=false"},
                )
                if resp.status_code == 200:
                    for task in resp.json():
                        if "楽天APIキー更新" in task.get("title", ""):
                            return None  # Task already exists

                # Calculate due date from renewed_at
                renewed_at = datetime.fromisoformat(status["renewed_at"])
                from datetime import timedelta
                due_date = (renewed_at + timedelta(days=settings.rakuten_deadline_days)).isoformat()

                # Create reminder task
                task_data = {
                    "title": "楽天APIキー更新",
                    "description": (
                        f"APIキーが{status['age_days']}日経過しています。\n"
                        f"期限: {due_date[:10]}\n"
                        f"手順: https://navi-manual.rms.rakuten.co.jp/auth-api"
                    ),
                    "due_date": due_date,
                    "priority": 2,
                }
                resp = await client.put(
                    f"/api/v1/projects/{settings.rakuten_vikunja_project_id}/tasks",
                    json=task_data,
                )
                if resp.status_code in (200, 201):
                    log.info("Created Rakuten renewal reminder task (age=%d days)", status["age_days"])
                    return {"task_created": True, "age_days": status["age_days"]}

        except Exception as e:
            log.warning("Could not create reminder task: %s", e)

        return None
