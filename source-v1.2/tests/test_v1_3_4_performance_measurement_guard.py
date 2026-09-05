from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from fh6garage.performance_measurement_guard import install_performance_measurement_guard


@dataclass
class _Event:
    timestamp: str
    name: str
    elapsed_ms: float
    thread: str
    item_count: int | None = None
    byte_count: int | None = None
    detail: str = ""


class _FakeMetrics:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.events: list[_Event] = []
        self.active = False

    def _event(self, name: str, elapsed_ms: float, **kwargs):
        return _Event("now", name, elapsed_ms, threading.current_thread().name, **kwargs)

    def _write_event(self, event: _Event) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.__dict__) + "\n")

    def _rotate(self, _path: Path) -> None:
        return None

    def log_path(self) -> Path:
        return self.path

    def record(self, name: str, elapsed_ms: float, **kwargs) -> None:
        event = self._event(name, elapsed_ms, **kwargs)
        self.events.append(event)
        self._write_event(event)

    def record_startup(self, name: str, elapsed_ms: float, **kwargs) -> None:
        self.record(name, elapsed_ms, **kwargs)

    def add_sample(self, _name: str, _elapsed_ms: float) -> None:
        return None

    def begin_startup(self, *_args, **_kwargs) -> None:
        self.active = True
        self.events.clear()

    def finish_startup(self, **_kwargs) -> None:
        if self.active:
            self.record_startup("startup.total", 100.0)
            self.active = False

    def startup_events(self):
        return list(self.events)

    def format_startup(self) -> str:
        return ""

    def clear_recent(self, *_args, **_kwargs) -> None:
        self.events.clear()


def test_measurement_guard_buffers_file_io_and_reports_uncertainty() -> None:
    root = Path(__file__).parents[1] / "fh6garage"
    guard = (root / "performance_measurement_guard.py").read_text(encoding="utf-8")

    assert "def buffered_write_event" in guard
    assert "pending.append(event)" in guard
    assert "def flush_log" in guard
    assert "handle.write(payload)" in guard
    assert "startup.total closes before disk flush" in guard
    assert "collector in-path" in guard
    assert "미분해 시간" in guard
    assert "중첩/중복 계측 가능" in guard
    assert "단독으로 원인을 증명하지 않음" in guard
    assert "UI ready 경계 정의" in guard
    assert '"startup.measurement_guard"' in guard
    assert "persist_startup_diagnostics()" in guard
    for field in (
        "collector_in_path_ms",
        "collector_ratio_pct",
        "collector_record_calls",
        "collector_sample_calls",
        "flush_after_ready_ms",
        "populate_child_sum_ms",
        "populate_gap_ms",
    ):
        assert field in guard


def test_measurement_guard_persists_self_contained_startup_diagnostics(tmp_path: Path) -> None:
    metrics = _FakeMetrics(tmp_path / "performance.jsonl")
    install_performance_measurement_guard(metrics)
    metrics.begin_startup(time.perf_counter_ns())
    metrics.record_startup("startup.initial_populate", 80.0)
    metrics.record_startup("startup.populate.child_nonoverlap_sum", 50.0)
    metrics.finish_startup()

    rows = [json.loads(line) for line in metrics.path.read_text(encoding="utf-8").splitlines()]
    diagnostic = next(row for row in rows if row["name"] == "startup.measurement_guard")
    detail = json.loads(diagnostic["detail"])
    assert detail["startup_total_ms"] == 100.0
    assert detail["populate_child_sum_ms"] == 50.0
    assert detail["populate_gap_ms"] == 30.0
    assert detail["collector_record_calls"] >= 3
    assert detail["collector_sample_calls"] == 0
    assert detail["flush_after_ready_ms"] >= 0.0


def test_measurement_guard_installs_before_runtime_probe_is_applied() -> None:
    source = (
        Path(__file__).parents[1]
        / "fh6garage"
        / "v1_3_4_backup_action_wording_patch.py"
    ).read_text(encoding="utf-8")

    assert "install_performance_measurement_guard(_performance_metrics)" in source
    assert source.index("install_performance_measurement_guard(_performance_metrics)") < source.index(
        "def apply_v1_3_4_backup_action_wording_patch"
    )
    assert source.index("apply_v1_3_4_livery_backup_filter_patch(MainWindow)") < source.index(
        "apply_v1_3_4_performance_probe_patch(MainWindow)"
    )


def test_measurement_guard_keeps_startup_and_runtime_controls_separate() -> None:
    guard = (
        Path(__file__).parents[1] / "fh6garage" / "performance_measurement_guard.py"
    ).read_text(encoding="utf-8")
    probe = (
        Path(__file__).parents[1] / "fh6garage" / "v1_3_4_performance_probe_patch.py"
    ).read_text(encoding="utf-8")

    assert "original_begin_startup" in guard
    assert "original_finish_startup" in guard
    assert "metrics.finish_startup = guarded_finish_startup" in guard
    assert "performance_profiling_enabled" in probe
    assert "초기 실행은 매번 자동 측정" in probe
