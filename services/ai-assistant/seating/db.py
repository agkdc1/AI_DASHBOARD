"""SQLite database setup for seating / hot-desking."""

import logging
from pathlib import Path

import aiosqlite

from config import settings

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS offices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    address TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS floors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    office_id INTEGER NOT NULL REFERENCES offices(id) ON DELETE CASCADE,
    floor_number INTEGER NOT NULL,
    name TEXT,
    floorplan_image TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(office_id, floor_number)
);

CREATE TABLE IF NOT EXISTS rooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    floor_id INTEGER NOT NULL REFERENCES floors(id) ON DELETE CASCADE,
    room_number INTEGER NOT NULL,
    name TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(floor_id, room_number)
);

CREATE TABLE IF NOT EXISTS desks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    desk_number INTEGER NOT NULL,
    desk_extension TEXT UNIQUE,
    phone_mac TEXT,
    phone_model TEXT DEFAULT 'GXP1760W',
    phone_ip TEXT,
    desk_type TEXT DEFAULT 'open' CHECK(desk_type IN ('open', 'designated')),
    designated_email TEXT,
    pos_x REAL,
    pos_y REAL,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(room_id, desk_number)
);

CREATE TABLE IF NOT EXISTS seat_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    desk_id INTEGER NOT NULL REFERENCES desks(id) ON DELETE CASCADE,
    employee_email TEXT NOT NULL,
    employee_name TEXT NOT NULL,
    employee_extension TEXT NOT NULL,
    checked_in_at TEXT DEFAULT (datetime('now')),
    checked_out_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_seat_assignments_active
    ON seat_assignments(desk_id) WHERE checked_out_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_seat_assignments_email
    ON seat_assignments(employee_email) WHERE checked_out_at IS NULL;
"""


async def get_db() -> aiosqlite.Connection:
    """Open a connection to the seating database."""
    db = await aiosqlite.connect(settings.seating_db_path)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_db() -> None:
    """Create seating tables and ensure floorplan directory exists."""
    db = await get_db()
    try:
        await db.executescript(_SCHEMA)
        log.info("Seating database ready at %s", settings.seating_db_path)
    finally:
        await db.close()

    Path(settings.floorplan_dir).mkdir(parents=True, exist_ok=True)
    log.info("Floorplan directory ready at %s", settings.floorplan_dir)
