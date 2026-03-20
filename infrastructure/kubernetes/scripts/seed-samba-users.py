#!/usr/bin/env python3
"""Seed Samba AD with users from the existing OpenLDAP ldap-seed.ldif.

Reads services/phone-provisioning/ldap-seed.ldif and creates equivalent AD user objects in
CN=Users,DC=shinbee,DC=local.

Usage:
    python3 infrastructure/kubernetes/scripts/seed-samba-users.py [--ldap-url URL] [--password PW]

Defaults:
    --ldap-url  ldap://10.0.0.250:389
    --password  (from env SAMBA_ADMIN_PASSWORD)
"""

import argparse
import os
import re
import sys

import ldap
import ldap.modlist


def parse_ldif(path: str) -> list[dict]:
    """Parse a simple LDIF file into a list of entry dicts."""
    entries = []
    current: dict[str, list[str]] = {}
    current_dn = ""

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                if current_dn and current:
                    entries.append({"dn": current_dn, "attrs": current})
                    current = {}
                    current_dn = ""
                continue
            if line.startswith("dn: "):
                current_dn = line[4:]
                current = {}
            elif ": " in line:
                key, val = line.split(": ", 1)
                current.setdefault(key, []).append(val)

    # Last entry
    if current_dn and current:
        entries.append({"dn": current_dn, "attrs": current})

    return entries


def main():
    parser = argparse.ArgumentParser(description="Seed Samba AD users from LDIF")
    parser.add_argument("--ldap-url", default="ldap://10.0.0.250:389")
    parser.add_argument("--password", default=os.environ.get("SAMBA_ADMIN_PASSWORD", ""))
    parser.add_argument("--ldif", default="services/phone-provisioning/ldap-seed.ldif")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.password:
        print("ERROR: Set SAMBA_ADMIN_PASSWORD env var or use --password")
        sys.exit(1)

    base_dn = "DC=shinbee,DC=local"
    users_dn = f"CN=Users,{base_dn}"
    bind_dn = f"CN=Administrator,{users_dn}"

    # Parse LDIF
    entries = parse_ldif(args.ldif)
    # Filter to only inetOrgPerson entries (skip OU)
    users = [e for e in entries if "inetOrgPerson" in e["attrs"].get("objectClass", [])]
    print(f"Found {len(users)} users in {args.ldif}")

    if args.dry_run:
        for u in users:
            uid = u["attrs"].get("uid", [""])[0]
            cn = u["attrs"].get("cn", [""])[0]
            print(f"  Would create: sAMAccountName={uid}, cn={cn}")
        return

    # Connect to Samba AD
    print(f"Connecting to {args.ldap_url}...")
    conn = ldap.initialize(args.ldap_url)
    conn.set_option(ldap.OPT_REFERRALS, 0)
    conn.simple_bind_s(bind_dn, args.password)
    print("Connected to Samba AD")

    created = 0
    skipped = 0
    failed = 0

    for u in users:
        uid = u["attrs"].get("uid", [""])[0]
        cn = u["attrs"].get("cn", [""])[0]
        sn = u["attrs"].get("sn", [cn])[0]
        phone = u["attrs"].get("telephoneNumber", [uid])[0]
        password = u["attrs"].get("userPassword", [f"1212{uid}"])[0]

        dn = f"CN={cn},{users_dn}"
        upn = f"{uid}@your-domain.local"

        attrs = {
            "objectClass": [b"top", b"person", b"organizationalPerson", b"user"],
            "sAMAccountName": [uid.encode()],
            "userPrincipalName": [upn.encode()],
            "cn": [cn.encode()],
            "sn": [sn.encode()],
            "displayName": [cn.encode()],
            "telephoneNumber": [phone.encode()],
            "userPassword": [password.encode()],
        }

        try:
            add_list = ldap.modlist.addModlist(attrs)
            conn.add_s(dn, add_list)
            print(f"  Created: {uid} ({cn})")
            created += 1
        except ldap.ALREADY_EXISTS:
            print(f"  Skipped (exists): {uid} ({cn})")
            skipped += 1
        except ldap.LDAPError as e:
            print(f"  FAILED: {uid} ({cn}): {e}")
            failed += 1

    conn.unbind_s()
    print(f"\nDone: {created} created, {skipped} skipped, {failed} failed")


if __name__ == "__main__":
    main()
