from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict, deque
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_MAX_RECENT = 300
_MAX_BYTES = 5 * 1024 * 1024
_ROTATIONS = 3
_enabled = False
_recent: deque["PerfEvent"] = deque(maxlen=_MAX_RECENT)
_startup_recent: list["PerfEvent"] = []
_aggregate_samples: dict[str, dict[str, float | int]] = {}
_lock = threading.RLock()
_startup_started_ns: int | None = None
_startup_active = False
_startup_waiting_for_scan = False
_startup_finished = False


@dataclass(slots=True)
class PerfEvent:
    timestamp: str
    name: str
    elapsed_ms: float
    thread: str
    item_count: int | None = None
    byte_count: int | None = None
    detail: str = ""


class PerformanceMetrics:
    """Compatibility collector retained for existing callers/tests."""

    def __init__(self) -> None:
        self.timings_ms: dict[str, float] = {}
        self.counters: dict[str, int | float | str | bool | None] = {}

    @contextmanager
    def measure(self, name: str) -> Iterator[None]:
        started = time.perf_counter_ns()
        try:
            yield
        finally:
            self.timings_ms[name] = round((time.perf_counter_ns() - started) / 1_000_000.0, 3)

    def set(self, name: str, value: float | str | bool | None) -> None:
        self.counters[name] = value

    def increment(self, name: str, amount: int = 1) -> None:
        current = self.counters.get(name, 0)
        self.counters[name] = int(current) + int(amount)

    def snapshot(self) -> dict[str, object]:
        return {"timings_ms": dict(self.timings_ms), "counters": dict(self.counters)}


def app_data_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    return base / "FH6GarageAnalyzer"


def log_dir() -> Path:
    return app_data_dir() / "performance"


def log_path() -> Path:
    return log_dir() / "performance.jsonl"


def set_enabled(value: bool) -> None:
    global _enabled
    _enabled = bool(value)


def is_enabled() -> bool:
    return _enabled


def begin_startup(started_ns: int | None = None) -> None:
    """Start one always-on launch measurement session."""
    global _startup_started_ns, _startup_active, _startup_waiting_for_scan, _startup_finished
    with _lock:
        _startup_recent.clear()
    _startup_started_ns = int(started_ns) if started_ns is not None else time.perf_counter_ns()
    _startup_active = True
    _startup_waiting_for_scan = False
    _startup_finished = False


def startup_active() -> bool:
    return bool(_startup_active and not _startup_finished and _startup_started_ns is not None)


def set_startup_waiting_for_scan(value: bool) -> None:
    global _startup_waiting_for_scan
    _startup_waiting_for_scan = bool(value)


def startup_waiting_for_scan() -> bool:
    return bool(_startup_waiting_for_scan)


def startup_elapsed_ms() -> float:
    if _startup_started_ns is None:
        return 0.0
    return max(0.0, (time.perf_counter_ns() - _startup_started_ns) / 1_000_000.0)


def _rotate(path: Path) -> None:
    try:
        if not path.is_file() or path.stat().st_size < _MAX_BYTES:
            return
    except OSError:
        return
    for index in range(_ROTATIONS, 0, -1):
        src = path if index == 1 else path.with_suffix(path.suffix + f".{index - 1}")
        dst = path.with_suffix(path.suffix + f".{index}")
        try:
            if src.exists():
                dst.unlink(missing_ok=True)
                src.replace(dst)
        except OSError:
            pass


def _event(
    name: str,
    elapsed_ms: float,
    *,
    item_count: int | None = None,
    byte_count: int | None = None,
    detail: str = "",
) -> PerfEvent:
    return PerfEvent(
        timestamp=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        name=str(name),
        elapsed_ms=round(float(elapsed_ms), 3),
        thread=threading.current_thread().name,
        item_count=item_count,
        byte_count=byte_count,
        detail=str(detail or ""),
    )


def _write_event(event: PerfEvent) -> None:
    path = log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _rotate(path)
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(asdict(event), ensure_ascii=False, separators=(",", ":")) + "\n")
    except OSError:
        pass


def record(
    name: str,
    elapsed_ms: float,
    *,
    item_count: int | None = None,
    byte_count: int | None = None,
    detail: str = "",
    force: bool = False,
) -> None:
    if not _enabled and not force:
        return
    event = _event(name, elapsed_ms, item_count=item_count, byte_count=byte_count, detail=detail)
    with _lock:
        _recent.append(event)
        _write_event(event)


def add_sample(name: str, elapsed_ms: float) -> None:
    """Add a high-frequency timing sample without consuming the rolling event buffer."""
    if not _enabled:
        return
    elapsed = max(0.0, float(elapsed_ms))
    with _lock:
        row = _aggregate_samples.setdefault(str(name), {"count": 0, "total_ms": 0.0, "max_ms": 0.0})
        row["count"] = int(row["count"]) + 1
        row["total_ms"] = float(row["total_ms"]) + elapsed
        row["max_ms"] = max(float(row["max_ms"]), elapsed)


