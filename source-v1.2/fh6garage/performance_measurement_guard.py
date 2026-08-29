from __future__ import annotations

import atexit
import json
import threading
import time
from dataclasses import asdict
from datetime import datetime
from typing import Any


_INSTALLED_ATTR = "_fh6_measurement_guard_installed"


def install_performance_measurement_guard(metrics: Any) -> None:
    """Reduce observer effect and expose uncertainty/coverage diagnostics.

    The existing profiler remains the source of timing events. This guard changes
    only collection/logging behavior: JSONL writes are buffered, collector
    overhead is measured, and the startup report explicitly distinguishes
    measured duration from causal interpretation.
    """
    if bool(getattr(metrics, _INSTALLED_ATTR, False)):
        return

    pending: list[Any] = []
    pending_lock = threading.RLock()
    stats_lock = threading.RLock()
    stats: dict[str, int] = {
        "record_ns": 0,
        "record_calls": 0,
        "sample_ns": 0,
        "sample_calls": 0,
        "flush_ns": 0,
        "flush_calls": 0,
        "flushed_events": 0,
    }
    last_startup_stats: dict[str, float | int | str] = {}

    original_write_event = metrics._write_event
    original_record = metrics.record
    original_record_startup = metrics.record_startup
    original_add_sample = metrics.add_sample
    original_begin_startup = metrics.begin_startup
    original_finish_startup = metrics.finish_startup
    original_format_startup = metrics.format_startup
    original_clear_recent = metrics.clear_recent

    def reset_stats() -> None:
        with stats_lock:
            for key in stats:
                stats[key] = 0
            last_startup_stats.clear()

    def buffered_write_event(event: Any) -> None:
        # No filesystem access on the measured path. A shallow event reference is
        # sufficient because PerfEvent is immutable in normal profiler use.
        with pending_lock:
            pending.append(event)

    def flush_log() -> float:
        started = time.perf_counter_ns()
        with pending_lock:
            if not pending:
                return 0.0
            batch = list(pending)
            pending.clear()

        path = metrics.log_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            metrics._rotate(path)
            payload = "".join(
                json.dumps(asdict(event), ensure_ascii=False, separators=(",", ":")) + "\n"
                for event in batch
            )
            with path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
        except OSError:
            # Preserve the events for a later retry instead of silently losing the
            # diagnostic session when storage is temporarily unavailable.
            with pending_lock:
                pending[0:0] = batch
        elapsed_ns = time.perf_counter_ns() - started
        with stats_lock:
            stats["flush_ns"] += elapsed_ns
            stats["flush_calls"] += 1
            stats["flushed_events"] += len(batch)
        return elapsed_ns / 1_000_000.0

    def timed_record(*args: Any, **kwargs: Any) -> None:
        started = time.perf_counter_ns()
        try:
            original_record(*args, **kwargs)
        finally:
            elapsed = time.perf_counter_ns() - started
            with stats_lock:
                stats["record_ns"] += elapsed
                stats["record_calls"] += 1

    def timed_record_startup(*args: Any, **kwargs: Any) -> None:
        started = time.perf_counter_ns()
        try:
            original_record_startup(*args, **kwargs)
        finally:
            elapsed = time.perf_counter_ns() - started
            with stats_lock:
                stats["record_ns"] += elapsed
                stats["record_calls"] += 1

    def timed_add_sample(*args: Any, **kwargs: Any) -> None:
        started = time.perf_counter_ns()
        try:
            original_add_sample(*args, **kwargs)
        finally:
            elapsed = time.perf_counter_ns() - started
            with stats_lock:
                stats["sample_ns"] += elapsed
                stats["sample_calls"] += 1

    def guarded_begin_startup(*args: Any, **kwargs: Any) -> None:
        reset_stats()
        with pending_lock:
            pending.clear()
        original_begin_startup(*args, **kwargs)

    def _last_elapsed(name: str) -> float | None:
        for event in reversed(metrics.startup_events()):
            if str(getattr(event, "name", "")) == name:
                return float(getattr(event, "elapsed_ms", 0.0) or 0.0)
        return None

    def _capture_startup_stats(flush_after_ready_ms: float) -> None:
        total = _last_elapsed("startup.total") or 0.0
        initial_populate = _last_elapsed("startup.initial_populate")
        child_names = (
            "startup.populate.car_table",
            "startup.populate.creator_table",
            "startup.populate.livery",
            "startup.populate.tuning",
            "startup.populate.db_status",
        )
        children = [value for name in child_names if (value := _last_elapsed(name)) is not None]
        child_sum = sum(children)
        populate_gap = None if initial_populate is None else initial_populate - child_sum

        with stats_lock:
            in_path_ms = (stats["record_ns"] + stats["sample_ns"]) / 1_000_000.0
            ratio = (in_path_ms / total * 100.0) if total > 0 else 0.0
            last_startup_stats.update(
                {
                    "startup_total_ms": total,
                    "collector_in_path_ms": in_path_ms,
                    "collector_ratio_pct": ratio,
                    "collector_record_calls": stats["record_calls"],
                    "collector_sample_calls": stats["sample_calls"],
                    "flush_after_ready_ms": flush_after_ready_ms,
                    "populate_child_sum_ms": child_sum,
                    "populate_gap_ms": populate_gap if populate_gap is not None else 0.0,
                    "populate_has_parent": int(initial_populate is not None),
                    "captured_at": datetime.now().isoformat(timespec="seconds"),
                }
            )

    def guarded_finish_startup(*args: Any, **kwargs: Any) -> None:
        original_finish_startup(*args, **kwargs)
        # startup.total closes before disk flush. This means JSON serialization and
        # file I/O cannot inflate the user-visible startup.total measurement.
        flush_ms = flush_log()
        _capture_startup_stats(flush_ms)

    def format_validation() -> str:
        with stats_lock:
            snapshot = dict(last_startup_stats)
            current_record_ms = (stats["record_ns"] + stats["sample_ns"]) / 1_000_000.0
            current_flush_ms = stats["flush_ns"] / 1_000_000.0

        if not snapshot:
            return (
                "측정 검증: startup 세션 완료 전\n"
                "주의: 각 타이밍은 구간의 경과시간이며 그 자체로 원인을 증명하지 않습니다."
            )

        total = float(snapshot.get("startup_total_ms", 0.0) or 0.0)
        in_path = float(snapshot.get("collector_in_path_ms", 0.0) or 0.0)
        ratio = float(snapshot.get("collector_ratio_pct", 0.0) or 0.0)
        flush_ms = float(snapshot.get("flush_after_ready_ms", 0.0) or 0.0)
        gap = float(snapshot.get("populate_gap_ms", 0.0) or 0.0)
        has_parent = bool(int(snapshot.get("populate_has_parent", 0) or 0))

        if ratio >= 5.0:
            confidence = "주의 · collector 오버헤드가 큼"
        elif ratio >= 1.0:
            confidence = "참고 · collector 오버헤드 확인 필요"
        else:
            confidence = "양호 · collector 자체 오버헤드는 낮음"

        lines = [
            f"측정 검증: {confidence}",
            f"startup.total: {total:.3f} ms",
            f"collector in-path: {in_path:.3f} ms ({ratio:.3f}%)",
            f"log flush after ready: {flush_ms:.3f} ms (startup.total에 포함되지 않음)",
            f"collector calls: record={int(snapshot.get('collector_record_calls', 0))}, sample={int(snapshot.get('collector_sample_calls', 0))}",
        ]
        if has_parent:
            if gap >= 0:
                lines.append(f"startup.initial_populate 미분해 시간: {gap:.3f} ms")
            else:
                lines.append(
                    f"startup.populate 하위 합계가 부모보다 {-gap:.3f} ms 큼 · 중첩/중복 계측 가능"
                )
        lines.extend(
            (
                "주의: 구간 시간은 '어디서 시간이 지났는지'를 나타내며 단독으로 원인을 증명하지 않음.",
                "주의: 중첩된 타이밍은 서로 합산하면 안 되며, UI ready 경계 정의가 체감 완료 시점과 다를 수 있음.",
                "주의: collector 오버헤드 수치는 기록/집계 bookkeeping만 포함하며 timer wrapper 자체의 극소 비용은 별도임.",
                f"현재 세션 누적 collector={current_record_ms:.3f} ms, log flush={current_flush_ms:.3f} ms",
            )
        )
        return "\n".join(lines)

    def guarded_format_startup() -> str:
        validation = format_validation()
        body = original_format_startup()
        if body:
            return f"[측정 검증]\n{validation}\n\n[Startup events]\n{body}"
        return f"[측정 검증]\n{validation}"

    def guarded_clear_recent(*args: Any, **kwargs: Any) -> None:
        original_clear_recent(*args, **kwargs)
        with pending_lock:
            pending.clear()
        reset_stats()

    metrics._write_event = buffered_write_event
    metrics.record = timed_record
    metrics.record_startup = timed_record_startup
    metrics.add_sample = timed_add_sample
    metrics.begin_startup = guarded_begin_startup
    metrics.finish_startup = guarded_finish_startup
    metrics.format_startup = guarded_format_startup
    metrics.clear_recent = guarded_clear_recent
    metrics.flush_log = flush_log
    metrics.format_validation = format_validation
    metrics._fh6_original_write_event = original_write_event
    setattr(metrics, _INSTALLED_ATTR, True)
    atexit.register(flush_log)
