#!/usr/bin/env python3
"""Generate Grandstream GXP-1760W provisioning files and LDAP seed.

Reads CSVs + config.yaml → outputs:
  services/phone-provisioning/output/cfg<mac>.xml     — per-phone provisioning (14 files)
  services/phone-provisioning/output/cfg<wifi_mac>.xml — symlinks for WiFi MACs (14 symlinks)
  services/phone-provisioning/ldap-seed.ldif          — LDAP seed data (17 users)
  services/phone-provisioning/create-extensions.sh    — Legacy FreePBX extension creation (superseded by confgen)

Usage:
    python3 services/phone-provisioning/generate.py
    python3 services/phone-provisioning/generate.py --dry-run
"""

import argparse
import csv
import os
import re
import sys
from pathlib import Path
from textwrap import dedent

import yaml


def load_config(repo_root: Path) -> dict:
    with open(repo_root / "config.yaml") as f:
        return yaml.safe_load(f)


def mac_normalize(mac: str) -> str:
    """Normalize MAC to lowercase 12-char hex: AA:BB:CC:DD:EE:FF → aabbccddeeff."""
    raw = re.sub(r"[:\-.]", "", mac).lower()
    return raw.zfill(12)  # zero-pad if short


def mac_wifi(eth_mac: str) -> str:
    """Compute WiFi MAC = ETH MAC + 1 (Grandstream convention)."""
    clean = mac_normalize(eth_mac)
    incremented = int(clean, 16) + 1
    return f"{incremented:012x}"


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_pjsip_passwords(path: Path) -> dict[str, str]:
    """Parse pjsip.auth.conf → {extension: password}."""
    passwords = {}
    current_ext = None
    for line in path.read_text().splitlines():
        line = line.strip()
        m = re.match(r"^\[(\d+)-auth\]$", line)
        if m:
            current_ext = m.group(1)
        elif line.startswith("password=") and current_ext:
            passwords[current_ext] = line.split("=", 1)[1]
    return passwords


# ---------------------------------------------------------------------------
# Grandstream XML provisioning
# ---------------------------------------------------------------------------

def xml_header() -> str:
    return '<?xml version="1.0" encoding="UTF-8" ?>\n<gs_provision version="1">\n<config version="1">\n'


def xml_footer() -> str:
    return "</config>\n</gs_provision>\n"


def xml_param(p_code: str, value: str) -> str:
    return f'<P{p_code}>{value}</P{p_code}>\n'


def generate_common_params(cfg: dict) -> str:
    """Generate XML params common to all phones (WiFi, NTP, LDAP, provisioning)."""
    phone = cfg["phone"]
    lines = []

    # --- WiFi ---
    if phone["wifi"]["ssid"]:
        lines.append(xml_param("7801", "1"))                         # WiFi enable
        lines.append(xml_param("7802", phone["wifi"]["ssid"]))       # SSID
        lines.append(xml_param("7803", "4"))                         # WPA2-PSK
        lines.append(xml_param("7804", phone["wifi"]["psk"]))        # PSK
    else:
        lines.append(xml_param("7801", "0"))                         # WiFi disable

    # --- NTP ---
    lines.append(xml_param("30", phone["ntp_server"]))               # NTP server
    lines.append(xml_param("64", phone["timezone_offset"]))          # Timezone offset

    # --- Provisioning & Firmware Upgrade ---
    prov_url = phone["provision"]["url"]
    lines.append(xml_param("192", prov_url))                         # Config server path
    lines.append(xml_param("237", prov_url))                         # Firmware server path
    lines.append(xml_param("212", "1"))                              # Firmware upgrade via: 1=HTTP
    lines.append(xml_param("194", "1"))                              # Config upgrade via: 1=HTTP
    lines.append(xml_param("193", "10080"))                          # Config check interval (min) — 7 days
    lines.append(xml_param("285", "1"))                              # Check new firmware at boot
    lines.append(xml_param("6767", "1"))                             # Automatic upgrade enabled

    # --- LDAP Phonebook (Samba AD) ---
    # P-code mapping verified on GXP1760W firmware 1.0.1.116
    ldap = phone["ldap"]
    lines.append(xml_param("8500", ldap["server"]))                  # LDAP server (Samba AD VIP)
    lines.append(xml_param("8501", str(ldap["port"])))               # LDAP port
    lines.append(xml_param("8502", "3"))                             # LDAP protocol version (3=LDAPv3)
    lines.append(xml_param("8505", ldap["base_dn"]))                 # Search Base (CN=Users,DC=shinbee,DC=local)
    lines.append(xml_param("8506", "(&(objectClass=user)(telephoneNumber=*))"))  # AD user search filter
    lines.append(xml_param("8507", "50"))                            # Max hits
    lines.append(xml_param("8510", ldap["name_attr"]))               # Name attribute
    lines.append(xml_param("8511", ldap["number_attr"]))             # Number attribute
    lines.append(xml_param("8516", "0"))                             # LDAP lookup for incoming call

    # --- Admin password ---
    lines.append(xml_param("2", phone["admin_password"]))            # Admin password

    # --- Display ---
    lines.append(xml_param("75", "1"))                               # Date display format (YYYY-MM-DD)
    lines.append(xml_param("102", "2"))                              # LCD contrast

    # --- Ring volume ---
    lines.append(xml_param("8352", "7"))                             # Speaker ring volume (0-7, max)

    # --- Idle screen softkeys ---
    # Softkey 1: LDAP Search (mode=29), Softkey 2: Menu (mode=27)
    lines.append(xml_param("1363", "29"))                            # Idle softkey 1 mode: LDAP Search
    lines.append(xml_param("1364", "0"))                             # Idle softkey 1 account
    lines.append(xml_param("1365", "0"))                             # Idle softkey 1 (reserved)
    lines.append(xml_param("1366", "27"))                            # Idle softkey 2 mode: Menu
    lines.append(xml_param("1367", "0"))                             # Idle softkey 2 account
    lines.append(xml_param("1368", "0"))                             # Idle softkey 2 (reserved)

    return "".join(lines)


