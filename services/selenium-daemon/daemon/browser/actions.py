"""CDP action executor for browser automation.

Extracted from rakuten_renewal/agent/browser.py ``execute_actions`` method
into a standalone async function. Handles action types: move, click, type,
drag, wait, scroll.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .session import BrowserSession

log = logging.getLogger(__name__)


async def execute_actions(
    browser: BrowserSession,
    actions: list[dict[str, Any]],
) -> None:
    """Execute a list of typed actions from Gemini's response.

    Each action dict must contain a ``"type"`` key. Supported action types:

    - ``move`` -- move mouse to ``{to: {x, y}}`` with optional ``control_points``
      and ``duration_ms``
    - ``click`` -- click at ``{x, y}`` with optional ``button`` and ``hold_ms``
    - ``type`` -- type ``{text}`` with optional ``inter_key_ms: {min, max}``
    - ``drag`` -- drag from ``{from: {x, y}}`` to ``{to: {x, y}}`` with optional
      ``control_points``, ``duration_ms``, ``overshoot``
    - ``wait`` -- pause for ``{ms}`` milliseconds (default 500)
    - ``scroll`` -- scroll at ``{x, y}`` by ``{delta_y}`` with optional ``smooth``

    Unknown action types are logged as warnings and skipped.

    Args:
        browser: A ``BrowserSession`` instance with move_mouse, click,
                 type_text, drag, and scroll methods.
        actions: Ordered list of action dicts to execute.
    """
    for action in actions:
        atype = action.get("type", "")

        if atype == "move":
            to = action.get("to", {})
            await browser.move_mouse(
                to_x=to.get("x", 0),
                to_y=to.get("y", 0),
                control_points=action.get("control_points"),
                duration_ms=action.get("duration_ms"),
            )

        elif atype == "click":
            await browser.click(
                x=action.get("x", 0),
                y=action.get("y", 0),
                button=action.get("button", "left"),
                hold_ms=action.get("hold_ms", 80),
            )

        elif atype == "type":
            inter = action.get("inter_key_ms", {})
            await browser.type_text(
                text=action.get("text", ""),
                inter_key_min=inter.get("min", 50),
                inter_key_max=inter.get("max", 200),
            )

        elif atype == "drag":
            from_pos = action.get("from", {})
            to_pos = action.get("to", {})
            await browser.drag(
                from_x=from_pos.get("x", 0),
                from_y=from_pos.get("y", 0),
                to_x=to_pos.get("x", 0),
                to_y=to_pos.get("y", 0),
                control_points=action.get("control_points"),
                duration_ms=action.get("duration_ms", 800),
                overshoot=action.get("overshoot"),
            )

        elif atype == "wait":
            ms = action.get("ms", 500)
            await asyncio.sleep(ms / 1000.0)

        elif atype == "scroll":
            await browser.scroll(
                x=action.get("x", 960),
                y=action.get("y", 540),
                delta_y=action.get("delta_y", 100),
                smooth=action.get("smooth", True),
            )

        else:
            log.warning("Unknown action type: %s (skipped)", atype)
