from __future__ import annotations

from pathlib import Path


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
