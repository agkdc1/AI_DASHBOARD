"""HashiCorp Vault client using AppRole authentication.

Generalized from rakuten_renewal/agent/vault_client.py for the Browser Daemon.
Reads AppRole credential paths and Vault address from environment variables
first, falling back to values in config.yaml.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import hvac

from . import config as cfg

log = logging.getLogger(__name__)


class VaultClient:
    """Thin wrapper around hvac for AppRole auth + KV v2 operations.

    Environment variables take precedence over config.yaml values:

    - ``VAULT_ADDR`` -- Vault server address
    - ``VAULT_APPROLE_ROLE_ID_PATH`` -- path to file containing the AppRole role-id
    - ``VAULT_APPROLE_SECRET_ID_PATH`` -- path to file containing the AppRole secret-id
    """

    def __init__(
        self,
        role_id_path: str | None = None,
        secret_id_path: str | None = None,
    ) -> None:
        # Vault address: env var > explicit arg context > config
        self._addr = os.environ.get("VAULT_ADDR") or cfg.vault_addr()

        # Role-ID path: explicit arg > env var > config
        self._role_id_path = (
            role_id_path
            or os.environ.get("VAULT_APPROLE_ROLE_ID_PATH")
            or cfg.cfg("vault.approle.daemon.role_id_path")
        )

        # Secret-ID path: explicit arg > env var > config
        self._secret_id_path = (
            secret_id_path
            or os.environ.get("VAULT_APPROLE_SECRET_ID_PATH")
            or cfg.cfg("vault.approle.daemon.secret_id_path")
        )

        self._client: hvac.Client | None = None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _login(self) -> hvac.Client:
        """Authenticate to Vault via AppRole, reusing an existing token if valid."""
        if self._client is not None and self._client.is_authenticated():
            return self._client

        role_id = Path(self._role_id_path).read_text().strip()
        secret_id = Path(self._secret_id_path).read_text().strip()

        client = hvac.Client(url=self._addr)
        client.auth.approle.login(role_id=role_id, secret_id=secret_id)
        log.info("Vault AppRole login successful (addr=%s)", self._addr)
        self._client = client
        return client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def read(self, path: str) -> dict[str, Any]:
        """Read a KV v2 secret.

        Args:
            path: Secret path relative to the ``secret/`` mount, e.g.
                  ``"daemon/yamato"`` or ``"rakuten/rms"``.

        Returns:
            The secret data dict.
        """
        client = self._login()
        resp = client.secrets.kv.v2.read_secret_version(
            path=path, mount_point="secret",
        )
        return resp["data"]["data"]

    def write(self, path: str, data: dict[str, Any]) -> None:
        """Write (create/update) a KV v2 secret.

        Args:
            path: Secret path relative to the ``secret/`` mount.
            data: Key-value pairs to store.
        """
        client = self._login()
        client.secrets.kv.v2.create_or_update_secret(
            path=path,
            secret=data,
            mount_point="secret",
        )
        log.info("Vault write: secret/%s", path)
