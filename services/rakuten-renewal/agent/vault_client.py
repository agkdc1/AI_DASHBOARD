"""HashiCorp Vault client using AppRole authentication."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import hvac

from . import config as cfg

log = logging.getLogger(__name__)


class VaultClient:
    """Thin wrapper around hvac for AppRole auth + KV v2 operations."""

    def __init__(
        self,
        role_id_path: str | None = None,
        secret_id_path: str | None = None,
    ) -> None:
        self._addr = cfg.vault_addr()
        self._role_id_path = role_id_path or cfg.cfg("vault.approle.rakuten.role_id_path")
        self._secret_id_path = secret_id_path or cfg.cfg("vault.approle.rakuten.secret_id_path")
        self._client: hvac.Client | None = None

    def _login(self) -> hvac.Client:
        if self._client is not None and self._client.is_authenticated():
            return self._client

        role_id = Path(self._role_id_path).read_text().strip()
        secret_id = Path(self._secret_id_path).read_text().strip()

        client = hvac.Client(url=self._addr)
        client.auth.approle.login(role_id=role_id, secret_id=secret_id)
        log.info("Vault AppRole login successful")
        self._client = client
        return client

    def read(self, path: str) -> dict[str, Any]:
        """Read a KV v2 secret.  *path* should be like 'rakuten/rms'."""
        client = self._login()
        resp = client.secrets.kv.v2.read_secret_version(path=path, mount_point="secret")
        return resp["data"]["data"]

    def write(self, path: str, data: dict[str, Any]) -> None:
        """Write (create/update) a KV v2 secret."""
        client = self._login()
        client.secrets.kv.v2.create_or_update_secret(
            path=path,
            secret=data,
            mount_point="secret",
        )
        log.info("Vault write: secret/%s", path)
