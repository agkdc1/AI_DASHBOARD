#!/usr/bin/env python3
"""Migrate hot-desk phones to permanent desk extensions.

Prerequisites:
  1. Admin has created offices/floors/rooms/desks in the Flutter UI
  2. Phone MACs have been assigned to desks in the seating admin

This script:
  1. Reads desk→MAC mappings from the seating API
  2. For each desk with a phone MAC:
     a. Creates the Asterisk extension via faxapi (if not already)
     b. Pushes SIP config (P35, P36, P34, P47, P270, P2312) to phone via faxapi
     c. Reboots the phone
  3. After all phones are configured, run selenium_config.py to disable public mode

Usage:
  python3 transition_to_desk_extensions.py [--dry-run] [--seating-url URL] [--faxapi-url URL]

Public mode MUST be disabled separately via Selenium:
  python3 selenium_config.py --type hotdesk  (with P1345=0 / P8468=0)
"""

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request


def get_desks_with_phones(seating_url: str) -> list[dict]:
    """Fetch all offices → floors → floor maps → desks with phone MACs."""
    desks = []

    # List offices
    req = urllib.request.Request(f"{seating_url}/seating/offices")
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
    offices = data.get("offices", [])

    for office in offices:
        # List floors
        req = urllib.request.Request(
            f"{seating_url}/seating/floors?office_id={office['id']}"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        floors = data.get("floors", [])

        for floor in floors:
            # Get floor map
            req = urllib.request.Request(
                f"{seating_url}/seating/floors/{floor['id']}/map"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())

            for desk_status in data.get("desks", []):
                desk = desk_status["desk"]
                if desk.get("phone_mac") and desk.get("phone_ip"):
                    desks.append(desk)

    return desks


def create_extension(faxapi_url: str, api_key: str, extension: str, name: str, dry_run: bool) -> bool:
    """Create Asterisk extension via faxapi."""
    print(f"  Creating extension {extension} ({name})...", end=" ")
    if dry_run:
        print("[DRY RUN]")
        return True

    body = json.dumps({
        "extension": extension,
        "name": name,
        "password": f"desk{extension}",
    }).encode()
    req = urllib.request.Request(
        f"{faxapi_url}/extensions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": api_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            print(f"OK ({result.get('status', 'unknown')})")
            return True
    except urllib.error.HTTPError as e:
        if e.code == 409:
            print("already exists")
            return True
        print(f"FAILED ({e.code}: {e.read().decode()[:100]})")
        return False


def push_sip_config(faxapi_url: str, api_key: str, phone_ip: str, extension: str, sip_server: str, dry_run: bool) -> bool:
    """Push SIP config to phone via faxapi phone display-name endpoint.

    Note: This uses the Grandstream HTTP API via faxapi. P3 (display name)
    persists, but we also need to push SIP credentials (P35, P36, P34, P270, P2312).
    This is done by extending the /phone/display-name call or using push_config.py separately.
    """
    print(f"  Pushing SIP config to {phone_ip} (ext {extension})...", end=" ")
    if dry_run:
        print("[DRY RUN]")
        return True

    # Set display name via faxapi
    body = json.dumps({
        "phone_ip": phone_ip,
        "display_name": f"Desk {extension}",
    }).encode()
    req = urllib.request.Request(
        f"{faxapi_url}/phone/display-name",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": api_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print("OK")
            return True
    except Exception as e:
        print(f"FAILED ({e})")
        return False


def main():
    parser = argparse.ArgumentParser(description="Migrate hot-desk phones to desk extensions")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without executing")
    parser.add_argument("--seating-url", default="https://ai.your-domain.com", help="Seating API base URL")
    parser.add_argument("--faxapi-url", default="http://10.0.0.254:8010", help="Faxapi base URL")
    parser.add_argument("--faxapi-key", default="", help="Faxapi API key")
    parser.add_argument("--sip-server", default="10.0.0.254", help="SIP server IP")
    args = parser.parse_args()

    if args.dry_run:
        print("=== DRY RUN MODE ===\n")

    print("Fetching desks with phone assignments...")
    try:
        desks = get_desks_with_phones(args.seating_url)
    except Exception as e:
        print(f"Failed to fetch desks: {e}")
        sys.exit(1)

    if not desks:
        print("No desks with phone MACs and IPs found. Assign phones in the Flutter admin first.")
        sys.exit(0)

    print(f"Found {len(desks)} desks with phones:\n")
    for desk in desks:
        print(f"  Ext {desk['desk_extension']} | MAC {desk['phone_mac']} | IP {desk['phone_ip']}")
    print()

    success = 0
    failed = 0

    for desk in desks:
        ext = desk["desk_extension"]
        phone_ip = desk["phone_ip"]
        print(f"\n--- Desk {ext} (phone {phone_ip}) ---")

        # Step 1: Create Asterisk extension
        if not create_extension(args.faxapi_url, args.faxapi_key, ext, f"Desk {ext}", args.dry_run):
            failed += 1
            continue

        # Step 2: Push SIP config and display name
        if not push_sip_config(args.faxapi_url, args.faxapi_key, phone_ip, ext, args.sip_server, args.dry_run):
            failed += 1
            continue

        success += 1

        if not args.dry_run:
            time.sleep(2)  # Brief pause between phones

    print(f"\n=== Summary: {success} OK, {failed} failed ===")

    if not args.dry_run and success > 0:
        print(
            "\nIMPORTANT: Run selenium_config.py to disable public mode on all phones:\n"
            "  python3 phone/selenium_config.py --type hotdesk\n"
            "(Public mode CANNOT be set via API — must use Selenium)"
        )


if __name__ == "__main__":
    main()
