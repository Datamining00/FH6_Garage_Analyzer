from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

from fh6garage import performance_metrics as metrics


def test_profiler_disabled_fast_path_records_nothing() -> None:
    metrics.clear_recent(clear_file=False)
    metrics.set_enabled(False)
    with metrics.measure("disabled.test"):
        pass
    assert metrics.recent_events() == []


def test_profiler_records_elapsed_and_metadata() -> None:
    metrics.clear_recent(clear_file=False)
    metrics.set_enabled(True)
    with metrics.measure("enabled.test", item_count=7, byte_count=11, detail="unit"):
        time.sleep(0.001)
    event = metrics.recent_events(1)[0]
    assert event.name == "enabled.test"
    assert event.elapsed_ms >= 0
    assert event.item_count == 7
    assert event.byte_count == 11
    assert event.detail == "unit"
    metrics.set_enabled(False)


def test_profiler_jsonl_uses_localappdata() -> None:
    previous = os.environ.get("LOCALAPPDATA")
    try:
        with tempfile.TemporaryDirectory() as temp:
            os.environ["LOCALAPPDATA"] = temp
            metrics.clear_recent(clear_file=True)
            metrics.set_enabled(True)
            metrics.record("file.test", 1.25)
            path = metrics.log_path()
            assert path.is_file()
            assert Path(temp) in path.parents
            assert '"name":"file.test"' in path.read_text(encoding="utf-8")
    finally:
        metrics.set_enabled(False)
        if previous is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = previous


def test_startup_records_even_when_runtime_profiler_is_disabled() -> None:
    previous = os.environ.get("LOCALAPPDATA")
    try:
        with tempfile.TemporaryDirectory() as temp:
            os.environ["LOCALAPPDATA"] = temp
            metrics.clear_recent(clear_file=True)
            metrics.set_enabled(False)
            metrics.begin_startup(time.perf_counter_ns())
            with metrics.measure_startup("startup.unit", item_count=3):
                time.sleep(0.001)
            metrics.finish_startup(detail="unit complete")
            startup = metrics.startup_events()
            assert [event.name for event in startup][-2:] == ["startup.unit", "startup.total"]
            assert startup[-2].item_count == 3
            assert startup[-1].detail == "unit complete"
            assert metrics.log_path().is_file()
    finally:
        metrics.set_enabled(False)
        if previous is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = previous


def test_startup_buffer_survives_runtime_rolling_buffer_churn() -> None:
    metrics.clear_recent(clear_file=False)
    metrics.set_enabled(False)
    metrics.begin_startup(time.perf_counter_ns())
    metrics.record_startup("startup.marker", 12.5)
    metrics.finish_startup()
    metrics.set_enabled(True)
    for index in range(350):
        metrics.record("runtime.noise", float(index % 3))
    assert any(event.name == "startup.marker" for event in metrics.startup_events())
    assert "startup.marker" in metrics.format_startup()
    metrics.set_enabled(False)


def test_aggregate_only_samples_do_not_consume_recent_event_slots() -> None:
    metrics.clear_recent(clear_file=False)
    metrics.set_enabled(True)
    for value in (1.0, 2.0, 5.0):
        metrics.add_sample("ui.livery_relayout.width_sync", value)
    assert metrics.recent_events() == []
    rows = {row["name"]: row for row in metrics.aggregate_recent()}
    row = rows["ui.livery_relayout.width_sync"]
    assert row["count"] == 3
    assert row["total_ms"] == 8.0
    assert row["avg_ms"] == 2.667
    assert row["max_ms"] == 5.0
    metrics.set_enabled(False)


def test_performance_probe_is_installed_after_backup_layers() -> None:
    source = Path(__file__).parents[1] / "fh6garage" / "v1_3_4_backup_action_wording_patch.py"
    text = source.read_text(encoding="utf-8")
    assert "apply_v1_3_4_performance_probe_patch" in text
    assert text.index("apply_v1_3_4_livery_backup_filter_patch(MainWindow)") < text.index(
        "apply_v1_3_4_performance_probe_patch(MainWindow)"
    )


def test_startup_probe_covers_process_entry_scan_and_first_ready_state() -> None:
    root = Path(__file__).parents[1]
    app = (root / "app.py").read_text(encoding="utf-8")
    probe = (root / "fh6garage" / "v1_3_4_performance_probe_patch.py").read_text(encoding="utf-8")

    assert "_APP_ENTRY_NS = time.perf_counter_ns()" in app
    assert "begin_startup(_APP_ENTRY_NS)" in app
    assert 'record_startup("startup.qapplication"' in app
    assert 'record_startup("startup.settings"' in app
    assert 'record_startup("startup.patch_install"' in app
    assert 'record_startup("startup.mainwindow_init"' in app
    assert '"startup.first_window_render"' in app
    assert "set_startup_waiting_for_scan(wait_for_scan)" in app

    assert 'startup_name="startup.scan"' in probe
    assert 'startup_name="startup.initial_populate"' in probe
    assert '"startup.ready_after_scan_render"' in probe


def test_livery_relayout_and_populate_are_split_into_diagnostic_phases() -> None:
    root = Path(__file__).parents[1]
    probe = (root / "fh6garage" / "v1_3_4_performance_probe_patch.py").read_text(encoding="utf-8")
    for marker in (
        "ui.populate.car_table",
        "ui.populate.creator_table",
        "ui.populate.livery",
        "ui.populate.tuning",
        "ui.populate.db_status",
        "ui.livery_relayout.total",
        "ui.livery_relayout.clear_layout",
        "ui.livery_relayout.layout_visible",
        "ui.livery_relayout.visibility",
        "ui.livery_relayout.filter_match",
        "ui.livery_relayout.process_events",
        "ui.livery_relayout.width_sync",
        "ui.livery_relayout.unaccounted",
    ):
        assert marker in probe


def test_backup_diagnostics_cover_match_sort_and_card_build_paths() -> None:
    root = Path(__file__).parents[1]
    probe = (root / "fh6garage" / "v1_3_4_performance_probe_patch.py").read_text(encoding="utf-8")
    for marker in (
        "backup.match.game_index",
        "backup.match.repository_records",
        "backup.match.entry_compare",
        "backup.sort_key",
        "backup.build_items",
        "backup.rebuild_request",
        "backup.card_configure",
        "backup.card_factory",
    ):
        assert marker in probe


def test_performance_page_has_pinned_startup_and_aggregate_sections() -> None:
    root = Path(__file__).parents[1]
    probe = (root / "fh6garage" / "v1_3_4_performance_probe_patch.py").read_text(encoding="utf-8")
    assert "performance_startup_view" in probe
    assert "performance_summary_view" in probe
    assert "format_startup()" in probe
    assert "format_aggregate(300" in probe
