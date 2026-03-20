"""Integration tests for LDAP (phone provisioning).

Run with: RUN_INTEGRATION=1 pytest -m integration tests/integration/test_ldap.py -v
"""

import pytest

from config import settings

pytestmark = [pytest.mark.integration]

TEST_UID = "399"
TEST_DN = f"uid={TEST_UID},ou=users,{settings.ldap_base_dn}"


@pytest.fixture
def phone_service_live():
    """PhoneService with real LDAP connection."""
    from phone.service import PhoneService
    return PhoneService()


class TestLDAP:
    def test_connection(self, phone_service_live):
        """Verify LDAP connection works."""
        conn = phone_service_live._ensure_ldap()
        assert conn is not None

    @pytest.mark.asyncio
    async def test_create_user(self, phone_service_live, ldap_cleanup):
        result = await phone_service_live.create_user(TEST_UID, "TEST-USER", "testpass")
        assert result.get("uid") == TEST_UID
        ldap_cleanup.append(TEST_DN)

    @pytest.mark.asyncio
    async def test_get_user(self, phone_service_live, ldap_cleanup):
        await phone_service_live.create_user(TEST_UID, "TEST-GET", "pass")
        ldap_cleanup.append(TEST_DN)

        user = await phone_service_live.get_user(TEST_UID)
        assert user is not None
        assert user["uid"] == TEST_UID
        assert user["cn"] == "TEST-GET"

    @pytest.mark.asyncio
    async def test_list_includes_created(self, phone_service_live, ldap_cleanup):
        await phone_service_live.create_user(TEST_UID, "TEST-LIST", "pass")
        ldap_cleanup.append(TEST_DN)

        users = await phone_service_live.list_users()
        uids = [u["uid"] for u in users]
        assert TEST_UID in uids

    @pytest.mark.asyncio
    async def test_find_by_email(self, phone_service_live, ldap_cleanup):
        # Create user with email attribute via raw LDAP
        import ldap as ldap_lib
        import ldap.modlist
        conn = phone_service_live._ensure_ldap()
        attrs = {
            "objectClass": [b"inetOrgPerson"],
            "uid": [TEST_UID.encode()],
            "cn": [b"TEST-EMAIL"],
            "sn": [b"TEST-EMAIL"],
            "telephoneNumber": [TEST_UID.encode()],
            "userPassword": [b"pass"],
            "mail": [b"test-integration@test.com"],
        }
        add_list = ldap_lib.modlist.addModlist(attrs)
        conn.add_s(TEST_DN, add_list)
        ldap_cleanup.append(TEST_DN)

        user = await phone_service_live.find_by_email("test-integration@test.com")
        assert user is not None
        assert user["uid"] == TEST_UID

    @pytest.mark.asyncio
    async def test_update_user(self, phone_service_live, ldap_cleanup):
        await phone_service_live.create_user(TEST_UID, "TEST-UPDATE", "pass")
        ldap_cleanup.append(TEST_DN)

        result = await phone_service_live.update_user(TEST_UID, cn="UPDATED-NAME")
        assert result.get("cn") == "UPDATED-NAME" or result.get("updated")

    @pytest.mark.asyncio
    async def test_delete_user(self, phone_service_live, ldap_cleanup):
        await phone_service_live.create_user(TEST_UID, "TEST-DELETE", "pass")
        # Don't add to ldap_cleanup — we delete manually

        result = await phone_service_live.delete_user(TEST_UID)
        assert result is True

        # Verify gone
        user = await phone_service_live.get_user(TEST_UID)
        assert user is None

    @pytest.mark.asyncio
    async def test_next_available_extension(self, phone_service_live):
        ext = await phone_service_live.next_available_extension()
        assert ext.isdigit()
        assert 300 <= int(ext) <= 399
