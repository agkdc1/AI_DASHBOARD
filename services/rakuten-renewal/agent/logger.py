"""Structured JSONL logging for Rakuten renewal sessions."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SessionLogger:
    """Append structured events to a per-session JSONL file."""

    def __init__(self, session_id: str, mode: str, log_dir: Path) -> None:
        self.session_id = session_id
        self.mode = mode
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / f"{session_id}.jsonl"
        self._events: list[dict[str, Any]] = []

    def event(self, event_type: str, **kwargs: Any) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event_type,
            **kwargs,
        }
        self._events.append(entry)
        with open(self.log_file, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def session_start(self, attempt: int = 1) -> None:
        self.event("session_start", mode=self.mode, attempt=attempt)

    def session_end(self, result: str, duration_ms: int) -> None:
        self.event("session_end", mode=self.mode, result=result, duration_ms=duration_ms)

    @property
    def events(self) -> list[dict[str, Any]]:
        return list(self._events)

    def summary(self) -> dict[str, Any]:
        """Return a metadata summary suitable for GCS upload."""
        captcha_attempts = sum(
            1 for e in self._events if e["event"] == "captcha_detected"
        )
        captcha_successes = sum(
            1 for e in self._events
            if e["event"] == "captcha_result" and e.get("success")
        )
        gemini_calls = sum(
            1 for e in self._events if e["event"] == "gemini_call"
        )
        duration = 0
        for e in self._events:
            if e["event"] == "session_end":
                duration = e.get("duration_ms", 0)
                break

        return {
            "session_id": self.session_id,
            "mode": self.mode,
            "result": next(
                (e.get("result") for e in reversed(self._events) if e["event"] == "session_end"),
                "unknown",
            ),
            "timestamp": self._events[0]["ts"] if self._events else None,
            "duration_ms": duration,
            "captcha_attempts": captcha_attempts,
            "captcha_successes": captcha_successes,
            "gemini_calls": gemini_calls,
        }
