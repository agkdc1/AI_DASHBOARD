"""Headless PDF download handler using Chrome DevTools Protocol.

Configures Chrome to automatically download files to a designated directory
(no dialog, no print prompt), monitors for completed downloads, and verifies
the result is a valid PDF.

Carrier portals may deliver PDFs in several ways:
  1. Direct file download (Content-Disposition: attachment)
  2. New tab with embedded PDF viewer
  3. JavaScript blob: URL

This module handles case 1 via CDP ``setDownloadBehavior``. Cases 2 and 3
require additional CDP interception that can be added as needed.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import nodriver as uc

log = logging.getLogger(__name__)

# PDF magic bytes (%PDF)
_PDF_MAGIC = b"%PDF"


class DownloadHandler:
    """Configure headless Chrome for automatic PDF downloads via CDP."""

    # ------------------------------------------------------------------
    # Browser configuration
    # ------------------------------------------------------------------

    @staticmethod
    async def configure_browser(page: Any, download_dir: Path) -> None:
        """Set CDP download behaviour so files go directly to *download_dir*.

        Tries both ``browser.set_download_behavior`` and
        ``page.set_download_behavior`` since the available CDP domain
        varies between Chrome versions.

        Args:
            page: A nodriver ``Tab`` (page) object.
            download_dir: Absolute path for downloaded files.
        """
        download_dir.mkdir(parents=True, exist_ok=True)
        dl_path = str(download_dir)

        # Method 1: Browser-level download behaviour
        try:
            await page.send(
                uc.cdp.browser.set_download_behavior(
                    behavior="allow",
                    download_path=dl_path,
                )
            )
            log.info(
                "CDP browser.setDownloadBehavior -> %s", dl_path
            )
        except Exception:
            log.debug(
                "browser.setDownloadBehavior not available, trying page-level"
            )

        # Method 2: Page-level download behaviour (fallback)
        try:
            await page.send(
                uc.cdp.page.set_download_behavior(
                    behavior="allow",
                    download_path=dl_path,
                )
            )
            log.info(
                "CDP page.setDownloadBehavior -> %s", dl_path
            )
        except Exception:
            log.debug("page.setDownloadBehavior not available either")

    # ------------------------------------------------------------------
    # Download monitoring
    # ------------------------------------------------------------------

    @staticmethod
    async def wait_for_download(
        download_dir: Path,
        timeout_secs: int = 60,
        poll_interval: float = 1.0,
    ) -> Path | None:
        """Poll *download_dir* for a new ``.pdf`` file.

        Chrome downloads typically create a ``.crdownload`` partial file
        first, then rename to the final extension. This method waits
        until a fully-written ``.pdf`` appears.

        Args:
            download_dir: The directory to watch.
            timeout_secs: Maximum seconds to wait before giving up.
            poll_interval: Seconds between checks.

        Returns:
            Path to the downloaded PDF, or ``None`` on timeout.
        """
        # Snapshot existing PDFs before the download starts
        existing: set[Path] = set(download_dir.glob("*.pdf"))
        elapsed = 0.0

        while elapsed < timeout_secs:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            # Check for any new .pdf files
            current = set(download_dir.glob("*.pdf"))
            new_files = current - existing
            if new_files:
                # Take the most recently modified new file
                newest = max(new_files, key=lambda p: p.stat().st_mtime)
                # Extra wait to ensure file writing is complete
                await asyncio.sleep(0.5)
                if newest.exists() and newest.stat().st_size > 0:
                    log.info(
                        "Download complete: %s (%d bytes, %.1fs)",
                        newest.name,
                        newest.stat().st_size,
                        elapsed,
                    )
                    return newest

            # Also check if a .crdownload file is in progress
            in_progress = list(download_dir.glob("*.crdownload"))
            if in_progress and elapsed < timeout_secs:
                log.debug(
                    "Download in progress: %s",
                    [f.name for f in in_progress],
                )

        log.warning(
            "Download timeout after %ds in %s", timeout_secs, download_dir
        )
        return None

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    @staticmethod
    def verify_pdf(path: Path) -> bool:
        """Check that *path* exists and is a valid PDF (magic bytes check).

        Args:
            path: Path to the file to verify.

        Returns:
            ``True`` if the file exists and starts with ``%PDF``.
        """
        if not path.exists():
            log.warning("PDF verification failed: file not found (%s)", path)
            return False

        try:
            with open(path, "rb") as f:
                header = f.read(4)
            if header.startswith(_PDF_MAGIC):
                log.debug("PDF verified: %s", path.name)
                return True
            else:
                log.warning(
                    "PDF verification failed: bad magic bytes %r (%s)",
                    header,
                    path.name,
                )
                return False
        except OSError:
            log.exception("PDF verification failed: read error (%s)", path)
            return False

    # ------------------------------------------------------------------
    # Filename generation
    # ------------------------------------------------------------------

    @staticmethod
    def generate_filename(
        carrier: str,
        sales_order_id: str,
        tracking_number: str,
    ) -> str:
        """Generate a standardised PDF filename.

        Format: ``{YYYY-MM-DD}_{sales_order_id}_{tracking_number}.pdf``

        Args:
            carrier: Carrier identifier (used in path, not filename).
            sales_order_id: InvenTree sales order ID, e.g. ``"SO-0042"``.
            tracking_number: Carrier-assigned tracking number.

        Returns:
            Filename string (no directory component).
        """
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        # Sanitise fields for safe filenames
        so = sales_order_id.replace("/", "-").replace("\\", "-")
        tn = tracking_number.replace("/", "-").replace("\\", "-")
        return f"{date_str}_{so}_{tn}.pdf"
