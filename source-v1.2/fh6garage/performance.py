from __future__ import annotations

import json
import os
import platform
import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator


@dataclass(frozen=True, slots=True)
class PerformanceEvent:
    name: str
    duration_ms: float
    timestamp: str
    thread: str
    details: dict[str, Any]


class PerformanceRecorder:
    """Thread-safe wall-clock recorder for the diagnostic v1.3.2 build."""

    FORMAT_VERSION = 1

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._events: list[PerformanceEvent] = []
        self._session_started = datetime.now().astimezone()

    def reset(self) -> None:
        with self._lock:
            self._events.clear()
            self._session_started = datetime.now().astimezone()

    def events(self) -> list[PerformanceEvent]:
        with self._lock:
            return list(self._events)

    def record(
        self,
        name: str,
        duration_seconds: float,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        event = PerformanceEvent(
            name=str(name),
            duration_ms=max(0.0, float(duration_seconds) * 1000.0),
            timestamp=datetime.now().astimezone().isoformat(timespec="milliseconds"),
            thread=threading.current_thread().name,
            details=self._clean_details(details or {}),
        )
        with self._lock:
            self._events.append(event)

    @contextmanager
    def measure(
        self,
        name: str,
        details: dict[str, Any] | None = None,
    ) -> Iterator[None]:
        started = time.perf_counter()
        try:
            yield
        finally:
            self.record(name, time.perf_counter() - started, details=details)

    @staticmethod
    def _clean_details(details: dict[str, Any]) -> dict[str, Any]:
        """Keep diagnostic metadata compact and JSON-safe.

        Full save paths are deliberately not retained. Path objects are reduced
        to their final component, which is enough to identify a slow container
        without copying the user's directory structure into the report.
        """
        result: dict[str, Any] = {}
        for key, value in details.items():
            if isinstance(value, Path):
                result[str(key)] = value.name
            elif isinstance(value, (str, int, float, bool)) or value is None:
                result[str(key)] = value
            elif isinstance(value, (list, tuple, set)):
                result[str(key)] = [
                    item.name if isinstance(item, Path) else str(item)
                    for item in value
                ]
            else:
                result[str(key)] = str(value)
        return result

    @staticmethod
    def default_report_dir() -> Path:
        base = Path(
            os.environ.get("LOCALAPPDATA")
            or (Path.home() / "AppData" / "Local")
        )
        return base / "FH6GarageAnalyzer" / "PerformanceReports"

    def save_report(self, directory: Path | None = None) -> tuple[Path, Path]:
        target = Path(directory) if directory is not None else self.default_report_dir()
        target.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        txt_path = target / f"FH6_Performance_Report_{stamp}.txt"
        json_path = target / f"FH6_Performance_Report_{stamp}.json"

        events = self.events()
        payload = {
            "format_version": self.FORMAT_VERSION,
            "application": "FH6 Assistant",
            "application_version": "1.3.2-performance",
            "session_started": self._session_started.isoformat(timespec="seconds"),
            "report_created": datetime.now().astimezone().isoformat(timespec="seconds"),
            "system": {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "processor": platform.processor(),
            },
            "events": [asdict(event) for event in events],
        }
        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        txt_path.write_text(self._render_text(events), encoding="utf-8")
        return txt_path, json_path

    def _render_text(self, events: list[PerformanceEvent]) -> str:
        grouped: dict[str, list[float]] = defaultdict(list)
        for event in events:
            grouped[event.name].append(event.duration_ms)

        lines = [
            "FH6 Assistant v1.3.2 - Performance Report",
            "=" * 54,
            "",
            f"Session started: {self._session_started.isoformat(timespec='seconds')}",
            f"Report created: {datetime.now().astimezone().isoformat(timespec='seconds')}",
            f"Events: {len(events):,}",
            f"Python: {platform.python_version()}",
            f"Platform: {platform.platform()}",
            "",
            "Important",
            "---------",
            "Timers can be nested. Do not add all Total values together; a parent",
            "operation may already include its child operations.",
            "Wall-clock time is measured with time.perf_counter().",
            "",
            "Aggregate by operation",
            "----------------------",
            f"{'Operation':42} {'Calls':>7} {'Total ms':>13} {'Avg ms':>12} {'Max ms':>12}",
            "-" * 91,
        ]

        aggregate = []
        for name, values in grouped.items():
            total = sum(values)
            aggregate.append((total, name, len(values), total / len(values), max(values)))
        for total, name, calls, avg, maximum in sorted(aggregate, reverse=True):
            lines.append(
                f"{name[:42]:42} {calls:7,d} {total:13.3f} {avg:12.3f} {maximum:12.3f}"
            )

        lines.extend(
            [
                "",
                "Slowest individual events",
                "-------------------------",
                f"{'Duration ms':>13}  {'Operation':38}  Details",
                "-" * 100,
            ]
        )
        for event in sorted(events, key=lambda item: item.duration_ms, reverse=True)[:50]:
            detail_text = ", ".join(
                f"{key}={value}" for key, value in event.details.items()
            )
            lines.append(
                f"{event.duration_ms:13.3f}  {event.name[:38]:38}  {detail_text}"
            )

        lines.extend(
            [
                "",
                "Interpretation hints",
                "--------------------",
                "- action.scan_to_main_ui: scan request to completion of the main synchronous UI rebuild.",
                "- scan.save: worker-thread save parsing/scanning time.",
                "- scan.livery_sha256: time spent hashing C_livery payloads for duplicate detection.",
                "- ui.*: PySide6 table/grid/filter/thumbnail work on the GUI thread.",
                "- v132.auction_thumbnail_assign: CacheThumbnails manifest matching work.",
                "",
            ]
        )
        return "\n".join(lines)


RECORDER = PerformanceRecorder()
