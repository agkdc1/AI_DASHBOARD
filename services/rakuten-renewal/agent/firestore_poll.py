"""Poll Firestore for 2FA codes deposited by the Email Sentinel."""

from __future__ import annotations

import asyncio
import logging
import time

from google.cloud import firestore
from google.auth import identity_pool

from . import config as cfg

log = logging.getLogger(__name__)

_WIF_CRED = cfg.repo_root() / "Vault" / "pki" / "wif-credential-config.json"


def _client() -> firestore.Client:
    creds = identity_pool.Credentials.from_file(str(_WIF_CRED))
    scoped = creds.with_scopes(["https://www.googleapis.com/auth/datastore"])
    return firestore.Client(
        project=cfg.cfg("rakuten.sentinel.firestore_project"),
        credentials=scoped,
    )


async def poll_2fa_code(
    poll_interval: int | None = None,
    timeout: int | None = None,
) -> str | None:
    """Poll Firestore for a fresh 2FA code.  Returns the code or None on timeout."""
    interval = poll_interval or cfg.cfg("rakuten.sentinel.poll_interval_secs")
    max_wait = timeout or cfg.cfg("rakuten.sentinel.poll_timeout_secs")

    db = _client()
    doc_ref = db.collection("auth").document("rakuten").collection("data").document("current_2fa")

    start = time.monotonic()
    while time.monotonic() - start < max_wait:
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            if data and not data.get("consumed", True):
                code = data.get("code")
                # Mark as consumed
                doc_ref.update({"consumed": True, "consumed_at": firestore.SERVER_TIMESTAMP})
                log.info("2FA code retrieved (waited %.1fs)", time.monotonic() - start)
                return code

        await asyncio.sleep(interval)

    log.warning("2FA poll timed out after %ds", max_wait)
    return None


async def poll_manual_key(
    poll_interval: int = 30,
    timeout: int = 86400,
) -> dict[str, str] | None:
    """Poll for manually-submitted API keys (human fallback).

    Waits up to *timeout* seconds (default 24h).
    """
    db = _client()
    doc_ref = db.collection("auth").document("rakuten").collection("data").document("manual_key")

    start = time.monotonic()
    while time.monotonic() - start < timeout:
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            if data and not data.get("consumed", True):
                keys = {
                    "service_secret": data.get("service_secret", ""),
                    "license_key": data.get("license_key", ""),
                }
                doc_ref.update({"consumed": True, "consumed_at": firestore.SERVER_TIMESTAMP})
                log.info("Manual key retrieved from Firestore")
                return keys

        await asyncio.sleep(poll_interval)

    log.warning("Manual key poll timed out after %ds", timeout)
    return None