def generate_sip_params(ext: str, password: str, sip_cfg: dict, name: str = "") -> str:
    """Generate SIP account 1 parameters for a fixed phone."""
    display_name = name if name else ext
    lines = []
    lines.append(xml_param("270", "1"))                              # Account 1 active
    lines.append(xml_param("47", sip_cfg["sip_server"]))             # SIP Server
    lines.append(xml_param("48", sip_cfg["sip_server"]))             # Outbound Proxy
    lines.append(xml_param("35", ext))                               # SIP User ID
    lines.append(xml_param("36", ext))                               # Auth ID
    lines.append(xml_param("34", password))                          # Auth password
    lines.append(xml_param("3", display_name))                       # Account Name / Display
    lines.append(xml_param("52", str(sip_cfg["sip_port"])))          # SIP Port
    lines.append(xml_param("2312", "1"))                             # Account enable
    lines.append(xml_param("2327", "0"))                             # SIP Transport: UDP
    lines.append(xml_param("2380", "1"))                             # Account ringtone
    return "".join(lines)


def generate_desk_params(desk_ext: str, password: str, sip_cfg: dict) -> str:
    """Generate desk extension parameters for CFU-based hot-desking.

    Each hot-desk phone gets a permanent desk extension. When an employee
    checks in via Flutter, their personal extension gets CFU (Call Forward
    Unconditional) set to this desk extension. Public Mode is OFF.
    """
    display_name = f"Desk {desk_ext[-2:]}"  # e.g. "Desk 01" for 2101
    lines = []
    lines.append(xml_param("270", "1"))                              # Account 1 active
    lines.append(xml_param("47", sip_cfg["sip_server"]))             # SIP Server
    lines.append(xml_param("48", sip_cfg["sip_server"]))             # Outbound Proxy
    lines.append(xml_param("35", desk_ext))                          # SIP User ID (desk ext)
    lines.append(xml_param("36", desk_ext))                          # Auth ID
    lines.append(xml_param("34", password))                          # Auth password
    lines.append(xml_param("3", display_name))                       # Display name
    lines.append(xml_param("52", str(sip_cfg["sip_port"])))          # SIP Port
    lines.append(xml_param("2312", "1"))                             # Account enable
    lines.append(xml_param("2327", "0"))                             # SIP Transport: UDP
    lines.append(xml_param("8468", "0"))                             # Public Mode OFF (CFU seating)
    lines.append(xml_param("2380", "1"))                             # Account ringtone
    return "".join(lines)


