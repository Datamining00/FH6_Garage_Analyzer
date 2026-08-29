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


def test_performance_probe_is_installed_after_backup_layers() -> None:
    source = Path(__file__).parents[1] / "fh6garage" / "v1_3_4_backup_action_wording_patch.py"
    text = source.read_text(encoding="utf-8")
    assert "apply_v1_3_4_performance_probe_patch" in text
    assert text.index("apply_v1_3_4_livery_backup_filter_patch(MainWindow)") < text.index(
        "apply_v1_3_4_performance_probe_patch(MainWindow)"
    )
