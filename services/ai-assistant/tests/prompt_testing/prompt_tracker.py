"""Pass rate tracking across prompt test runs for before/after comparison."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

RESULTS_DIR = Path(__file__).parent / "results"


class PromptTracker:
    """Track and compare pass rates across prompt test runs."""

    def __init__(self) -> None:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        module: str,
        version: str,
        total: int,
        passed: int,
        failed_scripts: list[str] | None = None,
    ) -> Path:
        """Record a test run result.

        Args:
            module: Module name (meeting, voice, call, assistant, task_manager).
            version: Version identifier (e.g. "v1", "v2-improved-prompt").
            total: Total number of test scripts.
            passed: Number of passed scripts.
            failed_scripts: List of script IDs that failed.

        Returns:
            Path to the saved result file.
        """
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        result = {
            "module": module,
            "version": version,
            "timestamp": ts,
            "total": total,
            "passed": passed,
            "pass_rate": round(passed / total, 4) if total > 0 else 0.0,
            "failed_scripts": failed_scripts or [],
        }

        filename = f"{module}_{version}_{ts}.json"
        path = RESULTS_DIR / filename
        path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
        log.info("Recorded result: %s (%.1f%% pass rate)", filename, result["pass_rate"] * 100)
        return path

    def compare_versions(self, module: str) -> list[dict]:
        """Load all results for a module, sorted by timestamp.

        Returns:
            List of result dicts with pass_rate trend.
        """
        results = []
        for path in sorted(RESULTS_DIR.glob(f"{module}_*.json")):
            try:
                data = json.loads(path.read_text())
                results.append(data)
            except Exception as e:
                log.warning("Failed to load %s: %s", path, e)
        return results

    def latest(self, module: str) -> dict | None:
        """Get the most recent result for a module."""
        results = self.compare_versions(module)
        return results[-1] if results else None

    def print_comparison(self, module: str) -> None:
        """Print a formatted comparison of all runs for a module."""
        results = self.compare_versions(module)
        if not results:
            print(f"No results for module: {module}")
            return

        print(f"\n{'='*60}")
        print(f"Pass Rate History: {module}")
        print(f"{'='*60}")
        print(f"{'Version':<25} {'Pass Rate':>10} {'Passed':>8} {'Total':>8} {'Timestamp':<16}")
        print(f"{'-'*25} {'-'*10} {'-'*8} {'-'*8} {'-'*16}")
        for r in results:
            print(
                f"{r['version']:<25} {r['pass_rate']*100:>9.1f}% "
                f"{r['passed']:>8} {r['total']:>8} {r['timestamp']:<16}"
            )
        print()
