"""Send fallback notification emails via SendGrid."""

from __future__ import annotations

import logging
from typing import Any

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from . import config as cfg
from .vault_client import VaultClient

log = logging.getLogger(__name__)


def _get_sendgrid_client(vault: VaultClient) -> SendGridAPIClient:
    secrets = vault.read("rakuten/sendgrid")
    return SendGridAPIClient(api_key=secrets["api_key"])


def send_fallback_email(
    vault: VaultClient,
    error_description: str,
    session_id: str,
) -> None:
    """Send human-fallback email when all automated renewal attempts fail."""
    admin_email = cfg.cfg("rakuten.fallback.admin_email")
    sentinel_addr = cfg.cfg("rakuten.fallback.sentinel_address")
    log_dir = cfg.log_dir()

    body = f"""The automated Rakuten API key renewal agent failed after {cfg.cfg('rakuten.max_retries')} attempts.

Please:
1. Log into RMS manually and renew the API keys
2. Reply to: {sentinel_addr}
   with the new Service Secret and License Key

Last error: {error_description}
Logs: {log_dir}/{session_id}.jsonl
GCS: gs://{cfg.gcs_bucket()}/{cfg.gcs_prefix()}/sessions/{session_id}/
"""

    message = Mail(
        from_email=sentinel_addr,
        to_emails=admin_email,
        subject="[SHINBEE] Rakuten API Key Renewal Failed - Manual Action Required",
        plain_text_content=body,
    )

    try:
        sg = _get_sendgrid_client(vault)
        response = sg.send(message)
        log.info("Fallback email sent (status %s)", response.status_code)
    except Exception:
        log.exception("Failed to send fallback email")
        raise


def send_alert(
    vault: VaultClient,
    subject: str,
    body: str,
) -> None:
    """Send a generic alert email."""
    admin_email = cfg.cfg("rakuten.fallback.admin_email")
    sentinel_addr = cfg.cfg("rakuten.fallback.sentinel_address")

    message = Mail(
        from_email=sentinel_addr,
        to_emails=admin_email,
        subject=f"[SHINBEE] {subject}",
        plain_text_content=body,
    )

    try:
        sg = _get_sendgrid_client(vault)
        sg.send(message)
        log.info("Alert email sent: %s", subject)
    except Exception:
        log.exception("Failed to send alert email")