def generate_phone_xml(phone_type: str, cfg: dict, ext: str = "", password: str = "", name: str = "") -> str:
    """Generate complete provisioning XML for one phone."""
    xml = xml_header()
    xml += generate_common_params(cfg)

    if phone_type == "fixed":
        xml += generate_sip_params(ext, password, cfg["phone"], name=name)
    elif phone_type == "desk":
        xml += generate_desk_params(ext, password, cfg["phone"])
    else:
        raise ValueError(f"Unknown phone_type: {phone_type}")

    xml += xml_footer()
    return xml


# ---------------------------------------------------------------------------
# LDAP seed LDIF
# ---------------------------------------------------------------------------

def generate_ldif(cfg: dict, fixed_users: list[dict], free_users: list[dict]) -> str:
    """Generate LDAP seed LDIF for all users (deduplicated by extension)."""
    base_dn = cfg["phone"]["ldap"]["base_dn"]
    prefix = cfg["phone"]["sip_password_prefix"]
    lines = []

    # Org unit for phone users
    lines.append(f"dn: ou=users,{base_dn}")
    lines.append("objectClass: organizationalUnit")
    lines.append("ou: users")
    lines.append("")

    # Merge all users, fixed phones take priority over free users
    seen = set()

    # Fixed extension users first (SIP password = prefix + ext)
    for row in fixed_users:
        name = row["NAME"]
        ext = row["NUMBER"]
        seen.add(ext)
        dn = f"uid={ext},ou=users,{base_dn}"
        lines.append(f"dn: {dn}")
        lines.append("objectClass: inetOrgPerson")
        lines.append(f"uid: {ext}")
        lines.append(f"cn: {name}")
        lines.append(f"sn: {name}")
        lines.append(f"telephoneNumber: {ext}")
        lines.append(f"userPassword: {prefix}{ext}")
        lines.append("")

    # Free (roaming) users — skip duplicates already added from fixed
    for row in free_users:
        name = row["NAME"]
        ext = row["NUMBER"]
        if ext in seen:
            continue
        seen.add(ext)
        dn = f"uid={ext},ou=users,{base_dn}"
        lines.append(f"dn: {dn}")
        lines.append("objectClass: inetOrgPerson")
        lines.append(f"uid: {ext}")
        lines.append(f"cn: {name}")
        lines.append(f"sn: {name}")
        lines.append(f"telephoneNumber: {ext}")
        lines.append(f"userPassword: {prefix}{ext}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Legacy FreePBX extension creation script (superseded by confgen + faxapi /pbx/*)
# ---------------------------------------------------------------------------

def generate_extension_script(cfg: dict, free_users: list[dict]) -> str:
    """Generate shell script to create FreePBX PJSIP extensions 001-012."""
    phone = cfg["phone"]
    core_container = cfg["fax"]["docker"]["core_container"]
    password_prefix = phone["sip_password_prefix"]

    script = dedent(f"""\
        #!/usr/bin/env bash
        # create-extensions.sh — Create FreePBX PJSIP extensions for hot-desk users
        # Generated by services/phone-provisioning/generate.py — do not edit manually.
        #
        # Usage: sg docker -c "bash services/phone-provisioning/create-extensions.sh"

        set -euo pipefail

        CONTAINER="{core_container}"
        GREEN='\\033[0;32m'
        RED='\\033[0;31m'
        NC='\\033[0m'

        log() {{ echo -e "${{GREEN}}[OK]${{NC}} $*"; }}
        err() {{ echo -e "${{RED}}[ERR]${{NC}} $*" >&2; }}

        # Check container is running
        if ! docker inspect "$CONTAINER" &>/dev/null; then
            err "Container $CONTAINER not found"
            exit 1
        fi

    """)

    for row in free_users:
        ext = row["NUMBER"]
        name = row["NAME"]
        password = f"{password_prefix}{ext}"
        script += dedent(f"""\
            # Extension {ext} — {name}
            echo "Creating extension {ext} ({name})..."
            docker exec "$CONTAINER" bash -c '
                /var/lib/asterisk/bin/fwconsole ext --create \\
                    --ext="{ext}" \\
                    --name="{name}" \\
                    --tech="pjsip" \\
                    --secret="{password}" 2>/dev/null || echo "Extension {ext} may already exist"
            '
        """)

    script += dedent(f"""\

        # Reload FreePBX
        echo "Reloading FreePBX..."
        docker exec "$CONTAINER" /var/lib/asterisk/bin/fwconsole reload
        log "All extensions created and FreePBX reloaded"
    """)

    return script


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate phone provisioning files")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be generated without writing")
    args = parser.parse_args()

    # Find repo root (directory containing config.yaml)
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent
    if not (repo_root / "config.yaml").exists():
        print(f"ERROR: config.yaml not found at {repo_root}", file=sys.stderr)
        sys.exit(1)

    cfg = load_config(repo_root)
    phone = cfg["phone"]
    output_dir = repo_root / phone["output_dir"]
    output_dir.mkdir(parents=True, exist_ok=True)

    # Read CSVs
    fixed_phones = read_csv(repo_root / phone["csv_fixed"])
    free_phones = read_csv(repo_root / phone["csv_free_phones"])
    free_users = read_csv(repo_root / phone["csv_free_users"])

    # Read existing SIP passwords
    pjsip_path = repo_root / phone["pjsip_auth_conf"]
    passwords = read_pjsip_passwords(pjsip_path) if pjsip_path.exists() else {}

    print(f"Fixed phones: {len(fixed_phones)}")
    print(f"Free phones:  {len(free_phones)}")
    print(f"Free users:   {len(free_users)}")
    print(f"Known SIP passwords: {len(passwords)}")
    print()

    xml_count = 0
    symlink_count = 0

    # --- Generate fixed phone XMLs ---
    for row in fixed_phones:
        ext = row["NUMBER"]
        mac = row["MAC"]
        name = row["NAME"]

        # Get password from pjsip.auth.conf or use default pattern
        pw = passwords.get(ext, f"{phone['sip_password_prefix']}{ext}")

        xml = generate_phone_xml("fixed", cfg, ext=ext, password=pw, name=name)
        eth_mac = mac_normalize(mac)
        wifi_mac = mac_wifi(mac)

        eth_file = output_dir / f"cfg{eth_mac}.xml"
        wifi_file = output_dir / f"cfg{wifi_mac}.xml"

        if args.dry_run:
            print(f"  [DRY] {eth_file.name} — fixed {ext} ({name})")
            print(f"  [DRY] {wifi_file.name} → {eth_file.name} (symlink)")
        else:
            eth_file.write_text(xml)
            # Create symlink for WiFi MAC
            if wifi_file.exists() or wifi_file.is_symlink():
                wifi_file.unlink()
            wifi_file.symlink_to(eth_file.name)
            print(f"  {eth_file.name} — fixed {ext} ({name})")

        xml_count += 1
        symlink_count += 1

    # --- Generate desk phone XMLs (CFU-based hot-desking) ---
    for row in free_phones:
        mac = row["MAC"]
        desk_ext = row["DESK_EXT"]
        desk_pw = f"desk{desk_ext}"  # matches PBX DB password
        xml = generate_phone_xml("desk", cfg, ext=desk_ext, password=desk_pw)
        eth_mac = mac_normalize(mac)
        wifi_mac = mac_wifi(mac)

        eth_file = output_dir / f"cfg{eth_mac}.xml"
        wifi_file = output_dir / f"cfg{wifi_mac}.xml"

        if args.dry_run:
            print(f"  [DRY] {eth_file.name} — desk ext {desk_ext}")
            print(f"  [DRY] {wifi_file.name} → {eth_file.name} (symlink)")
        else:
            eth_file.write_text(xml)
            if wifi_file.exists() or wifi_file.is_symlink():
                wifi_file.unlink()
            wifi_file.symlink_to(eth_file.name)
            print(f"  {eth_file.name} — desk ext {desk_ext}")

        xml_count += 1
        symlink_count += 1

    print(f"\nGenerated {xml_count} XML files + {symlink_count} symlinks in {output_dir}/")

    # --- Generate LDAP seed ---
    ldif = generate_ldif(cfg, fixed_phones, free_users)
    ldif_path = script_dir / "ldap-seed.ldif"
    if args.dry_run:
        print(f"\n[DRY] Would write {ldif_path}")
    else:
        ldif_path.write_text(ldif)
        print(f"\nWrote {ldif_path}")

    # --- Generate extension creation script ---
    ext_script = generate_extension_script(cfg, free_users)
    ext_script_path = script_dir / "create-extensions.sh"
    if args.dry_run:
        print(f"[DRY] Would write {ext_script_path}")
    else:
        ext_script_path.write_text(ext_script)
        ext_script_path.chmod(0o755)
        print(f"Wrote {ext_script_path}")

    print("\nDone.")


if __name__ == "__main__":
    main()
