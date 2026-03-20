"""Upload / download session artifacts to GCS."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from google.cloud import storage
from google.auth import identity_pool

from . import config as cfg

log = logging.getLogger(__name__)

# WIF credential config (same as backup system)
_WIF_CRED = cfg.repo_root() / "Vault" / "pki" / "wif-credential-config.json"


def _client() -> storage.Client:
    creds = identity_pool.Credentials.from_file(str(_WIF_CRED))
    return storage.Client(
        project=cfg.cfg("gcp.project_id"),
        credentials=creds,
    )


def _bucket() -> storage.Bucket:
    return _client().bucket(cfg.gcs_bucket())


def upload_file(local_path: Path, gcs_path: str) -> None:
    """Upload a single file to GCS."""
    blob = _bucket().blob(gcs_path)
    blob.upload_from_filename(str(local_path))
    log.info("GCS upload: %s -> gs://%s/%s", local_path.name, cfg.gcs_bucket(), gcs_path)


def upload_json(data: Any, gcs_path: str) -> None:
    """Upload a JSON-serializable object directly to GCS."""
    blob = _bucket().blob(gcs_path)
    blob.upload_from_string(
        json.dumps(data, ensure_ascii=False, indent=2),
        content_type="application/json",
    )
    log.info("GCS upload JSON: gs://%s/%s", cfg.gcs_bucket(), gcs_path)


def download_file(gcs_path: str, local_path: Path) -> None:
    """Download a single file from GCS."""
    local_path.parent.mkdir(parents=True, exist_ok=True)
    blob = _bucket().blob(gcs_path)
    blob.download_to_filename(str(local_path))
    log.debug("GCS download: gs://%s/%s -> %s", cfg.gcs_bucket(), gcs_path, local_path)


def list_prefix(prefix: str) -> list[str]:
    """List blob names under a GCS prefix."""
    blobs = _bucket().list_blobs(prefix=prefix, delimiter="/")
    # Collect prefixes (subdirectories)
    prefixes: list[str] = []
    for page in blobs.pages:
        prefixes.extend(page.prefixes)
    return sorted(prefixes)


def upload_session(
    session_id: str,
    mode: str,
    log_dir: Path,
    screenshots_dir: Path,
    state_file: Path,
    metadata: dict[str, Any],
    prompt_updated: bool = False,
    prompt_version: int | None = None,
) -> None:
    """Upload all artifacts from a completed session to GCS."""
    prefix = f"{cfg.gcs_prefix()}/sessions/{session_id}"
    retries = 3

    for attempt in range(1, retries + 1):
        try:
            # 1. Session log
            log_file = log_dir / f"{session_id}.jsonl"
            if log_file.exists():
                upload_file(log_file, f"{prefix}/session.jsonl")

            # 2. Screenshots
            session_ss_dir = screenshots_dir / session_id
            if session_ss_dir.is_dir():
                for png in sorted(session_ss_dir.glob("*.png")):
                    upload_file(png, f"{prefix}/screenshots/{png.name}")

            # 3. Metadata summary
            upload_json(metadata, f"{prefix}/metadata.json")

            # 4. State file
            if state_file.exists():
                upload_file(state_file, f"{cfg.gcs_prefix()}/state.json")

            # 5. Prompt history (if updated this session)
            if prompt_updated and prompt_version is not None:
                prompts_dir = cfg.prompts_dir()
                history = prompts_dir / "history.jsonl"
                if history.exists():
                    upload_file(history, f"{cfg.gcs_prefix()}/prompts/history.jsonl")
                new_prompt = prompts_dir / f"captcha_v{prompt_version}.txt"
                if new_prompt.exists():
                    upload_file(new_prompt, f"{cfg.gcs_prefix()}/prompts/captcha_v{prompt_version}.txt")

            log.info("Session %s uploaded to GCS (%s)", session_id, prefix)
            return

        except Exception:
            if attempt == retries:
                log.exception("GCS upload failed after %d retries", retries)
                raise
            log.warning("GCS upload attempt %d failed, retrying...", attempt)


def download_recent_sessions(n: int = 5) -> list[Path]:
    """Download the last *n* session logs from GCS to a temp dir."""
    import tempfile

    prefix = f"{cfg.gcs_prefix()}/sessions/"
    session_dirs = list_prefix(prefix)

    # Take the last N (sorted by timestamp in name)
    recent = session_dirs[-n:]
    tmp = Path(tempfile.mkdtemp(prefix="rakuten_meta_"))
    downloaded: list[Path] = []

    for sess_prefix in recent:
        sess_name = sess_prefix.rstrip("/").split("/")[-1]
        local_dir = tmp / sess_name
        local_dir.mkdir(parents=True, exist_ok=True)

        # Download session.jsonl
        try:
            download_file(f"{sess_prefix}session.jsonl", local_dir / "session.jsonl")
            downloaded.append(local_dir)
        except Exception:
            log.warning("Could not download %ssession.jsonl", sess_prefix)

    return downloaded
