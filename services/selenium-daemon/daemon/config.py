"""Load configuration from the unified SHINBEE config.yaml.

Generalized from rakuten_renewal/agent/config.py for the Browser Daemon.
Reads from the ``daemon.*`` config section and supports hot-reload.
"""

from __future__ import annotations

import functools
import os
from pathlib import Path
from typing import Any

import yaml

_CONFIG_PATH: Path = Path(os.environ.get("CONFIG_PATH", "/app/config.yaml"))
_cache: dict[str, Any] | None = None


def _load() -> dict[str, Any]:
    """Load and cache the YAML config file."""
    global _cache
    if _cache is None:
        with open(_CONFIG_PATH) as f:
            _cache = yaml.safe_load(f)
    return _cache


def reload() -> dict[str, Any]:
    """Force-reload the configuration from disk.

    Useful when external processes (e.g. meta-optimizer) update prompt files
    or when the config file is changed at runtime.
    """
    global _cache
    _cache = None
    return _load()


def cfg(dotpath: str) -> Any:
    """Retrieve a value by dot-separated path.

    Examples::

        cfg("daemon.browser.headless")     # True
        cfg("vault.address")               # "http://127.0.0.1:8200"
        cfg("daemon.gemini.model")         # "gemini-2.0-flash"
    """
    keys = dotpath.split(".")
    return functools.reduce(
        lambda d, k: d[int(k)] if isinstance(d, list) else d[k],
        keys,
        _load(),
    )


# ---------------------------------------------------------------------------
# Convenience accessors
# ---------------------------------------------------------------------------

def repo_root() -> Path:
    """Absolute path to the SHINBEE repository root."""
    return Path(cfg("global.repo_root"))


def daemon_root() -> Path:
    """Absolute path to the ``services/selenium-daemon/`` directory."""
    return repo_root() / "services" / "selenium-daemon"


def log_dir() -> Path:
    """Directory for structured JSONL session logs."""
    return repo_root() / cfg("daemon.logging.dir")


def prompts_dir() -> Path:
    """Directory containing Gemini prompt templates."""
    return Path(__file__).resolve().parent / "prompts"


def state_file() -> Path:
    """Path to the persistent state JSON (scheduling, session state)."""
    return daemon_root() / "state.json"


def screenshots_dir() -> Path:
    """Directory for debug screenshots."""
    return daemon_root() / "screenshots"


def pdf_dir() -> Path:
    """Root directory for downloaded waybill PDFs."""
    return repo_root() / cfg("daemon.download.pdf_dir")


def cookie_dir() -> Path:
    """Directory for disk-persisted session cookie jars."""
    return repo_root() / cfg("daemon.cookie_store.dir")


def selectors_dir() -> Path:
    """Directory containing per-carrier YAML selector files."""
    return Path(__file__).resolve().parent / "selectors"


# --- GCS -------------------------------------------------------------------

def gcs_bucket() -> str:
    """GCS bucket name for PDF/log archival."""
    return cfg("gcp.backup_bucket")


def gcs_prefix() -> str:
    """GCS prefix for daemon logs."""
    return cfg("daemon.logging.gcs_prefix")


# --- Vault -----------------------------------------------------------------

def vault_addr() -> str:
    """Vault server address."""
    return cfg("vault.address")


# --- Gemini ----------------------------------------------------------------

def gemini_model() -> str:
    """Default Gemini model for structured analysis tasks."""
    return cfg("daemon.gemini.model")


def captcha_model() -> str:
    """Gemini model for CAPTCHA solving (typically higher-capability)."""
    return cfg("daemon.gemini.captcha_model")


def repair_model() -> str:
    """Gemini model for adaptive XPath/CSS selector repair."""
    return cfg("daemon.gemini.repair_model")
