"""Keep-alive service for the Rakuten persistent browser session.

Maintains the Rakuten RMS session by periodically navigating to safe pages,
scrolling, and idling with human-like behaviour.  This is the only session
that requires continuous keep-alive because it uses a persistent browser.

Yamato/Sagawa cookie freshness is handled by the Scheduler (periodic cookie
refresh) -- they do not need a KeepAlive service.

The service is paused while a real job is executing on the Rakuten session
and resumes afterward.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import TYPE_CHECKING

from .. import config as cfg

if TYPE_CHECKING:
    from ..sessions.rakuten import RakutenSession

log = logging.getLogger(__name__)


class KeepAliveService:
    """Background keep-alive loop for the Rakuten persistent session.

    Usage::

        svc = KeepAliveService(rakuten_session)
        task = asyncio.create_task(svc.run())

        # Before a Rakuten job executes:
        svc.pause()
        # ... job runs ...
        svc.resume()

        # On shutdown:
        svc.stop()
        await task
    """

    def __init__(self, rakuten_session: RakutenSession) -> None:
        self._session = rakuten_session
        self._paused: bool = False
        self._running: bool = True
        self._consecutive_failures: int = 0
        self._max_consecutive_failures: int = 3

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    def pause(self) -> None:
        """Pause keep-alive while a job is executing on the Rakuten session."""
        self._paused = True
        log.debug("KeepAlive paused")

    def resume(self) -> None:
        """Resume keep-alive after a job completes."""
        self._paused = False
        log.debug("KeepAlive resumed")

    def stop(self) -> None:
        """Signal the keep-alive loop to exit."""
        self._running = False

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Async keep-alive loop. Runs until :meth:`stop` is called.

        Interval between keep-alive actions is randomised between
        ``keepalive_min_secs`` and ``keepalive_max_secs`` from config.
        """
        log.info("KeepAlive service started for Rakuten session")

        while self._running:
            try:
                # Read configurable intervals
                min_secs = cfg.cfg("daemon.sessions.rakuten.keepalive_min_secs")
                max_secs = cfg.cfg("daemon.sessions.rakuten.keepalive_max_secs")
            except Exception:
                min_secs = 300
                max_secs = 600

            # Wait a random interval
            wait_secs = random.uniform(min_secs, max_secs)
            log.debug("KeepAlive sleeping %.0fs", wait_secs)

            # Sleep in small increments so we can respond to stop()
            elapsed = 0.0
            while elapsed < wait_secs and self._running:
                await asyncio.sleep(min(5.0, wait_secs - elapsed))
                elapsed += 5.0

            if not self._running:
                break

            # Skip if paused (a real job is running on this session)
            if self._paused:
                log.debug("KeepAlive is paused, skipping cycle")
                continue

            # Perform keep-alive action
            try:
                await self._keepalive_cycle()
            except Exception:
                log.exception("KeepAlive cycle failed")
                self._consecutive_failures += 1
                if self._consecutive_failures >= self._max_consecutive_failures:
                    await self._handle_repeated_failures()
                    self._consecutive_failures = 0

        log.info("KeepAlive service stopped")

    # ------------------------------------------------------------------
    # Keep-alive cycle
    # ------------------------------------------------------------------

    async def _keepalive_cycle(self) -> None:
        """Single keep-alive cycle with human-like behaviour."""
        # Occasional extended idle (simulates "reading" or AFK)
        if random.random() < 0.1:
            idle_time = random.uniform(15.0, 30.0)
            log.debug("KeepAlive: extended idle for %.0fs", idle_time)
            await asyncio.sleep(idle_time)

        # Call the session's keepalive method
        success = await self._session.keepalive()

        if success:
            self._consecutive_failures = 0
            log.debug("KeepAlive cycle completed successfully")

            # Occasional human-like extra actions
            await self._human_like_extras()
        else:
            self._consecutive_failures += 1
            log.warning(
                "KeepAlive failed (%d consecutive)",
                self._consecutive_failures,
            )

    async def _human_like_extras(self) -> None:
        """Additional human-like actions after successful keepalive.

        These run with low probability to simulate natural browsing
        patterns and reduce detection risk.
        """
        if self._session.browser is None:
            return

        # Random extra scroll (30% chance)
        if random.random() < 0.3:
            scroll_amount = random.randint(100, 400) * random.choice([-1, 1])
            await self._session.browser.scroll(
                x=random.randint(400, 1400),
                y=random.randint(300, 700),
                delta_y=scroll_amount,
                smooth=True,
            )
            await asyncio.sleep(random.uniform(0.5, 2.0))

        # Random mouse wander (20% chance)
        if random.random() < 0.2:
            await self._session.browser.move_mouse(
                to_x=random.randint(100, 1800),
                to_y=random.randint(100, 900),
            )
            await asyncio.sleep(random.uniform(0.3, 1.0))

        # Variable idle after interaction (simulates "reading")
        if random.random() < 0.15:
            idle = random.uniform(5.0, 15.0)
            log.debug("KeepAlive: idle reading for %.0fs", idle)
            await asyncio.sleep(idle)

    # ------------------------------------------------------------------
    # Failure handling
    # ------------------------------------------------------------------

    async def _handle_repeated_failures(self) -> None:
        """Handle repeated keepalive failures by attempting re-login.

        After ``_max_consecutive_failures`` consecutive failures, the
        session is likely expired. Attempt a fresh login.
        """
        log.warning(
            "KeepAlive: %d consecutive failures, attempting re-login",
            self._max_consecutive_failures,
        )

        try:
            success = await self._session.login()
            if success:
                log.info("KeepAlive: re-login successful")
            else:
                log.error(
                    "KeepAlive: re-login failed -- session requires "
                    "human intervention (PENDING_USER_LOGIN)"
                )
        except Exception:
            log.exception("KeepAlive: re-login raised an exception")
