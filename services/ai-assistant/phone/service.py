"""Phone management service — Samba AD user CRUD and device tracking."""

import logging
from typing import Any

import ldap
import ldap.modlist

from config import settings

log = logging.getLogger(__name__)

# Samba AD uses CN=Users as the default users container
USERS_CONTAINER = "CN=Users"


class PhoneService:
    """Manages Samba AD phonebook entries and phone device metadata."""

    def __init__(self) -> None:
        self._conn: Any = None

    def _ensure_ldap(self) -> Any:
        """Lazy-connect to Samba AD LDAP."""
        if self._conn is None:
            self._conn = ldap.initialize(settings.ldap_server)
            self._conn.set_option(ldap.OPT_REFERRALS, 0)
            self._conn.simple_bind_s(settings.ldap_bind_dn, settings.ldap_bind_password)
            log.info("Connected to Samba AD: %s", settings.ldap_server)
        return self._conn

    def _reconnect(self) -> Any:
        """Force reconnect (e.g. after server restart)."""
        self._conn = None
        return self._ensure_ldap()

    def _users_dn(self) -> str:
        return f"{USERS_CONTAINER},{settings.ldap_base_dn}"

    def _user_dn(self, uid: str, cn: str | None = None) -> str:
        """Build DN for a user. AD uses CN= not uid=."""
        display = cn or uid
        return f"CN={display},{self._users_dn()}"

    def _find_user_dn(self, uid: str) -> str | None:
        """Find user DN by sAMAccountName search."""
        try:
            conn = self._ensure_ldap()
            results = conn.search_s(
                self._users_dn(),
                ldap.SCOPE_ONELEVEL,
                f"(sAMAccountName={uid})",
                ["distinguishedName"],
            )
            for dn, attrs in results:
                if dn is not None:
                    return dn
            return None
        except ldap.LDAPError:
            return None

    # ------------------------------------------------------------------
    # LDAP user CRUD
    # ------------------------------------------------------------------

    async def list_users(self) -> list[dict]:
        """List all AD phonebook users."""
        try:
            conn = self._ensure_ldap()
            results = conn.search_s(
                self._users_dn(),
                ldap.SCOPE_ONELEVEL,
                "(&(objectClass=user)(telephoneNumber=*))",
                ["sAMAccountName", "cn", "telephoneNumber"],
            )
            users = []
            for dn, attrs in results:
                if dn is None:
                    continue
                users.append({
                    "uid": attrs.get("sAMAccountName", [b""])[0].decode(),
                    "cn": attrs.get("cn", [b""])[0].decode(),
                    "telephoneNumber": attrs.get("telephoneNumber", [b""])[0].decode(),
                    "dn": dn,
                })
            return users
        except ldap.LDAPError as e:
            log.error("AD list_users failed: %s", e)
            self._conn = None
            return []

    async def get_user(self, uid: str) -> dict | None:
        """Get a single AD user by sAMAccountName (extension number)."""
        try:
            conn = self._ensure_ldap()
            results = conn.search_s(
                self._users_dn(),
                ldap.SCOPE_ONELEVEL,
                f"(sAMAccountName={uid})",
                ["sAMAccountName", "cn", "sn", "telephoneNumber"],
            )
            if not results:
                return None
            for dn, attrs in results:
                if dn is None:
                    continue
                return {
                    "uid": attrs.get("sAMAccountName", [b""])[0].decode(),
                    "cn": attrs.get("cn", [b""])[0].decode(),
                    "sn": attrs.get("sn", [b""])[0].decode(),
                    "telephoneNumber": attrs.get("telephoneNumber", [b""])[0].decode(),
                    "dn": dn,
                }
            return None
        except ldap.LDAPError as e:
            log.error("AD get_user(%s) failed: %s", uid, e)
            self._conn = None
            return None

    async def create_user(self, uid: str, cn: str, password: str) -> dict:
        """Create a new AD phonebook user entry."""
        dn = self._user_dn(uid, cn)
        upn = f"{uid}@your-domain.local"
        attrs = {
            "objectClass": [b"top", b"person", b"organizationalPerson", b"user"],
            "sAMAccountName": [uid.encode()],
            "userPrincipalName": [upn.encode()],
            "cn": [cn.encode()],
            "sn": [cn.encode()],
            "telephoneNumber": [uid.encode()],
            "userPassword": [password.encode()],
        }
        try:
            conn = self._ensure_ldap()
            add_list = ldap.modlist.addModlist(attrs)
            conn.add_s(dn, add_list)
            log.info("Created AD user: %s (%s)", uid, cn)
            return {"uid": uid, "cn": cn, "telephoneNumber": uid, "dn": dn}
        except ldap.ALREADY_EXISTS:
            log.warning("AD user %s already exists", uid)
            return {"error": f"User {uid} already exists"}
        except ldap.LDAPError as e:
            log.error("AD create_user(%s) failed: %s", uid, e)
            self._conn = None
            return {"error": str(e)}

    async def update_user(self, uid: str, cn: str | None = None, password: str | None = None) -> dict:
        """Update an existing AD user."""
        dn = self._find_user_dn(uid)
        if not dn:
            return {"error": f"User {uid} not found"}

        mods = []
        if cn is not None:
            mods.append((ldap.MOD_REPLACE, "displayName", [cn.encode()]))
            mods.append((ldap.MOD_REPLACE, "sn", [cn.encode()]))
        if password is not None:
            mods.append((ldap.MOD_REPLACE, "userPassword", [password.encode()]))

        if not mods:
            return {"error": "No fields to update"}

        try:
            conn = self._ensure_ldap()
            conn.modify_s(dn, mods)
            log.info("Updated AD user: %s", uid)
            return await self.get_user(uid) or {"uid": uid, "updated": True}
        except ldap.NO_SUCH_OBJECT:
            return {"error": f"User {uid} not found"}
        except ldap.LDAPError as e:
            log.error("AD update_user(%s) failed: %s", uid, e)
            self._conn = None
            return {"error": str(e)}

    async def delete_user(self, uid: str) -> bool:
        """Delete an AD user."""
        dn = self._find_user_dn(uid)
        if not dn:
            log.warning("AD user %s not found for deletion", uid)
            return False

        try:
            conn = self._ensure_ldap()
            conn.delete_s(dn)
            log.info("Deleted AD user: %s", uid)
            return True
        except ldap.NO_SUCH_OBJECT:
            log.warning("AD user %s not found for deletion", uid)
            return False
        except ldap.LDAPError as e:
            log.error("AD delete_user(%s) failed: %s", uid, e)
            self._conn = None
            return False

    # ------------------------------------------------------------------
    # Auto-provisioning (3XX extension range)
    # ------------------------------------------------------------------

    async def find_by_email(self, email: str) -> dict | None:
        """Find AD user by mail attribute."""
        try:
            conn = self._ensure_ldap()
            results = conn.search_s(
                self._users_dn(),
                ldap.SCOPE_ONELEVEL,
                f"(mail={email})",
                ["sAMAccountName", "cn", "telephoneNumber", "mail"],
            )
            if not results:
                return None
            for dn, attrs in results:
                if dn is None:
                    continue
                return {
                    "uid": attrs.get("sAMAccountName", [b""])[0].decode(),
                    "cn": attrs.get("cn", [b""])[0].decode(),
                    "telephoneNumber": attrs.get("telephoneNumber", [b""])[0].decode(),
                    "mail": attrs.get("mail", [b""])[0].decode(),
                    "dn": dn,
                }
            return None
        except ldap.LDAPError as e:
            log.error("AD find_by_email(%s) failed: %s", email, e)
            self._conn = None
            return None

    async def next_available_extension(
        self, start: int | None = None, end: int | None = None
    ) -> str:
        """Find next available extension in the auto-provision range."""
        start = start or settings.extension_range_start
        end = end or settings.extension_range_end

        try:
            conn = self._ensure_ldap()
            results = conn.search_s(
                self._users_dn(),
                ldap.SCOPE_ONELEVEL,
                "(&(objectClass=user)(sAMAccountName=*))",
                ["sAMAccountName"],
            )
            existing = set()
            for dn, attrs in results:
                if dn is None:
                    continue
                sam = attrs.get("sAMAccountName", [b""])[0].decode()
                if sam.isdigit():
                    existing.add(int(sam))

            for ext in range(start, end + 1):
                if ext not in existing:
                    return str(ext)

            raise ValueError(f"No available extensions in range {start}-{end}")
        except ldap.LDAPError as e:
            log.error("AD next_available_extension failed: %s", e)
            self._conn = None
            raise

    async def auto_provision(self, email: str, display_name: str) -> dict:
        """Auto-provision a phone extension for a user on first login.

        1. Check if user already has AD entry (by email)
        2. If not, create one with next available 3XX extension
        3. Create Asterisk extension via faxapi (SQLite + confgen)
        4. Return account info
        """
        import httpx

        # Check existing
        existing = await self.find_by_email(email)
        if existing:
            return {
                "accounts": [existing],
                "newly_created": False,
                "extension": existing["uid"],
            }

        # Find next available extension
        ext = await self.next_available_extension()
        password = f"{settings.extension_range_start}{ext}"  # e.g. "300300"

        # Create AD entry with mail attribute
        dn = self._user_dn(ext, display_name)
        upn = f"{ext}@your-domain.local"
        attrs = {
            "objectClass": [b"top", b"person", b"organizationalPerson", b"user"],
            "sAMAccountName": [ext.encode()],
            "userPrincipalName": [upn.encode()],
            "cn": [display_name.encode()],
            "sn": [display_name.encode()],
            "telephoneNumber": [ext.encode()],
            "userPassword": [password.encode()],
            "mail": [email.encode()],
        }
        try:
            conn = self._ensure_ldap()
            add_list = ldap.modlist.addModlist(attrs)
            conn.add_s(dn, add_list)
            log.info("Auto-provisioned AD user: %s (%s) ext=%s", email, display_name, ext)
        except ldap.LDAPError as e:
            log.error("Auto-provision AD create failed: %s", e)
            self._conn = None
            return {"error": str(e)}

        # Create Asterisk extension via faxapi (SQLite + confgen → AMI reload)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{settings.faxapi_url}/extensions",
                    json={"extension": ext, "name": display_name, "password": password},
                    headers={"X-API-Key": settings.faxapi_key} if hasattr(settings, 'faxapi_key') else {},
                )
                if resp.status_code not in (200, 201):
                    log.warning("Asterisk extension creation returned %s", resp.status_code)

                # Reload Asterisk configs
                await client.post(
                    f"{settings.faxapi_url}/extensions/reload",
                    headers={"X-API-Key": settings.faxapi_key} if hasattr(settings, 'faxapi_key') else {},
                )
        except Exception as e:
            log.warning("Asterisk extension creation failed (non-fatal): %s", e)

        account = {
            "uid": ext,
            "cn": display_name,
            "telephoneNumber": ext,
            "mail": email,
            "dn": dn,
        }
        return {
            "accounts": [account],
            "newly_created": True,
            "extension": ext,
        }

    # ------------------------------------------------------------------
    # Device listing (reads from provisioning config, not LDAP)
    # ------------------------------------------------------------------

    async def list_devices(self) -> list[dict]:
        """List known phone devices from provisioning data.

        Reads the CSV files to return device info. In production this could
        be backed by a database, but for now CSVs are the source of truth.
        """
        import csv
        from pathlib import Path

        devices = []

        for csv_path, phone_type in [
            (Path("/app/data/phone_number_fixed.csv"), "fixed"),
            (Path("/app/data/phone_free.csv"), "hotdesk"),
        ]:
            if not csv_path.exists():
                continue
            with open(csv_path, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    device = {
                        "mac": row.get("MAC", ""),
                        "type": phone_type,
                        "name": row.get("NAME", ""),
                        "extension": row.get("NUMBER", ""),
                    }
                    devices.append(device)

        return devices
