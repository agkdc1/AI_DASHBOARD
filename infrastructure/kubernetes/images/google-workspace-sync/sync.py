#!/usr/bin/env python3
"""Google Workspace → Samba AD user sync.

Runs as a K8s CronJob every 6h. Syncs users from Google Workspace
directory into Samba AD LDAP (CN=Users,DC=shinbee,DC=local).

No password sync — GCPW handles authentication on PCs.
"""

import logging
import os
import sys

import ldap
import ldap.modlist
from google.oauth2 import service_account
from googleapiclient.discovery import build

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# Configuration from environment
GOOGLE_CREDENTIALS_FILE = os.environ.get(
    "GOOGLE_APPLICATION_CREDENTIALS", "/etc/gcs/key.json"
)
GOOGLE_DOMAIN = os.environ.get("GOOGLE_WORKSPACE_DOMAIN", "your-domain.com")
GOOGLE_ADMIN_EMAIL = os.environ.get("GOOGLE_ADMIN_EMAIL", "admin@your-domain.com")

SAMBA_LDAP_URL = os.environ.get(
    "SAMBA_AD_LDAP_URL", "ldap://samba-ad-internal.shinbee.svc.cluster.local:389"
)
SAMBA_ADMIN_PASSWORD = os.environ["SAMBA_ADMIN_PASSWORD"]
SAMBA_BASE_DN = os.environ.get("SAMBA_BASE_DN", "DC=shinbee,DC=local")
SAMBA_USERS_DN = f"CN=Users,{SAMBA_BASE_DN}"
SAMBA_BIND_DN = f"CN=Administrator,{SAMBA_USERS_DN}"

SCOPES = [
    "https://www.googleapis.com/auth/admin.directory.user.readonly",
]


def get_google_users() -> list[dict]:
    """Fetch all users from Google Workspace directory."""
    credentials = service_account.Credentials.from_service_account_file(
        GOOGLE_CREDENTIALS_FILE,
        scopes=SCOPES,
        subject=GOOGLE_ADMIN_EMAIL,
    )
    service = build("admin", "directory_v1", credentials=credentials)

    users = []
    request = service.users().list(domain=GOOGLE_DOMAIN, maxResults=500)
    while request is not None:
        response = request.execute()
        users.extend(response.get("users", []))
        request = service.users().list_next(request, response)

    log.info("Fetched %d users from Google Workspace", len(users))
    return users


def get_ad_users(conn: ldap.ldapobject.LDAPObject) -> dict[str, dict]:
    """Get existing AD users keyed by sAMAccountName."""
    results = conn.search_s(
        SAMBA_USERS_DN,
        ldap.SCOPE_ONELEVEL,
        "(&(objectClass=user)(sAMAccountName=*))",
        ["sAMAccountName", "cn", "mail", "displayName"],
    )
    ad_users = {}
    for dn, attrs in results:
        if dn is None:
            continue
        sam = attrs.get("sAMAccountName", [b""])[0].decode()
        if sam:
            ad_users[sam.lower()] = {
                "dn": dn,
                "cn": attrs.get("cn", [b""])[0].decode(),
                "mail": attrs.get("mail", [b""])[0].decode() if attrs.get("mail") else "",
                "displayName": attrs.get("displayName", [b""])[0].decode() if attrs.get("displayName") else "",
            }
    return ad_users


def create_ad_user(
    conn: ldap.ldapobject.LDAPObject,
    sam_account_name: str,
    display_name: str,
    given_name: str,
    surname: str,
    email: str,
) -> bool:
    """Create a new AD user object."""
    dn = f"CN={display_name},{SAMBA_USERS_DN}"
    upn = f"{sam_account_name}@{SAMBA_BASE_DN.replace('DC=', '').replace(',', '.')}".lower()

    attrs = {
        "objectClass": [b"top", b"person", b"organizationalPerson", b"user"],
        "sAMAccountName": [sam_account_name.encode()],
        "userPrincipalName": [upn.encode()],
        "cn": [display_name.encode()],
        "displayName": [display_name.encode()],
        "givenName": [given_name.encode()] if given_name else [],
        "sn": [surname.encode()] if surname else [display_name.encode()],
        "mail": [email.encode()],
        # Set password via userPassword (insecure LDAP is enabled for Grandstream)
        "userPassword": [f"Change-Me-{sam_account_name}!".encode()],
    }
    # Remove empty values
    attrs = {k: v for k, v in attrs.items() if v}

    try:
        add_list = ldap.modlist.addModlist(attrs)
        conn.add_s(dn, add_list)
        log.info("Created AD user: %s (%s)", sam_account_name, display_name)
        return True
    except ldap.ALREADY_EXISTS:
        log.debug("User %s already exists (CN conflict), skipping", sam_account_name)
        return False
    except ldap.LDAPError as e:
        log.error("Failed to create user %s: %s", sam_account_name, e)
        return False


def update_ad_user(
    conn: ldap.ldapobject.LDAPObject,
    dn: str,
    display_name: str,
) -> bool:
    """Update display name if changed."""
    try:
        mods = [(ldap.MOD_REPLACE, "displayName", [display_name.encode()])]
        conn.modify_s(dn, mods)
        log.info("Updated display name for %s", dn)
        return True
    except ldap.LDAPError as e:
        log.error("Failed to update %s: %s", dn, e)
        return False


def main():
    # Connect to Samba AD LDAP
    log.info("Connecting to Samba AD at %s", SAMBA_LDAP_URL)
    conn = ldap.initialize(SAMBA_LDAP_URL)
    conn.set_option(ldap.OPT_REFERRALS, 0)
    conn.simple_bind_s(SAMBA_BIND_DN, SAMBA_ADMIN_PASSWORD)

    # Get existing AD users
    ad_users = get_ad_users(conn)
    log.info("Found %d existing AD users", len(ad_users))

    # Get Google Workspace users
    google_users = get_google_users()

    created = 0
    updated = 0
    skipped = 0

    for guser in google_users:
        email = guser.get("primaryEmail", "")
        if not email:
            continue

        sam = email.split("@")[0].lower()
        given_name = guser.get("name", {}).get("givenName", "")
        surname = guser.get("name", {}).get("familyName", "")
        display_name = guser.get("name", {}).get("fullName", "") or f"{given_name} {surname}".strip()

        if sam in ad_users:
            # Check if display name needs update
            existing = ad_users[sam]
            if existing["displayName"] != display_name and display_name:
                update_ad_user(conn, existing["dn"], display_name)
                updated += 1
            else:
                skipped += 1
        else:
            if create_ad_user(conn, sam, display_name, given_name, surname, email):
                created += 1
            else:
                skipped += 1

    conn.unbind_s()

    log.info(
        "Sync complete: %d created, %d updated, %d skipped (total Google users: %d)",
        created,
        updated,
        skipped,
        len(google_users),
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.exception("Workspace sync failed")
        sys.exit(1)
