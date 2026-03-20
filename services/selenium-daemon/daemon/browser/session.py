"""Browser session management using nodriver (undetected Chrome).

Generalized from rakuten_renewal/agent/browser.py for multi-session support.
Each session has its own name, optional session_id, and configurable user-agent
(for Chrome Extension UA sync). The ``execute_actions`` method has been moved
to ``actions.py``.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import random
from pathlib import Path
from typing import Any

import nodriver as uc

from ..config import cfg, screenshots_dir
from .mouse import generate_path, compute_delays, fitts_duration

log = logging.getLogger(__name__)


class BrowserSession:
    """Manage a headless Chrome session via nodriver with human-like input.

    Args:
        session_name: Logical session name (e.g. ``"rakuten"``, ``"yamato"``).
        session_id: Optional unique run identifier for screenshot sub-directories.
                    Defaults to *session_name* if not provided.
        user_agent: Optional user-agent string override. When provided (e.g. from
                    Chrome Extension cookie injection), it takes precedence over
                    the value in ``config.yaml``.
    """

    def __init__(
        self,
        session_name: str,
        session_id: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        self.session_name = session_name
        self.session_id = session_id or session_name
        self._user_agent_override = user_agent
        self.browser: uc.Browser | None = None
        self.page: uc.Tab | None = None
        self._screenshots_dir = screenshots_dir() / self.session_id
        self._screenshots_dir.mkdir(parents=True, exist_ok=True)
        self._screenshot_counter = 0
        self._cursor_x = 960
        self._cursor_y = 540

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Launch browser with anti-detection settings."""
        width, height = cfg("daemon.browser.window_size")
        headless = cfg("daemon.browser.headless")

        # Ensure DISPLAY is set for non-headless mode (Xvfb)
        if not headless and not os.environ.get("DISPLAY"):
            os.environ["DISPLAY"] = ":99"
        user_agent = self._user_agent_override or cfg("daemon.browser.user_agent")

        # Small random viewport jitter
        width += random.randint(-20, 20)
        height += random.randint(-10, 10)

        self.browser = await uc.start(
            headless=headless,
            browser_args=[
                f"--window-size={width},{height}",
                f"--user-agent={user_agent}",
                "--disable-blink-features=AutomationControlled",
                "--lang=ja-JP",
                "--accept-lang=ja,en-US;q=0.9,en;q=0.8",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-background-networking",
                "--disable-default-apps",
                "--disable-sync",
                "--metrics-recording-only",
                "--no-first-run",
                "--js-flags=--max-old-space-size=512",
            ],
        )
        self.page = await self.browser.get("about:blank")

        # Auto-dismiss JavaScript dialogs (alert/confirm/prompt) to prevent
        # CDP commands from hanging when a dialog is open.
        self.page.add_handler(
            uc.cdp.page.JavascriptDialogOpening,
            self._handle_dialog,
        )

        # Set timezone to JST
        await self.page.send(
            uc.cdp.emulation.set_timezone_override(timezone_id="Asia/Tokyo")
        )
        log.info(
            "[%s] Browser started (headless=%s, %dx%d)",
            self.session_name, headless, width, height,
        )

    async def _handle_dialog(self, event: uc.cdp.page.JavascriptDialogOpening) -> None:
        """Auto-accept JavaScript dialogs to prevent CDP from hanging."""
        log.info(
            "[%s] JS dialog (%s): %s",
            self.session_name, event.type_.value, event.message,
        )
        await self.page.send(
            uc.cdp.page.handle_java_script_dialog(accept=True)
        )

    async def close(self) -> None:
        """Cleanly shut down the browser."""
        if self.browser:
            self.browser.stop()
            self.browser = None
            self.page = None
            log.info("[%s] Browser closed", self.session_name)

    # ------------------------------------------------------------------
    # Navigation & Screenshots
    # ------------------------------------------------------------------

    async def navigate(self, url: str) -> None:
        """Navigate to a URL and wait for load."""
        assert self.page is not None, "Browser not started"
        await self.page.get(url)
        await asyncio.sleep(random.uniform(1.0, 2.0))
        log.info("[%s] Navigated to %s", self.session_name, url)

    async def screenshot(self, label: str = "") -> Path:
        """Take a screenshot and save to the session directory."""
        assert self.page is not None, "Browser not started"
        self._screenshot_counter += 1
        name = f"{self._screenshot_counter:03d}"
        if label:
            name += f"_{label}"
        name += ".png"
        path = self._screenshots_dir / name
        try:
            await asyncio.wait_for(
                self.page.save_screenshot(str(path)), timeout=10.0
            )
            log.debug("[%s] Screenshot: %s", self.session_name, path.name)
        except asyncio.TimeoutError:
            log.warning("[%s] Screenshot timed out: %s", self.session_name, name)
        except Exception:
            log.warning("[%s] Screenshot failed: %s", self.session_name, name, exc_info=True)
        return path

    # ------------------------------------------------------------------
    # Download Configuration
    # ------------------------------------------------------------------

    async def configure_downloads(self, download_dir: str) -> None:
        """Configure Chrome to auto-download files to the given directory.

        Uses CDP ``Page.setDownloadBehavior`` to suppress download dialogs
        and direct files to *download_dir*.

        Args:
            download_dir: Absolute path where downloads should be saved.
        """
        assert self.page is not None, "Browser not started"
        await self.page.send(
            uc.cdp.browser.set_download_behavior(
                behavior="allow",
                download_path=download_dir,
            )
        )
        log.info(
            "[%s] Downloads configured: %s",
            self.session_name, download_dir,
        )

    # ------------------------------------------------------------------
    # Mouse Movement
    # ------------------------------------------------------------------

    async def move_mouse(
        self,
        to_x: int,
        to_y: int,
        control_points: list[dict[str, int]] | None = None,
        duration_ms: int | None = None,
    ) -> None:
        """Move mouse along a Bezier curve to (to_x, to_y)."""
        assert self.page is not None, "Browser not started"

        if duration_ms is None:
            dist = math.hypot(to_x - self._cursor_x, to_y - self._cursor_y)
            duration_ms = fitts_duration(dist)

        path = generate_path(
            start=(self._cursor_x, self._cursor_y),
            end=(to_x, to_y),
            control_points=control_points,
        )
        delays = compute_delays(len(path), duration_ms)

        for (x, y), delay in zip(path, delays):
            await self.page.send(
                uc.cdp.input_.dispatch_mouse_event(
                    type_="mouseMoved",
                    x=x,
                    y=y,
                )
            )
            await asyncio.sleep(delay / 1000.0)

        self._cursor_x = to_x
        self._cursor_y = to_y

    # ------------------------------------------------------------------
    # Click
    # ------------------------------------------------------------------

    async def click(
        self,
        x: int,
        y: int,
        button: str = "left",
        hold_ms: int = 80,
    ) -> None:
        """Click at coordinates with human-like hold duration."""
        assert self.page is not None, "Browser not started"
        cdp_button = "left" if button == "left" else "right"

        await self.page.send(
            uc.cdp.input_.dispatch_mouse_event(
                type_="mousePressed",
                x=x,
                y=y,
                button=uc.cdp.input_.MouseButton(cdp_button),
                click_count=1,
            )
        )
        await asyncio.sleep(hold_ms / 1000.0)
        await self.page.send(
            uc.cdp.input_.dispatch_mouse_event(
                type_="mouseReleased",
                x=x,
                y=y,
                button=uc.cdp.input_.MouseButton(cdp_button),
                click_count=1,
            )
        )
        self._cursor_x = x
        self._cursor_y = y

    # ------------------------------------------------------------------
    # Typing
    # ------------------------------------------------------------------

    async def type_text(
        self,
        text: str,
        inter_key_min: int = 50,
        inter_key_max: int = 200,
    ) -> None:
        """Type text character by character with variable inter-key delays."""
        assert self.page is not None, "Browser not started"
        for char in text:
            await self.page.send(
                uc.cdp.input_.dispatch_key_event(
                    type_="keyDown",
                    text=char,
                    key=char,
                )
            )
            await asyncio.sleep(random.uniform(0.01, 0.03))
            await self.page.send(
                uc.cdp.input_.dispatch_key_event(
                    type_="keyUp",
                    key=char,
                )
            )
            await asyncio.sleep(
                random.randint(inter_key_min, inter_key_max) / 1000.0
            )

    # ------------------------------------------------------------------
    # Drag
    # ------------------------------------------------------------------

    async def drag(
        self,
        from_x: int,
        from_y: int,
        to_x: int,
        to_y: int,
        control_points: list[dict[str, int]] | None = None,
        duration_ms: int = 800,
        overshoot: dict[str, int] | None = None,
    ) -> None:
        """Drag from one point to another (for sliders/puzzles)."""
        assert self.page is not None, "Browser not started"

        # Move to start
        await self.move_mouse(from_x, from_y)

        # Press
        await self.page.send(
            uc.cdp.input_.dispatch_mouse_event(
                type_="mousePressed",
                x=from_x,
                y=from_y,
                button=uc.cdp.input_.MouseButton("left"),
                click_count=1,
            )
        )

        # Generate drag path
        path = generate_path(
            start=(from_x, from_y),
            end=(to_x, to_y),
            control_points=control_points,
            jitter_sigma=0.8,
        )
        delays = compute_delays(len(path), duration_ms)

        for (x, y), delay in zip(path, delays):
            await self.page.send(
                uc.cdp.input_.dispatch_mouse_event(
                    type_="mouseMoved",
                    x=x,
                    y=y,
                    button=uc.cdp.input_.MouseButton("left"),
                )
            )
            await asyncio.sleep(delay / 1000.0)

        # Overshoot and correct
        if overshoot:
            ox, oy = overshoot["x"], overshoot["y"]
            await self.page.send(
                uc.cdp.input_.dispatch_mouse_event(
                    type_="mouseMoved",
                    x=ox,
                    y=oy,
                    button=uc.cdp.input_.MouseButton("left"),
                )
            )
            await asyncio.sleep(overshoot.get("correct_ms", 200) / 1000.0)
            # Correct back
            await self.page.send(
                uc.cdp.input_.dispatch_mouse_event(
                    type_="mouseMoved",
                    x=to_x,
                    y=to_y,
                    button=uc.cdp.input_.MouseButton("left"),
                )
            )

        # Release
        await self.page.send(
            uc.cdp.input_.dispatch_mouse_event(
                type_="mouseReleased",
                x=to_x,
                y=to_y,
                button=uc.cdp.input_.MouseButton("left"),
                click_count=1,
            )
        )
        self._cursor_x = to_x
        self._cursor_y = to_y

    # ------------------------------------------------------------------
    # Scroll
    # ------------------------------------------------------------------

    async def scroll(
        self,
        x: int,
        y: int,
        delta_y: int,
        smooth: bool = True,
    ) -> None:
        """Scroll at position (x, y)."""
        assert self.page is not None, "Browser not started"
        if smooth:
            steps = max(1, abs(delta_y) // 30)
            step_delta = delta_y // steps
            for _ in range(steps):
                await self.page.send(
                    uc.cdp.input_.dispatch_mouse_event(
                        type_="mouseWheel",
                        x=x,
                        y=y,
                        delta_x=0,
                        delta_y=step_delta,
                    )
                )
                await asyncio.sleep(random.uniform(0.02, 0.06))
        else:
            await self.page.send(
                uc.cdp.input_.dispatch_mouse_event(
                    type_="mouseWheel",
                    x=x,
                    y=y,
                    delta_x=0,
                    delta_y=delta_y,
                )
            )
