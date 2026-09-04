from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "fh6garage"


def _read(name: str) -> str:
    return (PACKAGE / name).read_text(encoding="utf-8")


def test_v1_4_rc1_identity_is_explicit_and_consistent() -> None:
    source = _read("v1_4_identity_patch.py")
    assert 'VERSION_TEXT = "v1.4 RC1"' in source
    assert 'APP_VERSION = "1.4-rc1"' in source
    assert 'WINDOW_TITLE = "FH6 Assistant v1.4 RC1"' in source
    assert "app.setApplicationVersion(APP_VERSION)" in source


def test_performance_snapshot_uses_rc1_version() -> None:
    source = _read("v1_3_2_performance_profiler.py")
    assert '"app_version": "1.4-rc1"' in source
    assert '"app_version": "1.3.2"' not in source
