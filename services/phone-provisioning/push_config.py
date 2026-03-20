#!/usr/bin/env python3
"""Push provisioning config to all Grandstream GXP-1760W phones via HTTP API.

Discovers phone IPs from ARP table (c0:74:ad OUI), logs in to each phone
via dologin, and pushes the full provisioning config.

Usage:
    python3 phone/push_config.py                  # push to all phones
    python3 phone/push_config.py --ip 10.0.7.25   # push to a single phone
    python3 phone/push_config.py --dry-run         # show what would be pushed
"""

import argparse
import csv
import re
import subprocess
import sys
import urllib.parse
import urllib.request
import json
from pathlib import Path

import yaml

GRANDSTREAM_OUI = "c0:74:ad"
LOGIN_TIMEOUT = 5
POST_TIMEOUT = 10


def load_config(repo_root: Path) -> dict:
    with open(repo_root / "config.yaml") as f:
        return yaml.safe_load(f)


def mac_normalize(mac: str) -> str:
    raw = re.sub(r"[:\-.]", "", mac).lower()
    return raw.zfill(12)


def mac_wifi(eth_mac: str) -> str:
    clean = mac_normalize(eth_mac)
    return f"{int(clean, 16) + 1:012x}"


def discover_phones() -> dict[str, str]:
    """Discover Grandstream phones from ARP table. Returns {ip: wifi_mac}."""
    result = subprocess.run(["arp", "-a"], capture_output=True, text=True)
    phones = {}
    for line in result.stdout.splitlines():
        m = re.search(r"\((\d+\.\d+\.\d+\.\d+)\)\s+at\s+([\da-f:]+)", line)
        if m:
            ip, mac = m.group(1), m.group(2)
            if mac.startswith(GRANDSTREAM_OUI):
                phones[ip] = mac
    return phones


def wifi_mac_to_eth(wifi_mac: str) -> str:
    """Convert WiFi MAC back to ETH MAC (subtract 1)."""
    clean = re.sub(r"[:\-.]", "", wifi_mac).lower().zfill(12)
    eth_int = int(clean, 16) - 1
    return f"{eth_int:012x}"


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_phone_lookup(repo_root: Path, cfg: dict) -> dict:
    """Build {eth_mac: {type, ext, name}} lookup from CSVs."""
    phone = cfg["phone"]
    lookup = {}

    for row in read_csv(repo_root / phone["csv_fixed"]):
        eth = mac_normalize(row["MAC"])
        lookup[eth] = {"type": "fixed", "ext": row["NUMBER"], "name": row["NAME"]}

    for row in read_csv(repo_root / phone["csv_free_phones"]):
        eth = mac_normalize(row["MAC"])
        lookup[eth] = {"type": "hotdesk", "ext": "", "name": "hot-desk"}

    return lookup


def http_request(url: str, data: dict | None = None, headers: dict | None = None) -> dict | None:
    """Make HTTP request, return parsed JSON or None on failure."""
    hdrs = headers or {}
    try:
        if data is not None:
            encoded = urllib.parse.urlencode(data).encode("utf-8")
            req = urllib.request.Request(url, data=encoded, headers=hdrs)
        else:
            req = urllib.request.Request(url, headers=hdrs)
        with urllib.request.urlopen(req, timeout=POST_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"    HTTP error: {e}")
        return None


