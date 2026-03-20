#!/usr/bin/env python3
"""Migrate FreePBX configuration to SQLite for headless Asterisk.

Reads data from two sources:
  1. FreePBX MariaDB (via container) — extensions, ring groups, routes, etc.
  2. Existing Asterisk config files — PJSIP auth passwords, callerIDs

Outputs: services/fax/data/pbx.db (SQLite)

Usage:
    # From repo root on Pi (needs Docker access for MariaDB queries):
    python3 services/fax/scripts/migrate_freepbx_to_sqlite.py

    # Or use --from-files to skip MariaDB and extract from config files only:
    python3 services/fax/scripts/migrate_freepbx_to_sqlite.py --from-files
"""

import argparse
import os
import re
import sqlite3
import sys
from pathlib import Path

# Resolve paths relative to repo root
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ASTERISK_ETC = REPO_ROOT / "services" / "fax" / "data" / "asterisk-etc"
DB_PATH = REPO_ROOT / "services" / "fax" / "data" / "pbx.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS extensions (
    ext TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    password TEXT NOT NULL,
    context TEXT DEFAULT 'from-internal',
    mailbox INTEGER DEFAULT 1,
    recording INTEGER DEFAULT 1,
    call_group TEXT DEFAULT '1',
    pickup_group TEXT DEFAULT '1',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ring_groups (
    id INTEGER PRIMARY KEY,
    number TEXT UNIQUE NOT NULL,
    strategy TEXT DEFAULT 'ringall',
    timeout INTEGER DEFAULT 60,
    destination TEXT DEFAULT 'hangup',
    description TEXT
);

CREATE TABLE IF NOT EXISTS ring_group_members (
    group_id INTEGER REFERENCES ring_groups(id),
    ext TEXT REFERENCES extensions(ext),
    PRIMARY KEY (group_id, ext)
);

CREATE TABLE IF NOT EXISTS outbound_routes (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    pattern TEXT NOT NULL,
    trunk TEXT DEFAULT 'ntt-trunk',
    priority INTEGER DEFAULT 1,
    action TEXT DEFAULT 'ALLOW'
);