def record_startup(
    name: str,
    elapsed_ms: float,
    *,
    item_count: int | None = None,
    byte_count: int | None = None,
    detail: str = "",
) -> None:
    """Record startup independently from the runtime rolling buffer lifetime."""
    event = _event(name, elapsed_ms, item_count=item_count, byte_count=byte_count, detail=detail)
    with _lock:
        _startup_recent.append(event)
        _recent.append(event)
        _write_event(event)


def finish_startup(*, detail: str = "") -> None:
    global _startup_active, _startup_finished, _startup_waiting_for_scan
    if not startup_active():
        return
    record_startup("startup.total", startup_elapsed_ms(), detail=detail)
    _startup_finished = True
    _startup_active = False
    _startup_waiting_for_scan = False


@contextmanager
def measure(
    name: str,
    *,
    item_count: int | None = None,
    byte_count: int | None = None,
    detail: str = "",
) -> Iterator[None]:
    if not _enabled:
        yield
        return
    started = time.perf_counter_ns()
    try:
        yield
    finally:
        record(name, (time.perf_counter_ns() - started) / 1_000_000.0, item_count=item_count, byte_count=byte_count, detail=detail)


@contextmanager
def measure_startup(
    name: str,
    *,
    item_count: int | None = None,
    byte_count: int | None = None,
    detail: str = "",
) -> Iterator[None]:
    if not startup_active():
        yield
        return
    started = time.perf_counter_ns()
    try:
        yield
    finally:
        record_startup(name, (time.perf_counter_ns() - started) / 1_000_000.0, item_count=item_count, byte_count=byte_count, detail=detail)


def recent_events(limit: int = 100) -> list[PerfEvent]:
    with _lock:
        return list(_recent)[-max(0, int(limit)):]


def startup_events() -> list[PerfEvent]:
    with _lock:
        return list(_startup_recent)


def _format_event(event: PerfEvent) -> str:
    meta: list[str] = []
    if event.item_count is not None:
        meta.append(f"items={event.item_count}")
    if event.byte_count is not None:
        meta.append(f"bytes={event.byte_count}")
    if event.detail:
        meta.append(event.detail)
    suffix = " · " + " · ".join(meta) if meta else ""
    return f"{event.elapsed_ms:10.3f} ms  {event.name}{suffix}  [{event.thread}]"


def format_recent(limit: int = 100, *, include_startup: bool = False) -> str:
    events = recent_events(limit)
    if not include_startup:
        events = [event for event in events if not event.name.startswith("startup.")]
    return "\n".join(_format_event(event) for event in events)


def format_startup() -> str:
    return "\n".join(_format_event(event) for event in startup_events())


def aggregate_recent(limit: int = 300, *, include_startup: bool = False) -> list[dict[str, Any]]:
    events = recent_events(limit)
    if not include_startup:
        events = [event for event in events if not event.name.startswith("startup.")]
    grouped: dict[str, list[float]] = defaultdict(list)
    for event in events:
        grouped[event.name].append(float(event.elapsed_ms))

    combined: dict[str, dict[str, float | int]] = {}
    for name, values in grouped.items():
        combined[name] = {"count": len(values), "total_ms": sum(values), "max_ms": max(values)}
    with _lock:
        for name, row in _aggregate_samples.items():
            target = combined.setdefault(name, {"count": 0, "total_ms": 0.0, "max_ms": 0.0})
            target["count"] = int(target["count"]) + int(row["count"])
            target["total_ms"] = float(target["total_ms"]) + float(row["total_ms"])
            target["max_ms"] = max(float(target["max_ms"]), float(row["max_ms"]))

    rows: list[dict[str, Any]] = []
    for name, row in combined.items():
        count = max(1, int(row["count"]))
        total = float(row["total_ms"])
        rows.append({
            "name": name,
            "count": count,
            "total_ms": round(total, 3),
            "avg_ms": round(total / count, 3),
            "max_ms": round(float(row["max_ms"]), 3),
        })
    rows.sort(key=lambda row: (-float(row["total_ms"]), str(row["name"])))
    return rows


def format_aggregate(limit: int = 300, *, max_rows: int = 40) -> str:
    rows = aggregate_recent(limit)
    if not rows:
        return ""
    lines = ["count    total ms      avg ms      max ms  event"]
    for row in rows[: max(1, int(max_rows))]:
        lines.append(
            f"{int(row['count']):5d}  {float(row['total_ms']):10.3f}  "
            f"{float(row['avg_ms']):10.3f}  {float(row['max_ms']):10.3f}  {row['name']}"
        )
    return "\n".join(lines)


def clear_recent(*, clear_file: bool = False) -> None:
    with _lock:
        _recent.clear()
        _startup_recent.clear()
        _aggregate_samples.clear()
        if clear_file:
            for index in range(_ROTATIONS + 1):
                path = log_path() if index == 0 else log_path().with_suffix(log_path().suffix + f".{index}")
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass


def write_latest_performance(payload: dict[str, object]) -> Path | None:
    """Compatibility helper for legacy diagnostics callers."""
    try:
        directory = log_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "latest.json"
        data = dict(payload)
        data["written_at_utc"] = datetime.now(timezone.utc).isoformat()
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)
        return path
    except (OSError, TypeError, ValueError):
        return None
