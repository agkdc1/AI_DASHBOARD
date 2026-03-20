"""Password sync service — verify current password, then set AD + Google."""

import logging
from typing import Any

import ldap

from config import settings

log = logging.getLogger(__name__)

# Correct base DN for AD.YOUR-DOMAIN.COM realm
AD_BASE_DN = "DC=ad,DC=your-domain,DC=com"
AD_USERS_DN = f"CN=Users,{AD_BASE_DN}"
AD_ADMIN_DN = f"CN=Administrator,{AD_USERS_DN}"


class PasswordSyncService:
    """Verifies current password, then sets new password in AD + Google."""

    def _ldaps_uri(self) -> str:
        return (
            settings.ldap_server.replace("ldap://", "ldaps://").replace(
                ":389", ":636"
            )
        )

    def _ldap_connect(self, bind_dn: str, bind_pw: str) -> Any:
        """Create a fresh LDAPS connection and bind."""
        uri = self._ldaps_uri()
        conn = ldap.initialize(uri)
        conn.set_option(ldap.OPT_REFERRALS, 0)
        conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
        conn.set_option(ldap.OPT_X_TLS_NEWCTX, 0)
        conn.simple_bind_s(bind_dn, bind_pw)
        return conn

    def find_user_by_email(self, email: str) -> tuple[str | None, str | None]:
        """Find AD user DN and sAMAccountName by mail attribute.

        Uses admin bind for searching.  Returns (dn, sam) or (None, None).
        """
        try:
            conn = self._ldap_connect(AD_ADMIN_DN, settings.ldap_bind_password)
            results = conn.search_s(
                AD_USERS_DN,
                ldap.SCOPE_ONELEVEL,
                f"(mail={email})",
                ["sAMAccountName", "cn", "mail"],
            )
            conn.unbind_s()
            for dn, attrs in results:
                if dn is not None:
                    sam = attrs.get("sAMAccountName", [b""])[0].decode()
                    return dn, sam
            return None, None
        except ldap.LDAPError as e:
            log.error("LDAP search by email failed: %s", e)
            return None, None

    def verify_password(self, user_dn: str, password: str) -> bool:
        """Verify a user's current password by attempting LDAP bind."""
        try:
            conn = self._ldap_connect(user_dn, password)
            conn.unbind_s()
            return True
        except ldap.INVALID_CREDENTIALS:
            return False
        except ldap.LDAPError as e:
            log.error("LDAP bind verification failed: %s", e)
            return False

    def set_ad_password(self, user_dn: str, new_password: str) -> bool:
        """Set AD password via LDAPS unicodePwd attribute (admin bind)."""
        encoded_pw = f'"{new_password}"'.encode("utf-16-le")
        try:
            conn = self._ldap_connect(AD_ADMIN_DN, settings.ldap_bind_password)
            conn.modify_s(
                user_dn,
                [(ldap.MOD_REPLACE, "unicodePwd", [encoded_pw])],
            )
            conn.unbind_s()
            log.info("AD password set for %s", user_dn)
            return True
        except ldap.UNWILLING_TO_PERFORM as e:
            log.error("AD password change refused (complexity?): %s", e)
            return False
        except ldap.LDAPError as e:
            log.error("AD password change failed: %s", e)
            return False

    def set_google_password(self, email: str, new_password: str) -> bool:
        """Set Google Workspace password via Admin SDK."""
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            creds = service_account.Credentials.from_service_account_file(
                settings.gsps_sa_key_path,
                scopes=["https://www.googleapis.com/auth/admin.directory.user"],
                subject=settings.gsps_admin_email,
            )
            directory = build(
                "admin", "directory_v1", credentials=creds, cache_discovery=False
            )
            directory.users().update(
                userKey=email,
                body={"password": new_password, "changePasswordAtNextLogin": False},
            ).execute()
            log.info("Google Workspace password set for %s", email)
            return True
        except Exception as e:
            log.error("Google password change failed for %s: %s", email, e)
            return False

    async def sync_password(
        self, email: str, new_password: str
    ) -> dict[str, Any]:
        """Set new password in both AD and Google Workspace.

        Identity must be verified by the caller (e.g. Google Sign-In token).
        """
        result: dict[str, Any] = {"email": email, "ad_ok": False, "google_ok": False}

        # Find AD user by email
        user_dn, sam = self.find_user_by_email(email)
        if not user_dn:
            result["error"] = "AD アカウントが見つかりません"
            return result

        # Set AD password first — abort if it fails
        result["ad_ok"] = self.set_ad_password(user_dn, new_password)
        if not result["ad_ok"]:
            result["error"] = (
                "パスワードの変更に失敗しました"
                "（パスワードの複雑さの要件を確認してください）"
            )
            return result

        # Set Google Workspace password only after AD succeeds
        result["google_ok"] = self.set_google_password(email, new_password)
        if not result["google_ok"]:
            result["error"] = (
                "ファイル共有のパスワードは変更されましたが、"
                "Google パスワードの変更に失敗しました。管理者に連絡してください。"
            )

        return result