def login(ip: str, password: str) -> tuple[str | None, str | None]:
    """Login to phone via dologin. Returns (sid, cookie_header) or (None, None)."""
    url = f"http://{ip}/cgi-bin/dologin"
    data = urllib.parse.urlencode({"password": password}).encode("utf-8")
    headers = {
        "Referer": f"http://{ip}/",
        "Origin": f"http://{ip}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    try:
        req = urllib.request.Request(url, data=data, headers=headers)
        with urllib.request.urlopen(req, timeout=LOGIN_TIMEOUT) as resp:
            # Extract session cookie
            cookies = resp.headers.get_all("Set-Cookie") or []
            cookie_parts = []
            for c in cookies:
                name_val = c.split(";")[0]
                cookie_parts.append(name_val)
            cookie_header = "; ".join(cookie_parts)

            body = json.loads(resp.read().decode("utf-8"))
            if body.get("response") == "success":
                sid = body["body"]["sid"]
                return sid, cookie_header
            else:
                print(f"    Login failed: {body}")
                return None, None
    except Exception as e:
        print(f"    Login error: {e}")
        return None, None


def push_config(ip: str, sid: str, cookie: str, params: dict) -> bool:
    """Push config values via api.values.post with urlencoded form data."""
    url = f"http://{ip}/cgi-bin/api.values.post"
    payload = {"sid": sid}
    payload.update(params)

    encoded = urllib.parse.urlencode(payload).encode("utf-8")
    headers = {
        "Cookie": cookie,
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": f"http://{ip}/",
    }
    try:
        req = urllib.request.Request(url, data=encoded, headers=headers)
        with urllib.request.urlopen(req, timeout=POST_TIMEOUT) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            if body.get("response") == "success" and body.get("body", {}).get("status") == "right":
                return True
            else:
                print(f"    POST response: {body}")
                return False
    except Exception as e:
        print(f"    POST error: {e}")
        return False


def reboot(ip: str, password: str) -> bool:
    """Trigger save+reboot via API."""
    url = f"http://{ip}/cgi-bin/api-sys_operation"
    params = urllib.parse.urlencode({"passcode": password, "request": "REBOOT"})
    try:
        req = urllib.request.Request(f"{url}?{params}")
        with urllib.request.urlopen(req, timeout=LOGIN_TIMEOUT) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return body.get("response") == "success"
    except Exception as e:
        print(f"    Reboot error: {e}")
        return False


def build_common_params(cfg: dict) -> dict:
    """Build common P-code params (LDAP, WiFi, NTP, provisioning)."""
    phone = cfg["phone"]
    ldap = phone["ldap"]
    params = {}

    # WiFi
    if phone["wifi"]["ssid"]:
        params["P7801"] = "1"
        params["P7802"] = phone["wifi"]["ssid"]
        params["P7803"] = "4"  # WPA2-PSK
        params["P7804"] = phone["wifi"]["psk"]

    # NTP
    params["P30"] = phone["ntp_server"]
    params["P64"] = phone["timezone_offset"]

    # Provisioning & Firmware Upgrade
    prov_url = phone["provision"]["url"]
    params["P192"] = prov_url       # Config server path
    params["P237"] = prov_url       # Firmware server path
    params["P212"] = "1"            # Firmware upgrade via: 1=HTTP
    params["P194"] = "1"            # Config upgrade via: 1=HTTP
    params["P193"] = "10080"        # Config check interval (min) — 7 days
    params["P285"] = "1"            # Check new firmware at boot
    params["P6767"] = "1"           # Automatic upgrade enabled

    # LDAP Phonebook (P-codes verified on firmware 1.0.1.116)
    params["P8500"] = ldap["server"]
    params["P8501"] = str(ldap["port"])
    params["P8502"] = "3"  # LDAP protocol version (LDAPv3)
    params["P8505"] = ldap["base_dn"]  # Search Base
    params["P8506"] = "(objectClass=inetOrgPerson)"  # Search filter
    params["P8507"] = "50"  # Max hits
    params["P8510"] = ldap["name_attr"]
    params["P8511"] = ldap["number_attr"]
    params["P8516"] = "0"  # LDAP lookup for incoming call

    # Display
    params["P75"] = "1"   # Date format YYYY-MM-DD
    params["P102"] = "2"  # LCD contrast

    # Ring volume
    params["P8352"] = "7"  # Speaker ring volume (0-7, max)

    # Idle screen softkeys
    # Softkey 1: LDAP Search (mode=29), Softkey 2: Menu (mode=27)
    params["P1363"] = "29"  # Idle softkey 1 mode: LDAP Search
    params["P1364"] = "0"   # Idle softkey 1 account
    params["P1365"] = "0"   # Idle softkey 1 (reserved)
    params["P1366"] = "27"  # Idle softkey 2 mode: Menu
    params["P1367"] = "0"   # Idle softkey 2 account
    params["P1368"] = "0"   # Idle softkey 2 (reserved)

    return params


def build_fixed_params(ext: str, password: str, cfg: dict, name: str = "") -> dict:
    """Build SIP account params for a fixed phone."""
    phone = cfg["phone"]
    display_name = name if name else ext
    return {
        "P270": "1",   # Account 1 active
        "P47": phone["sip_server"],
        "P48": phone["sip_server"],  # Outbound proxy
        "P35": ext,    # SIP User ID
        "P36": ext,    # Auth ID
        "P34": password,  # Auth password
        "P3": display_name,  # Account name / display
        "P52": str(phone["sip_port"]),
        "P2312": "1",  # Account enable
        "P2327": "0",  # SIP Transport: UDP
        "P8468": "0",  # Public mode disabled
        "P2380": "1",  # Account ringtone
    }


def build_hotdesk_params(cfg: dict) -> dict:
    """Build hot-desk params (account active but no credentials, public mode login prompt)."""
    phone = cfg["phone"]
    return {
        "P270": "1",   # Account 1 active (required for public mode login screen)
        "P2312": "1",  # Account enabled
        "P8468": "1",  # Public mode / hot desking
        "P35": "",     # Clear SIP User ID
        "P36": "",     # Clear Auth ID
        "P34": "",     # Clear Auth Password
        "P3": "",      # Clear display name
        "P47": phone["sip_server"],
        "P48": phone["sip_server"],
        "P52": str(phone["sip_port"]),
        "P2327": "0",  # SIP Transport: UDP
    }


def main():
    parser = argparse.ArgumentParser(description="Push config to Grandstream phones")
    parser.add_argument("--ip", help="Push to a single phone IP")
    parser.add_argument("--type", choices=["fixed", "hotdesk"], help="Only push to this phone type")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be pushed")
    parser.add_argument("--no-reboot", action="store_true", help="Don't reboot phones after push")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    cfg = load_config(repo_root)
    phone_cfg = cfg["phone"]
    admin_pw = phone_cfg["admin_password"]

    # Read existing SIP passwords
    pjsip_path = repo_root / phone_cfg["pjsip_auth_conf"]
    sip_passwords = {}
    if pjsip_path.exists():
        for line in pjsip_path.read_text().splitlines():
            line = line.strip()
            m = re.match(r"^\[(\d+)-auth\]$", line)
            if m:
                current_ext = m.group(1)
            elif line.startswith("password=") and "current_ext" in dir():
                sip_passwords[current_ext] = line.split("=", 1)[1]

    # Build phone MAC → info lookup
    phone_lookup = build_phone_lookup(repo_root, cfg)

    # Discover phones or use single IP
    if args.ip:
        phones = {args.ip: "manual"}
    else:
        phones = discover_phones()
        if not phones:
            print("No Grandstream phones found in ARP table.")
            sys.exit(1)

    print(f"Found {len(phones)} phone(s)\n")

    # Build common config
    common_params = build_common_params(cfg)

    success_count = 0
    fail_count = 0

    for ip, wifi_mac in sorted(phones.items()):
        eth_mac = wifi_mac_to_eth(wifi_mac) if wifi_mac != "manual" else "unknown"
        info = phone_lookup.get(eth_mac, {"type": "unknown", "ext": "?", "name": "?"})

        # Skip if type filter is set and doesn't match
        if args.type and info["type"] != args.type:
            continue

        label = f"{ip} [{eth_mac}] {info['type']}"
        if info["type"] == "fixed":
            label += f" ext={info['ext']} ({info['name']})"

        print(f"  {label}")

        # Build full params for this phone
        params = dict(common_params)
        if info["type"] == "fixed":
            ext = info["ext"]
            pw = sip_passwords.get(ext, f"{phone_cfg['sip_password_prefix']}{ext}")
            params.update(build_fixed_params(ext, pw, cfg, name=info["name"]))
        elif info["type"] == "hotdesk":
            params.update(build_hotdesk_params(cfg))
        else:
            # Unknown phone — push common params + hotdesk as default
            params.update(build_hotdesk_params(cfg))
            print(f"    WARNING: unknown phone, applying hot-desk config")

        if args.dry_run:
            print(f"    [DRY] Would push {len(params)} P-codes")
            success_count += 1
            continue

        # Login
        sid, cookie = login(ip, admin_pw)
        if not sid:
            print(f"    FAILED to login")
            fail_count += 1
            continue

        # Push config
        if push_config(ip, sid, cookie, params):
            print(f"    OK — pushed {len(params)} P-codes")
            success_count += 1
        else:
            print(f"    FAILED to push config")
            fail_count += 1
            continue

        # Reboot
        if not args.no_reboot:
            if reboot(ip, admin_pw):
                print(f"    Rebooting...")
            else:
                print(f"    WARNING: reboot failed (config was saved)")

    print(f"\nDone: {success_count} OK, {fail_count} failed")
    if fail_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