CREATE TABLE IF NOT EXISTS inbound_routes (
    id INTEGER PRIMARY KEY,
    did TEXT NOT NULL,
    destination TEXT NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS day_night_modes (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    day_destination TEXT NOT NULL,
    night_destination TEXT NOT NULL,
    password TEXT DEFAULT '5304',
    current_state TEXT DEFAULT 'day'
);

CREATE TABLE IF NOT EXISTS feature_codes (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    enabled INTEGER DEFAULT 1,
    context TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ivr_menus (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    timeout INTEGER DEFAULT 10,
    timeout_destination TEXT,
    invalid_destination TEXT,
    audio_file TEXT
);

CREATE TABLE IF NOT EXISTS ivr_entries (
    ivr_id INTEGER REFERENCES ivr_menus(id),
    digit TEXT NOT NULL,
    destination TEXT NOT NULL,
    PRIMARY KEY (ivr_id, digit)
);

CREATE TABLE IF NOT EXISTS blacklist (
    number TEXT PRIMARY KEY,
    description TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
"""


def parse_pjsip_auth(conf_path: Path) -> dict[str, str]:
    """Parse pjsip.auth.conf → {ext: password}."""
    passwords = {}
    current_ext = None
    for line in conf_path.read_text().splitlines():
        line = line.strip()
        m = re.match(r"^\[(\d+)-auth\]$", line)
        if m:
            current_ext = m.group(1)
            continue
        if current_ext and line.startswith("password="):
            passwords[current_ext] = line.split("=", 1)[1]
            current_ext = None
    return passwords


def parse_pjsip_endpoints(conf_path: Path) -> dict[str, str]:
    """Parse pjsip.endpoint.conf → {ext: display_name from callerid}."""
    names = {}
    current_ext = None
    for line in conf_path.read_text().splitlines():
        line = line.strip()
        # Match [NNN] but not [NNN-auth], [NNN-aor], [anonymous], [0]
        m = re.match(r"^\[(\d{2,})\]$", line)
        if m:
            current_ext = m.group(1)
            continue
        if current_ext and line.startswith("callerid="):
            # Format: callerid=NAME <EXT>
            cid = line.split("=", 1)[1]
            name_match = re.match(r"(.+?)\s*<\d+>", cid)
            if name_match:
                names[current_ext] = name_match.group(1).strip()
            else:
                names[current_ext] = current_ext
            current_ext = None
    return names


def extract_from_files() -> dict:
    """Extract all PBX config from existing Asterisk config files."""
    data = {
        "extensions": [],
        "ring_groups": [],
        "ring_group_members": [],
        "outbound_routes": [],
        "inbound_routes": [],
        "day_night_modes": [],
        "feature_codes": [],
        "ivr_menus": [],
        "ivr_entries": [],
    }

    # --- Extensions from auth + endpoint configs ---
    passwords = parse_pjsip_auth(ASTERISK_ETC / "pjsip.auth.conf")
    names = parse_pjsip_endpoints(ASTERISK_ETC / "pjsip.endpoint.conf")

    for ext in sorted(passwords.keys(), key=lambda x: x.zfill(4)):
        name = names.get(ext, ext)
        pw = passwords[ext]
        data["extensions"].append({
            "ext": ext,
            "name": name,
            "password": pw,
            "context": "from-internal",
            "mailbox": 1,
            "recording": 1,
            "call_group": "1",
            "pickup_group": "1",
        })

    # --- Ring group 200 (desk phones — excludes floor phones, fax, system) ---
    # Excluded: 101=1F floor, 230=director ext, 401=4F, 501=5F,
    # 601/602=fax, 701/702=7F IP, 801/802=system
    rg200_exclude = {"101", "230", "401", "501", "601", "602", "701", "702", "801", "802"}
    all_exts = sorted(passwords.keys(), key=lambda x: x.zfill(4))
    data["ring_groups"].append({
        "id": 1,
        "number": "200",
        "strategy": "ringall",
        "timeout": 60,
        "destination": "hangup",
        "description": "All desk extensions ring group",
    })
    for ext in all_exts:
        if ext not in rg200_exclude:
            data["ring_group_members"].append({"group_id": 1, "ext": ext})

    # --- Outbound routes (from plan audit) ---
    data["outbound_routes"] = [
        {"id": 1, "name": "Hikari1", "pattern": "_90[1-9]XXXXXXXX", "trunk": "ntt-trunk", "priority": 1, "action": "ALLOW"},
        {"id": 2, "name": "Hikari1_120", "pattern": "_90120XXXXXX", "trunk": "ntt-trunk", "priority": 2, "action": "ALLOW"},
        {"id": 3, "name": "Hikari1_0800", "pattern": "_90800XXXXXXX", "trunk": "ntt-trunk", "priority": 3, "action": "ALLOW"},
        {"id": 4, "name": "High_Risk", "pattern": "_900[1-9]X.", "trunk": "ntt-trunk", "priority": 4, "action": "ALLOW"},
        {"id": 5, "name": "High_Risk_Intl", "pattern": "_9010X.", "trunk": "ntt-trunk", "priority": 5, "action": "ALLOW"},
        {"id": 6, "name": "BLOCK_0180", "pattern": "_90180X.", "trunk": "BLOCK", "priority": 6, "action": "BLOCK"},
        {"id": 7, "name": "BLOCK_0990", "pattern": "_90990X.", "trunk": "BLOCK", "priority": 7, "action": "BLOCK"},
    ]

    # --- Inbound DID routes ---
    data["inbound_routes"] = [
        {"id": 1, "did": "default", "destination": "daynight-0", "description": "Main number → day/night routing"},
        {"id": 2, "did": "0312345679", "destination": "fax", "description": "Fax line → fax-iax"},
        {"id": 3, "did": "_036424530[0123578]", "destination": "daynight-0", "description": "Additional DIDs → day/night"},
        {"id": 4, "did": "0364245358", "destination": "daynight-0", "description": "Additional DID → day/night"},
    ]

    # --- Day/night modes ---
    data["day_night_modes"] = [
        {"id": 0, "name": "基本営業時間", "day_destination": "ivr-1", "night_destination": "daynight-1", "password": "5304", "current_state": "day"},
        {"id": 1, "name": "休み１", "day_destination": "announcement-1", "night_destination": "announcement-1", "password": "5304", "current_state": "day"},
        {"id": 2, "name": "直通", "day_destination": "ringgroup-200", "night_destination": "daynight-1", "password": "5304", "current_state": "day"},
    ]

    # --- Feature codes ---
    data["feature_codes"] = [
        {"code": "*72", "name": "Call Forward Enable", "enabled": 1, "context": "app-cf-on"},
        {"code": "*73", "name": "Call Forward Disable", "enabled": 1, "context": "app-cf-off"},
        {"code": "*90", "name": "Call Forward Busy Enable", "enabled": 1, "context": "app-cf-busy-on"},
        {"code": "*91", "name": "Call Forward Busy Disable", "enabled": 1, "context": "app-cf-busy-off"},
        {"code": "*52", "name": "Call Forward No Answer Enable", "enabled": 1, "context": "app-cf-noanswer-on"},
        {"code": "*53", "name": "Call Forward No Answer Disable", "enabled": 1, "context": "app-cf-noanswer-off"},
        {"code": "*30", "name": "Blacklist Add", "enabled": 1, "context": "app-blacklist-add"},
        {"code": "*31", "name": "Blacklist Remove", "enabled": 1, "context": "app-blacklist-remove"},
        {"code": "*32", "name": "Blacklist Last Caller", "enabled": 1, "context": "app-blacklist-last"},
        {"code": "*1", "name": "One-Touch Recording", "enabled": 1, "context": "app-recording-toggle"},
        {"code": "*8", "name": "Group Pickup", "enabled": 1, "context": "app-pickup"},
        {"code": "**", "name": "Directed Pickup", "enabled": 1, "context": "app-directed-pickup"},
        {"code": "*70", "name": "Call Waiting Enable", "enabled": 1, "context": "app-cw-on"},
        {"code": "*71", "name": "Call Waiting Disable", "enabled": 1, "context": "app-cw-off"},
        {"code": "##", "name": "In-Call Transfer (Blind)", "enabled": 1, "context": "app-transfer-blind"},
        {"code": "*2", "name": "In-Call Transfer (Attended)", "enabled": 1, "context": "app-transfer-attended"},
        {"code": "*280", "name": "Day/Night Toggle 0", "enabled": 1, "context": "app-daynight-toggle"},
        {"code": "*281", "name": "Day/Night Toggle 1", "enabled": 1, "context": "app-daynight-toggle"},
        {"code": "*282", "name": "Day/Night Toggle 2", "enabled": 1, "context": "app-daynight-toggle"},
        {"code": "*98", "name": "Voicemail Login", "enabled": 1, "context": "app-vmail-login"},
        {"code": "*97", "name": "Voicemail Direct", "enabled": 1, "context": "app-vmail-direct"},
    ]

    # --- IVR menus ---
    data["ivr_menus"] = [
        {"id": 1, "name": "Default", "description": "Main IVR", "timeout": 10, "timeout_destination": "ringgroup-200", "invalid_destination": "ringgroup-200", "audio_file": "custom/intro"},
        {"id": 2, "name": "NoAnswerToAll", "description": "Fallback IVR when no one answers", "timeout": 10, "timeout_destination": "hangup", "invalid_destination": "hangup", "audio_file": "custom/3821759e07902fa02d2aec2bcb10984f"},
    ]
    data["ivr_entries"] = [
        {"ivr_id": 1, "digit": "1", "destination": "ringgroup-200"},
        {"ivr_id": 1, "digit": "2", "destination": "ringgroup-200"},
        {"ivr_id": 2, "digit": "1", "destination": "ringgroup-200"},
        {"ivr_id": 2, "digit": "2", "destination": "ringgroup-200"},
    ]

    return data


def create_db(data: dict, db_path: Path) -> None:
    """Create and populate the SQLite database."""
    if db_path.exists():
        backup = db_path.with_suffix(".db.bak")
        db_path.rename(backup)
        print(f"Backed up existing DB to {backup}")

    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)

    # Extensions
    conn.executemany(
        "INSERT INTO extensions (ext, name, password, context, mailbox, recording, call_group, pickup_group) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [(e["ext"], e["name"], e["password"], e["context"], e["mailbox"], e["recording"],
          e.get("call_group", "1"), e.get("pickup_group", "1")) for e in data["extensions"]],
    )
    print(f"  Extensions: {len(data['extensions'])}")

    # Ring groups
    for rg in data["ring_groups"]:
        conn.execute(
            "INSERT INTO ring_groups (id, number, strategy, timeout, destination, description) VALUES (?, ?, ?, ?, ?, ?)",
            (rg["id"], rg["number"], rg["strategy"], rg["timeout"], rg["destination"], rg["description"]),
        )
    print(f"  Ring groups: {len(data['ring_groups'])}")

    # Ring group members
    conn.executemany(
        "INSERT INTO ring_group_members (group_id, ext) VALUES (?, ?)",
        [(m["group_id"], m["ext"]) for m in data["ring_group_members"]],
    )
    print(f"  Ring group members: {len(data['ring_group_members'])}")

    # Outbound routes
    conn.executemany(
        "INSERT INTO outbound_routes (id, name, pattern, trunk, priority, action) VALUES (?, ?, ?, ?, ?, ?)",
        [(r["id"], r["name"], r["pattern"], r["trunk"], r["priority"], r["action"]) for r in data["outbound_routes"]],
    )
    print(f"  Outbound routes: {len(data['outbound_routes'])}")

    # Inbound routes
    conn.executemany(
        "INSERT INTO inbound_routes (id, did, destination, description) VALUES (?, ?, ?, ?)",
        [(r["id"], r["did"], r["destination"], r["description"]) for r in data["inbound_routes"]],
    )
    print(f"  Inbound routes: {len(data['inbound_routes'])}")

    # Day/night modes
    conn.executemany(
        "INSERT INTO day_night_modes (id, name, day_destination, night_destination, password, current_state) VALUES (?, ?, ?, ?, ?, ?)",
        [(m["id"], m["name"], m["day_destination"], m["night_destination"], m["password"], m["current_state"]) for m in data["day_night_modes"]],
    )
    print(f"  Day/night modes: {len(data['day_night_modes'])}")

    # Feature codes
    conn.executemany(
        "INSERT INTO feature_codes (code, name, enabled, context) VALUES (?, ?, ?, ?)",
        [(f["code"], f["name"], f["enabled"], f["context"]) for f in data["feature_codes"]],
    )
    print(f"  Feature codes: {len(data['feature_codes'])}")

    # IVR menus
    conn.executemany(
        "INSERT INTO ivr_menus (id, name, description, timeout, timeout_destination, invalid_destination, audio_file) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(m["id"], m["name"], m["description"], m["timeout"], m["timeout_destination"], m["invalid_destination"], m.get("audio_file")) for m in data["ivr_menus"]],
    )
    print(f"  IVR menus: {len(data['ivr_menus'])}")

    # IVR entries
    conn.executemany(
        "INSERT INTO ivr_entries (ivr_id, digit, destination) VALUES (?, ?, ?)",
        [(e["ivr_id"], e["digit"], e["destination"]) for e in data["ivr_entries"]],
    )
    print(f"  IVR entries: {len(data['ivr_entries'])}")

    conn.commit()
    conn.close()


def verify_db(db_path: Path) -> None:
    """Print verification counts."""
    conn = sqlite3.connect(str(db_path))
    print("\nVerification:")
    for table in ["extensions", "ring_groups", "ring_group_members", "outbound_routes",
                   "inbound_routes", "day_night_modes", "feature_codes", "ivr_menus", "ivr_entries"]:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {count}")

    # Show extension sample
    print("\nExtension samples:")
    for row in conn.execute("SELECT ext, name, password FROM extensions ORDER BY ext LIMIT 10"):
        print(f"  {row[0]}: {row[1]} (pw: {row[2]})")
    print("  ...")
    for row in conn.execute("SELECT ext, name, password FROM extensions ORDER BY ext DESC LIMIT 5"):
        print(f"  {row[0]}: {row[1]} (pw: {row[2]})")

    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Migrate FreePBX config to SQLite")
    parser.add_argument("--from-files", action="store_true", help="Extract from config files only (skip MariaDB)")
    parser.add_argument("--db-path", type=Path, default=DB_PATH, help="Output SQLite path")
    args = parser.parse_args()

    print(f"Extracting PBX config from Asterisk config files...")
    print(f"  Source: {ASTERISK_ETC}")
    data = extract_from_files()

    print(f"\nCreating SQLite DB: {args.db_path}")
    create_db(data, args.db_path)
    verify_db(args.db_path)
    print(f"\nDone. DB written to {args.db_path}")


if __name__ == "__main__":
    main()
