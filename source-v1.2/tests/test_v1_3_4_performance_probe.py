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
            events = metrics.recent_events(5)
            assert [event.name for event in events][-2:] == ["startup.unit", "startup.total"]
            assert events[-2].item_count == 3
            assert events[-1].detail == "unit complete"
            assert metrics.log_path().is_file()
    finally:
        metrics.set_enabled(False)
        if previous is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = previous


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
        "ui.livery_relayout.add_widgets",
        "ui.livery_relayout.width_sync",
    ):
        assert marker in probe
