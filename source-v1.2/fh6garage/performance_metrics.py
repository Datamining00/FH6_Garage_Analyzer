from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from time import perf_counter
from typing import Iterator


class PerformanceMetrics:
    """Small timing/counter collector with no Qt dependency."""

    def __init__(self) -> None:
        self.timings_ms: dict[str, float] = {}
        self.counters: dict[str, int | float | str | bool | None] = {}

    @contextmanager
    def measure(self, name: str) -> Iterator[None]:
        started = perf_counter()
        try:
            yield
        finally:
            self.timings_ms[name] = round((perf_counter() - started) * 1000.0, 3)

    def set(self, name: str, value: int | float | str | bool | None) -> None:
        self.counters[name] = value

    def increment(self, name: str, amount: int = 1) -> None:
        current = self.counters.get(name, 0)
        self.counters[name] = int(current) + int(amount)

    def snapshot(self) -> dict[str, object]:
        return {
            "timings_ms": dict(self.timings_ms),
            "counters": dict(self.counters),
        }


def app_data_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    return base / "FH6GarageAnalyzer"


def write_latest_performance(payload: dict[str, object]) -> Path | None:
    """Atomically write diagnostics outside the FH6 save tree.

    Diagnostics are best-effort only. A permission/disk error must never affect
    save scanning or UI availability.
    """

    try:
        directory = app_data_dir() / "performance"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "latest.json"
        tmp = path.with_suffix(".json.tmp")
        data = dict(payload)
        data["written_at_utc"] = datetime.now(timezone.utc).isoformat()
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
        return path
    except (OSError, TypeError, ValueError):
        return None
