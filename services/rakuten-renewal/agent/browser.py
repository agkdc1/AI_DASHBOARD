"""Browser session management using nodriver (undetected Chrome)."""

from __future__ import annotations

import asyncio
import logging
import random
from pathlib import Path

import nodriver as uc

from . import config as cfg
from .mouse import generate_path, compute_delays, fitts_duration, Point

log = logging.getLogger(__name__)


class BrowserSession:
    """Manage a headless Chrome session via nodriver with human-like input."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.browser: uc.Browser | None = None
        self.page: uc.Tab | None = None
        self._screenshots_dir = cfg.screenshots_dir() / session_id
        self._screenshots_dir.mkdir(parents=True, exist_ok=True)
        self._screenshot_counter = 0
        self._cursor_x = 960
        self._cursor_y = 540

    async def start(self) -> None:
        """Launch browser with anti-detection settings."""
        width, height = cfg.cfg("rakuten.browser.window_size")
        headless = cfg.cfg("rakuten.browser.headless")
        user_agent = cfg.cfg("rakuten.browser.user_agent")

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
            ],
        )
        self.page = await self.browser.get("about:blank")

        # Set timezone to JST
        await self.page.send(uc.cdp.emulation.set_timezone_override(timezone_id="Asia/Tokyo"))
        log.info("Browser started (headless=%s, %dx%d)", headless, width, height)

    async def close(self) -> None:
        if self.browser:
            self.browser.stop()
            self.browser = None
            self.page = None
            log.info("Browser closed")

    async def navigate(self, url: str) -> None:
        """Navigate to a URL and wait for load."""
        assert self.page is not None
        await self.page.get(url)
        await asyncio.sleep(random.uniform(1.0, 2.0))
        log.info("Navigated to %s", url)

    async def screenshot(self, label: str = "") -> Path:
        """Take a screenshot and save to the session directory."""
        assert self.page is not None
        self._screenshot_counter += 1
        name = f"{self._screenshot_counter:03d}"
        if label:
            name += f"_{label}"
        name += ".png"
        path = self._screenshots_dir / name
        await self.page.save_screenshot(str(path))
        log.debug("Screenshot: %s", path.name)
        return path

    async def move_mouse(
        self,
        to_x: int,
        to_y: int,
        control_points: list[dict[str, int]] | None = None,
        duration_ms: int | None = None,
    ) -> None:
        """Move mouse along a Bezier curve to (to_x, to_y)."""
        assert self.page is not None

        if duration_ms is None:
            import math
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

    async def click(
        self,
        x: int,
        y: int,
        button: str = "left",
        hold_ms: int = 80,
    ) -> None:
        """Click at coordinates with human-like hold duration."""
        assert self.page is not None
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

    async def type_text(
        self,
        text: str,
        inter_key_min: int = 50,
        inter_key_max: int = 200,
    ) -> None:
        """Type text character by character with variable inter-key delays."""
        assert self.page is not None
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
            await asyncio.sleep(random.randint(inter_key_min, inter_key_max) / 1000.0)

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
        assert self.page is not None

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
                    type_="mouseMoved", x=ox, y=oy,
                    button=uc.cdp.input_.MouseButton("left"),
                )
            )
            await asyncio.sleep(overshoot.get("correct_ms", 200) / 1000.0)
            # Correct back
            await self.page.send(
                uc.cdp.input_.dispatch_mouse_event(
                    type_="mouseMoved", x=to_x, y=to_y,
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

    async def scroll(self, x: int, y: int, delta_y: int, smooth: bool = True) -> None:
        """Scroll at position (x, y)."""
        assert self.page is not None
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

    async def execute_actions(self, actions: list[dict]) -> None:
        """Execute a list of typed actions from Gemini's response."""
        for action in actions:
            atype = action["type"]

            if atype == "move":
                await self.move_mouse(
                    to_x=action["to"]["x"],
                    to_y=action["to"]["y"],
                    control_points=action.get("control_points"),
                    duration_ms=action.get("duration_ms"),
                )

            elif atype == "click":
                await self.click(
                    x=action["x"],
                    y=action["y"],
                    button=action.get("button", "left"),
                    hold_ms=action.get("hold_ms", 80),
                )

            elif atype == "type":
                inter = action.get("inter_key_ms", {})
                await self.type_text(
                    text=action["text"],
                    inter_key_min=inter.get("min", 50),
                    inter_key_max=inter.get("max", 200),
                )

            elif atype == "drag":
                await self.drag(
                    from_x=action["from"]["x"],
                    from_y=action["from"]["y"],
                    to_x=action["to"]["x"],
                    to_y=action["to"]["y"],
                    control_points=action.get("control_points"),
                    duration_ms=action.get("duration_ms", 800),
                    overshoot=action.get("overshoot"),
                )

            elif atype == "wait":
                ms = action.get("ms", 500)
                await asyncio.sleep(ms / 1000.0)

            elif atype == "scroll":
                await self.scroll(
                    x=action.get("x", 960),
                    y=action.get("y", 540),
                    delta_y=action.get("delta_y", 100),
                    smooth=action.get("smooth", True),
                )

            else:
                log.warning("Unknown action type: %s", atype)
