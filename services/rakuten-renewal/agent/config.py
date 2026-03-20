"""Load configuration from the unified SHINBEE config.yaml."""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import yaml

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.yaml"
_cache: dict[str, Any] | None = None


def _load() -> dict[str, Any]:
    global _cache
    if _cache is None:
        with open(_CONFIG_PATH) as f:
            _cache = yaml.safe_load(f)
    return _cache


def cfg(dotpath: str) -> Any:
    """Retrieve a value by dot-separated path (e.g. 'rakuten.gemini.model')."""
    keys = dotpath.split(".")
    return functools.reduce(
        lambda d, k: d[int(k)] if isinstance(d, list) else d[k],
        keys,
        _load(),
    )


# --- Convenience accessors ---------------------------------------------------

def repo_root() -> Path:
    return Path(cfg("global.repo_root"))


def rakuten_root() -> Path:
    return repo_root() / "services" / "rakuten-renewal"


def log_dir() -> Path:
    return repo_root() / cfg("rakuten.logging.dir")


def prompts_dir() -> Path:
    return Path(__file__).resolve().parent / "prompts"


def state_file() -> Path:
    return rakuten_root() / "state.json"


def screenshots_dir() -> Path:
    return rakuten_root() / "screenshots"


# GCS
def gcs_bucket() -> str:
    return cfg("gcp.backup_bucket")


def gcs_prefix() -> str:
    return cfg("rakuten.logging.gcs_prefix")


# Vault
def vault_addr() -> str:
    return cfg("vault.address")


# Gemini
def gemini_model() -> str:
    return cfg("rakuten.gemini.model")


def captcha_model() -> str:
    return cfg("rakuten.gemini.captcha_model")


def flash_model() -> str:
    return cfg("rakuten.gemini.flash_model")
