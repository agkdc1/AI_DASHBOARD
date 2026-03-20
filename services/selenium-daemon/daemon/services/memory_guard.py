"""Memory guardian for the Browser Daemon.

Primarily monitors the **Rakuten persistent Chrome** process since it is the
only browser that runs continuously.  Yamato/Sagawa browsers are ephemeral
(launched per-job, killed after), so they self-limit by design.

Responsibilities:
    1. Monitor Rakuten Chrome's RSS memory via ``psutil``.
    2. Detect and kill orphaned Chrome processes from failed on-demand releases.
    3. Restart Rakuten browser if memory exceeds the per-session limit.
    4. Alert admin if repeated restarts occur.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

import psutil

from .. import config as cfg

if TYPE_CHECKING:
    from ..sessions.base import BaseSession

log = logging.getLogger(__name__)


class MemoryGuardian:
    """Monitor daemon memory and guard against Chrome memory leaks.

    Args:
        sessions: Dict mapping session name to :class:`BaseSession` instance.
    """

    def __init__(self, sessions: dict[str, BaseSession]) -> None:
        self._sessions = sessions
        self._running: bool = True
        self._restart_history: list[float] = []  # timestamps of Rakuten restarts
        self._max_restarts_in_window: int = 3
        self._restart_window_secs: float = 600.0  # 10 minutes

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    def stop(self) -> None:
        """Signal the guardian loop to exit."""
        self._running = False

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Async monitoring loop. Runs until :meth:`stop` is called."""
        log.info("MemoryGuardian started")

        while self._running:
            try:
                interval = cfg.cfg("daemon.memory.check_interval_secs")
            except Exception:
                interval = 30

            await asyncio.sleep(interval)
            if not self._running:
                break

            try:
                await self._check_cycle()
            except Exception:
                log.exception("MemoryGuardian check cycle failed")

        log.info("MemoryGuardian stopped")

    # ------------------------------------------------------------------
    # Check cycle
    # ------------------------------------------------------------------

    async def _check_cycle(self) -> None:
        """Single monitoring cycle."""
        try:
            limit_mb = cfg.cfg("daemon.memory.limit_mb")
            warning_mb = cfg.cfg("daemon.memory.warning_mb")
            per_session_max_mb = cfg.cfg("daemon.memory.per_session_max_mb")
        except Exception:
            limit_mb = 2500
            warning_mb = 2000
            per_session_max_mb = 800

        # 1. Check Rakuten Chrome RSS
        rakuten_rss_mb = await self._get_rakuten_chrome_rss()
        if rakuten_rss_mb is not None:
            log.debug("Rakuten Chrome RSS: %.0f MB", rakuten_rss_mb)

            if rakuten_rss_mb > per_session_max_mb:
                log.warning(
                    "Rakuten Chrome RSS %.0f MB exceeds limit %d MB",
                    rakuten_rss_mb,
                    per_session_max_mb,
                )
                await self._handle_rakuten_over_limit()

        # 2. Check for orphaned on-demand Chrome processes
        orphan_count = await self._kill_orphaned_chromes()
        if orphan_count > 0:
            log.warning(
                "Killed %d orphaned Chrome process(es) "
                "(likely failed on-demand releases)",
                orphan_count,
            )

        # 3. Check total daemon RSS
        daemon_rss_mb = self._get_daemon_rss()
        if daemon_rss_mb > warning_mb:
            log.warning(
                "Total daemon RSS %.0f MB exceeds warning threshold %d MB",
                daemon_rss_mb,
                warning_mb,
            )

        if daemon_rss_mb > limit_mb:
            log.error(
                "Total daemon RSS %.0f MB exceeds hard limit %d MB, "
                "force-restarting Rakuten Chrome",
                daemon_rss_mb,
                limit_mb,
            )
            await self._force_restart_rakuten()

    # ------------------------------------------------------------------
    # Rakuten Chrome monitoring
    # ------------------------------------------------------------------

    async def _get_rakuten_chrome_rss(self) -> float | None:
        """Get the total RSS (MB) of the Rakuten Chrome process tree.

        Returns ``None`` if the Rakuten session has no active browser.
        """
        rakuten = self._sessions.get("rakuten")
        if rakuten is None or rakuten.browser is None:
            return None

        browser_obj = rakuten.browser.browser
        if browser_obj is None:
            return None

        # nodriver's Browser stores the process; try to get its PID
        try:
            # nodriver stores the browser process as browser._process
            proc = getattr(browser_obj, "_process", None)
            if proc is None:
                return None
            pid = proc.pid
        except AttributeError:
            return None

        # Sum RSS of the process and all children
        try:
            parent = psutil.Process(pid)
            total_rss = parent.memory_info().rss
            for child in parent.children(recursive=True):
                try:
                    total_rss += child.memory_info().rss
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            return total_rss / (1024 * 1024)  # bytes -> MB
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None

    async def _handle_rakuten_over_limit(self) -> None:
        """Attempt to reclaim Rakuten Chrome memory.

        Strategy:
        1. Try closing non-essential tabs first.
        2. If still over limit, restart the browser entirely.
        """
        rakuten = self._sessions.get("rakuten")
        if rakuten is None or rakuten.browser is None:
            return

        # Attempt tab cleanup
        try:
            browser_obj = rakuten.browser.browser
            if browser_obj is not None:
                targets = await browser_obj.targets
                if len(targets) > 1:
                    log.info(
                        "Closing %d non-essential tab(s)",
                        len(targets) - 1,
                    )
                    for target in targets[1:]:
                        try:
                            await target.close()
                        except Exception:
                            pass
                    await asyncio.sleep(2.0)
        except Exception:
            log.debug("Tab cleanup failed")

        # Re-check RSS after cleanup
        rss = await self._get_rakuten_chrome_rss()
        try:
            per_session_max = cfg.cfg("daemon.memory.per_session_max_mb")
        except Exception:
            per_session_max = 800

        if rss is not None and rss > per_session_max:
            log.warning(
                "Rakuten Chrome still at %.0f MB after tab cleanup, restarting",
                rss,
            )
            await self._force_restart_rakuten()

    async def _force_restart_rakuten(self) -> None:
        """Force-kill and restart the Rakuten browser.

        Cookies are saved before killing so the session can be restored.
        Tracks restart frequency and disables the session if too many
        restarts occur in a short window.
        """
        rakuten = self._sessions.get("rakuten")
        if rakuten is None:
            return

        now = time.monotonic()
        self._restart_history.append(now)

        # Prune old entries outside the window
        self._restart_history = [
            t for t in self._restart_history
            if now - t < self._restart_window_secs
        ]

        if len(self._restart_history) >= self._max_restarts_in_window:
            log.error(
                "Rakuten Chrome restarted %d times in %.0fs -- "
                "disabling session and alerting admin",
                len(self._restart_history),
                self._restart_window_secs,
            )
            rakuten.is_logged_in = False
            # TODO: Send admin alert via scheduler/notifier
            return

        log.info("Force-restarting Rakuten Chrome")

        try:
            await rakuten.save_cookies()
        except Exception:
            log.exception("Failed to save cookies before restart")

        try:
            await rakuten.close()
        except Exception:
            log.exception("Failed to close Rakuten session cleanly")

        # Re-login
        try:
            success = await rakuten.login()
            if success:
                log.info("Rakuten Chrome restarted and re-logged in")
            else:
                log.error(
                    "Rakuten re-login failed after restart -- "
                    "session requires human intervention"
                )
        except Exception:
            log.exception("Rakuten re-login failed after restart")

    # ------------------------------------------------------------------
    # Orphan cleanup
    # ------------------------------------------------------------------

    async def _kill_orphaned_chromes(self) -> int:
        """Find and kill Chrome processes not owned by any active session.

        On-demand sessions (Yamato/Sagawa) should have no Chrome processes
        outside of active jobs. Any stray Chrome processes indicate a
        ``release_browser`` failure.

        Returns:
            Number of orphaned processes killed.
        """
        # Collect PIDs of known active browsers
        known_pids: set[int] = set()
        for session in self._sessions.values():
            if session.browser is not None and session.browser.browser is not None:
                try:
                    proc = getattr(session.browser.browser, "_process", None)
                    if proc is not None:
                        parent = psutil.Process(proc.pid)
                        known_pids.add(parent.pid)
                        for child in parent.children(recursive=True):
                            known_pids.add(child.pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
                    pass

        # Find all Chrome/Chromium processes
        killed = 0
        daemon_pid = os.getpid()
        for proc in psutil.process_iter(["pid", "name", "ppid"]):
            try:
                name = proc.info["name"].lower()
                if "chrom" not in name:
                    continue
                pid = proc.info["pid"]
                if pid in known_pids:
                    continue
                # Only kill Chrome processes that are descendants of the daemon
                # (to avoid killing the user's personal Chrome)
                try:
                    parent_chain = proc.parents()
                    is_descendant = any(
                        p.pid == daemon_pid for p in parent_chain
                    )
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    is_descendant = False

                if is_descendant:
                    log.warning(
                        "Killing orphaned Chrome process PID %d (%s)",
                        pid,
                        name,
                    )
                    proc.kill()
                    killed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        return killed

    # ------------------------------------------------------------------
    # Daemon-level RSS
    # ------------------------------------------------------------------

    @staticmethod
    def _get_daemon_rss() -> float:
        """Get total RSS (MB) of the current process and all children."""
        try:
            current = psutil.Process(os.getpid())
            total = current.memory_info().rss
            for child in current.children(recursive=True):
                try:
                    total += child.memory_info().rss
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            return total / (1024 * 1024)
        except Exception:
            return 0.0
