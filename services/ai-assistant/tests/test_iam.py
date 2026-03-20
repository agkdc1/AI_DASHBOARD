"""Tests for the IAM (staff management + permissions) module."""

import os
import tempfile

import pytest

# Override IAM DB path before any import
_tmp = tempfile.mktemp(suffix=".db")
os.environ["AI_IAM_DB_PATH"] = _tmp

from iam import db, service
from iam.permissions import PERMISSIONS, ROLE_GUARANTEED


@pytest.fixture(autouse=True)
async def _fresh_db():
    """Create a fresh IAM database for each test."""
    import aiosqlite

    # Reset the DB path each time
    from config import settings
    object.__setattr__(settings, "iam_db_path", tempfile.mktemp(suffix=".db"))
    await db.init_db()
    yield
    # Cleanup
    try:
        os.unlink(settings.iam_db_path)
    except FileNotFoundError:
        pass


class TestInitDb:
    async def test_seeds_superuser(self):
        """Superuser is auto-created on init."""
        from config import settings
        staff = await service.get_staff(settings.superuser_email)
        assert staff is not None
        assert staff["role"] == "superuser"

    async def test_idempotent(self):
        """Calling init_db twice doesn't fail or duplicate."""
        await db.init_db()
        staff_list = await service.list_staff()
        superusers = [s for s in staff_list if s["role"] == "superuser"]
        assert len(superusers) == 1


class TestRegisterStaff:
    async def test_create(self):
        result = await service.register_staff(
            email="user@test.com",
            display_name="Test User",
        )
        assert result["email"] == "user@test.com"
        assert result["role"] == "staff"
        assert result["denied_permissions"] == []

    async def test_create_with_role(self):
        result = await service.register_staff(
            email="admin@test.com",
            display_name="Admin",
            role="admin",
        )
        assert result["role"] == "admin"

    async def test_invalid_role_raises(self):
        with pytest.raises(ValueError, match="Invalid role"):
            await service.register_staff(
                email="bad@test.com",
                display_name="Bad",
                role="invalid",
            )

    async def test_duplicate_raises(self):
        await service.register_staff(email="dup@test.com", display_name="Dup")
        with pytest.raises(Exception):
            await service.register_staff(email="dup@test.com", display_name="Dup2")


class TestGetStaff:
    async def test_found(self):
        await service.register_staff(email="find@test.com", display_name="Find")
        staff = await service.get_staff("find@test.com")
        assert staff is not None
        assert staff["display_name"] == "Find"

    async def test_not_found(self):
        staff = await service.get_staff("nobody@test.com")
        assert staff is None


class TestListStaff:
    async def test_includes_all(self):
        await service.register_staff(email="a@test.com", display_name="A")
        await service.register_staff(email="b@test.com", display_name="B")
        staff_list = await service.list_staff()
        emails = [s["email"] for s in staff_list]
        assert "a@test.com" in emails
        assert "b@test.com" in emails


class TestUpdateStaff:
    async def test_update_name(self):
        await service.register_staff(email="upd@test.com", display_name="Old")
        result = await service.update_staff("upd@test.com", display_name="New")
        assert result["display_name"] == "New"

    async def test_update_role(self):
        await service.register_staff(email="role@test.com", display_name="Role")
        result = await service.update_staff("role@test.com", role="admin")
        assert result["role"] == "admin"

    async def test_update_nonexistent_returns_none(self):
        result = await service.update_staff("ghost@test.com", display_name="X")
        assert result is None

    async def test_invalid_role_raises(self):
        await service.register_staff(email="badrole@test.com", display_name="X")
        with pytest.raises(ValueError, match="Invalid role"):
            await service.update_staff("badrole@test.com", role="fake")

    async def test_role_change_clears_guaranteed_deny_rules(self):
        """Changing role to admin should remove deny rules for guaranteed perms."""
        await service.register_staff(email="clear@test.com", display_name="Clear")
        # Add a deny rule for phone.admin (which admin role guarantees)
        await service.set_deny_rules("clear@test.com", ["phone.admin"])
        staff = await service.get_staff("clear@test.com")
        assert "phone.admin" in staff["denied_permissions"]

        # Now promote to admin
        await service.update_staff("clear@test.com", role="admin")
        staff = await service.get_staff("clear@test.com")
        assert "phone.admin" not in staff["denied_permissions"]


