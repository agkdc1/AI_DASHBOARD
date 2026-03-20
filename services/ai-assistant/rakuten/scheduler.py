"""Background scheduler for Rakuten API key renewal reminders."""

import asyncio
import logging

log = logging.getLogger(__name__)

CHECK_INTERVAL_SECS = 6 * 3600  # Every 6 hours


async def start_reminder_loop(service) -> asyncio.Task:
    """Start background task that checks key age and creates Vikunja reminders."""

    async def _loop():
        log.info("Rakuten reminder scheduler started (interval=%ds)", CHECK_INTERVAL_SECS)
        # Initial check on startup
        await asyncio.sleep(30)  # Wait for services to initialize

        while True:
            try:
                result = await service.check_and_remind()
                if result:
                    log.info("Rakuten reminder: %s", result)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Rakuten reminder check failed")

            await asyncio.sleep(CHECK_INTERVAL_SECS)

    task = asyncio.create_task(_loop(), name="rakuten-reminder")
    return task
