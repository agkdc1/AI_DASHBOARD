"""IAM business logic — staff CRUD and permission resolution."""

import logging
from typing import Any

from iam.db import get_db
from iam.permissions import PERMISSIONS, ROLE_GUARANTEED, ROLES

log = logging.getLogger(__name__)


async def list_staff() -> list[dict[str, Any]]:
    """Return all registered staff with their deny rules."""
    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            "SELECT email, display_name, photo_url, role, created_at, updated_at "
            "FROM staff ORDER BY created_at"
        )
        result = []
        for r in rows:
            staff = dict(r)
            deny_rows = await db.execute_fetchall(
                "SELECT permission FROM deny_rules WHERE email = ?",
                (staff["email"],),
            )
            staff["denied_permissions"] = [d["permission"] for d in deny_rows]
            result.append(staff)
        return result
    finally:
        await db.close()


async def get_staff(email: str) -> dict[str, Any] | None:
    """Get a single staff member with deny rules."""
    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            "SELECT email, display_name, photo_url, role, created_at, updated_at "
            "FROM staff WHERE email = ?",
            (email,),
        )
        if not rows:
            return None
        staff = dict(rows[0])
        deny_rows = await db.execute_fetchall(
            "SELECT permission FROM deny_rules WHERE email = ?",
            (email,),
        )
        staff["denied_permissions"] = [d["permission"] for d in deny_rows]
        return staff
    finally:
        await db.close()


async def register_staff(
    email: str, display_name: str, role: str = "staff", photo_url: str | None = None
) -> dict[str, Any]:
    """Create a new staff member."""
    if role not in ROLES:
        raise ValueError(f"Invalid role: {role}. Must be one of {ROLES}")
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO staff (email, display_name, photo_url, role) VALUES (?, ?, ?, ?)",
            (email, display_name, photo_url, role),
        )
        await db.commit()
        log.info("Registered staff: %s (%s)", email, role)
        return await get_staff(email)  # type: ignore[return-value]
    finally:
        await db.close()


async def update_staff(
    email: str,
    display_name: str | None = None,
    role: str | None = None,
    photo_url: str | None = ...,  # type: ignore[assignment]
) -> dict[str, Any] | None:
    """Update a staff member's profile."""
    existing = await get_staff(email)
    if not existing:
        return None
    if role is not None and role not in ROLES:
        raise ValueError(f"Invalid role: {role}. Must be one of {ROLES}")

    db = await get_db()
    try:
        updates = []
        params: list[Any] = []
        if display_name is not None:
            updates.append("display_name = ?")
            params.append(display_name)
        if role is not None:
            updates.append("role = ?")
            params.append(role)
        if photo_url is not ...:
            updates.append("photo_url = ?")
            params.append(photo_url)
        if updates:
            updates.append("updated_at = datetime('now')")
            params.append(email)
            await db.execute(
                f"UPDATE staff SET {', '.join(updates)} WHERE email = ?",
                params,
            )
            await db.commit()

        # If role changed, clean up deny rules for guaranteed permissions
        if role is not None:
            guaranteed = set(ROLE_GUARANTEED.get(role, []))
            if guaranteed:
                await db.execute(
                    f"DELETE FROM deny_rules WHERE email = ? AND permission IN ({','.join('?' * len(guaranteed))})",
                    [email, *guaranteed],
                )
                await db.commit()

        return await get_staff(email)
    finally:
        await db.close()


async def delete_staff(email: str) -> bool:
    """Delete a staff member. Returns False if not found or is superuser."""
    existing = await get_staff(email)
    if not existing:
        return False
    if existing["role"] == "superuser":
        raise ValueError("Cannot delete superuser")
    db = await get_db()
    try:
        await db.execute("DELETE FROM staff WHERE email = ?", (email,))
        await db.commit()
        log.info("Deleted staff: %s", email)
        return True
    finally:
        await db.close()


async def set_deny_rules(email: str, permissions: list[str]) -> dict[str, Any] | None:
    """Replace all deny rules for a staff member."""
    existing = await get_staff(email)
    if not existing:
        return None

    # Validate permissions
    invalid = [p for p in permissions if p not in PERMISSIONS]
    if invalid:
        raise ValueError(f"Invalid permissions: {invalid}")

    # Cannot deny role-guaranteed permissions
    role = existing["role"]
    guaranteed = set(ROLE_GUARANTEED.get(role, []))
    denied_guaranteed = [p for p in permissions if p in guaranteed]
    if denied_guaranteed:
        raise ValueError(
            f"Cannot deny {denied_guaranteed} — guaranteed by role '{role}'"
        )

    db = await get_db()
    try:
        await db.execute("DELETE FROM deny_rules WHERE email = ?", (email,))
        for perm in permissions:
            await db.execute(
                "INSERT INTO deny_rules (email, permission) VALUES (?, ?)",
                (email, perm),
            )
        await db.commit()
        log.info("Set %d deny rules for %s", len(permissions), email)
        return await get_staff(email)
    finally:
        await db.close()


async def resolve_permissions(email: str) -> dict[str, Any]:
    """Resolve effective permissions for a user.

    Returns:
        {registered: bool, role: str, denied: [...], all_permissions: [...]}

    Unregistered users get no restrictions (default allow).
    Superusers bypass all deny rules.
    """
    staff = await get_staff(email)
    if not staff:
        return {
            "registered": False,
            "role": "guest",
            "denied": [],
            "all_permissions": list(PERMISSIONS.keys()),
        }

    role = staff["role"]

    # Superuser bypasses everything
    if role == "superuser":
        return {
            "registered": True,
            "role": role,
            "denied": [],
            "all_permissions": list(PERMISSIONS.keys()),
        }

    denied = staff["denied_permissions"]
    allowed = [p for p in PERMISSIONS if p not in denied]
    return {
        "registered": True,
        "role": role,
        "denied": denied,
        "all_permissions": allowed,
    }
