"""Rakuten API key renewal job executor.

Navigates the Rakuten RMS API key management page, clicks the renewal
button, extracts the new keys via Gemini vision, writes them to Vault,
and optionally pushes updated settings to InvenTree via its REST API.

This consolidates the renewal logic previously in
``rakuten_renewal/agent/main.py`` (renew_mode).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import aiohttp

from .base import Job, JobStatus

if TYPE_CHECKING:
    from ..sessions.rakuten import RakutenSession
    from ..secret_client import SecretClient
    from ..vision.captcha import extract_keys

log = logging.getLogger(__name__)

# Secret paths (Vault-style, SecretClient converts to GCP SM IDs)
_API_KEYS_PATH = "rakuten/api_keys"
_INVENTREE_PATH = "daemon/inventree"

# InvenTree plugin settings endpoints
_INVENTREE_SETTING_PATTERN = "/api/plugins/settings/ecommerce/{key}/"


async def _update_inventree_settings(
    base_url: str,
    api_token: str,
    service_secret: str,
    license_key: str,
) -> bool:
    """Push renewed API keys to InvenTree plugin settings via REST API.

    Updates ``RAKUTEN_SERVICE_SECRET`` and ``RAKUTEN_LICENSE_KEY`` in the
    EcommerceIntegration plugin settings.

    Args:
        base_url: InvenTree server base URL (e.g. ``http://127.0.0.1:8000``).
        api_token: InvenTree API token with plugin settings write access.
        service_secret: The renewed Rakuten service secret.
        license_key: The renewed Rakuten license key.

    Returns:
        ``True`` if both settings were updated successfully.
    """
    headers = {
        "Authorization": f"Token {api_token}",
        "Content-Type": "application/json",
    }

    settings_to_update = {
        "RAKUTEN_SERVICE_SECRET": service_secret,
        "RAKUTEN_LICENSE_KEY": license_key,
    }

    try:
        async with aiohttp.ClientSession() as http:
            for key, value in settings_to_update.items():
                url = f"{base_url.rstrip('/')}{_INVENTREE_SETTING_PATTERN.format(key=key)}"
                async with http.patch(
                    url,
                    json={"value": value},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status not in (200, 201):
                        body = await resp.text()
                        log.error(
                            "Failed to update InvenTree setting %s: %s %s",
                            key, resp.status, body,
                        )
                        return False
                    log.info("Updated InvenTree setting: %s", key)

        return True

    except aiohttp.ClientError as exc:
        log.error("InvenTree API request failed: %s", exc)
        return False


async def execute(job: Job, session: RakutenSession, secrets: SecretClient) -> None:
    """Execute the Rakuten API key renewal job.

    Lifecycle:

    1. Ensure the Rakuten persistent session is logged in.
       If login fails, park the job as ``PENDING_USER_LOGIN``.
    2. Navigate to the API key management page.
    3. Locate and click the renewal button, confirm the dialog.
    4. Extract renewed keys from the page via Gemini vision
       (``captcha.extract_keys``).
    5. Write the new keys to GCP Secret Manager.
    6. Optionally update InvenTree EcommerceIntegration plugin settings
       via its REST API.
    7. Complete the job with renewal timestamp and InvenTree update status.

    Args:
        job: The renewal job instance.
        session: An authenticated ``RakutenSession`` (persistent).
        secrets: GCP Secret Manager client for reading/writing secrets.
    """
    job.status = JobStatus.RUNNING

    try:
        # Step 1: ensure logged in
        try:
            logged_in = await session.ensure_logged_in()
        except Exception as exc:
            log.warning("Rakuten login failed for renewal job %s: %s", job.job_id, exc)
            logged_in = False

        if not logged_in:
            log.warning(
                "Automated login failed -- parking renewal job %s as PENDING_USER_LOGIN",
                job.job_id,
            )
            job.set_pending_user_login()
            return

        # Step 2: navigate to API key page
        log.info("[rakuten] Navigating to API key management page for job %s", job.job_id)
        api_key_url = session.config.get("api_key_url", "https://navi-manual.rms.rakuten.co.jp/auth-api")
        await session.browser_session.navigate(api_key_url)
        await asyncio.sleep(2.0)

        # Step 3: take screenshot and find renewal button
        screenshot_path = await session.browser_session.screenshot("renewal_page")

        # Use the session's find_element for adaptive selector lookup
        renew_button = await session.find_element("renewal.renew_button")
        if renew_button is None:
            job.fail("Could not find renewal button on API key page")
            return

        # Click the renewal button
        log.info("[rakuten] Clicking renewal button")
        await renew_button.click()
        await asyncio.sleep(1.5)

        # Step 4: handle confirmation dialog
        confirm_button = await session.find_element("renewal.confirm_button")
        if confirm_button is not None:
            log.info("[rakuten] Confirming renewal dialog")
            await confirm_button.click()
            await asyncio.sleep(3.0)

        # Step 5: extract renewed keys via vision
        screenshot_path = await session.browser_session.screenshot("renewal_result")
        log.info("[rakuten] Extracting renewed keys via Gemini vision")

        # Import here to avoid circular imports at module level
        from ..vision.captcha import extract_keys as _extract_keys

        keys = await _extract_keys(screenshot_path)
        if not keys or "service_secret" not in keys or "license_key" not in keys:
            job.fail("Failed to extract renewed API keys from page")
            return

        service_secret = keys["service_secret"]
        license_key = keys["license_key"]
        log.info("[rakuten] Successfully extracted renewed keys")

        # Step 6: write to GCP SM
        secrets.write(_API_KEYS_PATH, {
            "service_secret": service_secret,
            "license_key": license_key,
            "renewed_at": datetime.now(timezone.utc).isoformat(),
        })
        log.info("[rakuten] Renewed keys written to GCP SM at %s", _API_KEYS_PATH)

        # Step 7: optionally update InvenTree plugin settings
        inventree_updated = False
        try:
            inventree_creds = secrets.read(_INVENTREE_PATH)
            inventree_base_url = inventree_creds.get("base_url", "")
            inventree_api_token = inventree_creds.get("api_token", "")

            if inventree_base_url and inventree_api_token:
                inventree_updated = await _update_inventree_settings(
                    base_url=inventree_base_url,
                    api_token=inventree_api_token,
                    service_secret=service_secret,
                    license_key=license_key,
                )
                if inventree_updated:
                    log.info("[rakuten] InvenTree plugin settings updated successfully")
                else:
                    log.warning("[rakuten] InvenTree plugin settings update failed (non-fatal)")
            else:
                log.info("[rakuten] InvenTree credentials not configured -- skipping plugin update")

        except Exception as exc:
            log.warning(
                "[rakuten] Could not update InvenTree (non-fatal): %s", exc
            )

        # Step 8: complete
        renewed_at = datetime.now(timezone.utc).isoformat()
        job.complete({
            "renewed_at": renewed_at,
            "inventree_updated": inventree_updated,
            "secret_path": _API_KEYS_PATH,
        })
        log.info(
            "[rakuten] Renewal job %s completed (inventree_updated=%s)",
            job.job_id, inventree_updated,
        )

    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"
        log.exception("[rakuten] Renewal job %s failed: %s", job.job_id, error_msg)
        job.fail(error_msg)
