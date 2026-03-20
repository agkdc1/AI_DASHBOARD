"""SQLite database setup for IAM."""

import logging

import aiosqlite

from config import settings

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS staff (
    email TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    photo_url TEXT,
    role TEXT NOT NULL DEFAULT 'staff',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS deny_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL REFERENCES staff(email) ON DELETE CASCADE,
    permission TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(email, permission)
);
"""


async def get_db() -> aiosqlite.Connection:
    """Open a connection to the IAM database."""
    db = await aiosqlite.connect(settings.iam_db_path)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_db() -> None:
    """Create tables and seed the superuser."""
    db = await get_db()
    try:
        await db.executescript(_SCHEMA)

        # Auto-seed superuser if not present
        row = await db.execute_fetchall(
            "SELECT email FROM staff WHERE email = ?",
            (settings.superuser_email,),
        )
        if not row:
            await db.execute(
                "INSERT INTO staff (email, display_name, role) VALUES (?, ?, ?)",
                (settings.superuser_email, "Administrator", "superuser"),
            )
            await db.commit()
            log.info("Seeded superuser: %s", settings.superuser_email)
        else:
            log.info("IAM database ready (%s already exists)", settings.superuser_email)
    finally:
        await db.close()