class TestDeleteStaff:
    async def test_delete(self):
        await service.register_staff(email="del@test.com", display_name="Del")
        result = await service.delete_staff("del@test.com")
        assert result is True
        assert await service.get_staff("del@test.com") is None

    async def test_delete_nonexistent(self):
        result = await service.delete_staff("nobody@test.com")
        assert result is False

    async def test_cannot_delete_superuser(self):
        from config import settings
        with pytest.raises(ValueError, match="Cannot delete superuser"):
            await service.delete_staff(settings.superuser_email)


class TestDenyRules:
    async def test_set_and_get(self):
        await service.register_staff(email="deny@test.com", display_name="Deny")
        result = await service.set_deny_rules("deny@test.com", ["wiki.edit", "wiki.view"])
        assert set(result["denied_permissions"]) == {"wiki.edit", "wiki.view"}

    async def test_replace_existing(self):
        await service.register_staff(email="rep@test.com", display_name="Rep")
        await service.set_deny_rules("rep@test.com", ["wiki.edit"])
        result = await service.set_deny_rules("rep@test.com", ["orders.view"])
        assert result["denied_permissions"] == ["orders.view"]

    async def test_clear_all(self):
        await service.register_staff(email="clr@test.com", display_name="Clr")
        await service.set_deny_rules("clr@test.com", ["wiki.edit"])
        result = await service.set_deny_rules("clr@test.com", [])
        assert result["denied_permissions"] == []

    async def test_invalid_permission_raises(self):
        await service.register_staff(email="inv@test.com", display_name="Inv")
        with pytest.raises(ValueError, match="Invalid permissions"):
            await service.set_deny_rules("inv@test.com", ["fake.perm"])

    async def test_cannot_deny_guaranteed(self):
        await service.register_staff(
            email="guar@test.com", display_name="Guar", role="admin"
        )
        with pytest.raises(ValueError, match="guaranteed by role"):
            await service.set_deny_rules("guar@test.com", ["staff.manage"])

    async def test_nonexistent_returns_none(self):
        result = await service.set_deny_rules("ghost@test.com", [])
        assert result is None

    async def test_cascade_delete(self):
        """Deny rules are deleted when staff member is deleted."""
        await service.register_staff(email="cas@test.com", display_name="Cas")
        await service.set_deny_rules("cas@test.com", ["wiki.edit"])
        await service.delete_staff("cas@test.com")
        # Re-register and verify clean slate
        await service.register_staff(email="cas@test.com", display_name="Cas2")
        staff = await service.get_staff("cas@test.com")
        assert staff["denied_permissions"] == []


class TestResolvePermissions:
    async def test_unregistered_user_gets_all(self):
        result = await service.resolve_permissions("nobody@test.com")
        assert result["registered"] is False
        assert result["role"] == "guest"
        assert result["denied"] == []
        assert set(result["all_permissions"]) == set(PERMISSIONS.keys())

    async def test_superuser_gets_all(self):
        from config import settings
        result = await service.resolve_permissions(settings.superuser_email)
        assert result["registered"] is True
        assert result["role"] == "superuser"
        assert result["denied"] == []
        assert set(result["all_permissions"]) == set(PERMISSIONS.keys())

    async def test_staff_with_deny_rules(self):
        await service.register_staff(email="deny@test.com", display_name="Deny")
        await service.set_deny_rules("deny@test.com", ["wiki.edit", "phone.admin"])
        result = await service.resolve_permissions("deny@test.com")
        assert result["registered"] is True
        assert result["role"] == "staff"
        assert set(result["denied"]) == {"wiki.edit", "phone.admin"}
        assert "wiki.edit" not in result["all_permissions"]
        assert "phone.admin" not in result["all_permissions"]
        assert "wiki.view" in result["all_permissions"]

    async def test_admin_has_guaranteed_perms(self):
        await service.register_staff(
            email="adm@test.com", display_name="Admin", role="admin"
        )
        result = await service.resolve_permissions("adm@test.com")
        assert "staff.manage" in result["all_permissions"]
        assert "phone.admin" in result["all_permissions"]

    async def test_staff_no_deny_gets_all(self):
        await service.register_staff(email="full@test.com", display_name="Full")
        result = await service.resolve_permissions("full@test.com")
        assert result["denied"] == []
        assert set(result["all_permissions"]) == set(PERMISSIONS.keys())
