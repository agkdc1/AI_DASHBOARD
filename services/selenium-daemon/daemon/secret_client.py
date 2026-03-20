"""GCP Secret Manager client — drop-in replacement for VaultClient.

Reads/writes JSON secrets from GCP Secret Manager instead of HashiCorp Vault.
Maintains the same ``read(path)`` / ``write(path, data)`` interface so
session and job code requires only an import change.

Path mapping: Vault's ``daemon/yamato`` becomes GCP SM secret ``daemon-yamato``.
The ``/`` → ``-`` conversion applies to all paths.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from google.cloud import secretmanager

from . import config as cfg

log = logging.getLogger(__name__)

_GCP_PROJECT = "your-gcp-project-id"


def _vault_path_to_sm_id(path: str) -> str:
    """Convert a Vault-style path to a GCP SM secret ID.

    Examples:
        ``daemon/yamato``  → ``daemon-yamato``
        ``rakuten/api_keys`` → ``rakuten-api-keys``
        ``rakuten/rms`` → ``rakuten-rms``
    """
    return path.replace("/", "-").replace("_", "-")


class SecretClient:
    """GCP Secret Manager client with VaultClient-compatible interface."""

    def __init__(self) -> None:
        import google.auth
        from google.auth.transport import requests as auth_requests

        _SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]
        credentials, project = google.auth.default(scopes=_SCOPES)

        # WIF X.509 credentials require explicit scoping; refresh to verify
        if hasattr(credentials, "with_scopes"):
            credentials = credentials.with_scopes(_SCOPES)
        credentials.refresh(auth_requests.Request())

        self._client = secretmanager.SecretManagerServiceClient(
            credentials=credentials
        )
        self._project = os.environ.get("GCP_PROJECT", _GCP_PROJECT)
        log.info("SecretClient initialized (project=%s)", self._project)

    def read(self, path: str) -> dict[str, Any]:
        """Read a secret (same interface as VaultClient.read).

        Args:
            path: Vault-style path, e.g. ``"daemon/yamato"``.

        Returns:
            The secret data dict (parsed from JSON).
        """
        secret_id = _vault_path_to_sm_id(path)
        name = f"projects/{self._project}/secrets/{secret_id}/versions/latest"

        try:
            response = self._client.access_secret_version(
                request={"name": name}
            )
            payload = response.payload.data.decode("utf-8")
            data = json.loads(payload)
            log.debug("Read secret '%s' from GCP SM (%d keys)", secret_id, len(data))
            return data
        except Exception as exc:
            log.error("Failed to read secret '%s' from GCP SM: %s", secret_id, exc)
            raise

    def write(self, path: str, data: dict[str, Any]) -> None:
        """Write (create new version of) a secret.

        Args:
            path: Vault-style path, e.g. ``"rakuten/api_keys"``.
            data: Key-value pairs to store as JSON.
        """
        secret_id = _vault_path_to_sm_id(path)
        parent = f"projects/{self._project}/secrets/{secret_id}"
        payload = json.dumps(data).encode("utf-8")

        try:
            # Try to add a version (secret must already exist)
            self._client.add_secret_version(
                request={"parent": parent, "payload": {"data": payload}}
            )
            log.info("Wrote secret '%s' to GCP SM", secret_id)
        except Exception:
            # Secret may not exist yet — create it first
            try:
                self._client.create_secret(
                    request={
                        "parent": f"projects/{self._project}",
                        "secret_id": secret_id,
                        "secret": {"replication": {"automatic": {}}},
                    }
                )
                self._client.add_secret_version(
                    request={"parent": parent, "payload": {"data": payload}}
                )
                log.info("Created and wrote secret '%s' to GCP SM", secret_id)
            except Exception as exc:
                log.error("Failed to write secret '%s' to GCP SM: %s", secret_id, exc)
                raise
