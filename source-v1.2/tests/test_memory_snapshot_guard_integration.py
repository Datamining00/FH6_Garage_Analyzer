from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from fh6garage.memory_applied_state import MemoryScanResult, PersistedAppliedState
from fh6garage.v1_3_2_memory_filter_coordination_patch import _snapshot_drop_diagnostic


ROOT = Path(__file__).resolve().parents[1]


def _names(count: int) -> frozenset[str]:
    return frozenset(f"Livery_{1000 + index}_{20260801000000 + index:014d}" for index in range(count))


class MemorySnapshotGuardIntegrationTests(unittest.TestCase):
    def test_previous_valid_state_is_compared_with_new_usable_result(self) -> None:
        window = SimpleNamespace(
            _fh6_memory_state=PersistedAppliedState(
                scanned_at="2026-08-31 21:00:00",
                pid=1234,
                consensus_status="HIGH",
                active_livery_names=_names(327),
            )
        )
        result = MemoryScanResult(
            pid=1234,
            status="HIGH",
            active_livery_names=_names(150),
        )
        diagnostic = _snapshot_drop_diagnostic(window, result)
        self.assertIsNotNone(diagnostic)
        assert diagnostic is not None
        self.assertEqual(diagnostic.previous_count, 327)
        self.assertEqual(diagnostic.current_count, 150)

    def test_normal_one_livery_change_passes_without_diagnostic(self) -> None:
        window = SimpleNamespace(
            _fh6_memory_state=PersistedAppliedState(
                scanned_at="2026-08-31 21:00:00",
                pid=1234,
                consensus_status="HIGH",
                active_livery_names=_names(327),
            )
        )
        result = MemoryScanResult(
            pid=1234,
            status="HIGH",
            active_livery_names=_names(326),
        )
        self.assertIsNone(_snapshot_drop_diagnostic(window, result))

    def test_unusable_new_result_is_left_to_existing_failure_path(self) -> None:
        window = SimpleNamespace(
            _fh6_memory_state=PersistedAppliedState(
                scanned_at="2026-08-31 21:00:00",
                pid=1234,
                consensus_status="HIGH",
                active_livery_names=_names(327),
            )
        )
        result = MemoryScanResult(
            pid=1234,
            status="AMBIGUOUS",
            active_livery_names=_names(10),
        )
        self.assertIsNone(_snapshot_drop_diagnostic(window, result))

    def test_guard_is_installed_before_memory_thread_bridge(self) -> None:
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        coordination = app.index("apply_v1_3_2_memory_filter_coordination_patch(MainWindow)")
        bridge = app.index("apply_v1_3_2_memory_thread_safety_patch(MainWindow)")
        self.assertLess(coordination, bridge)

        source = (
            ROOT / "fh6garage" / "v1_3_2_memory_filter_coordination_patch.py"
        ).read_text(encoding="utf-8")
        bridge_source = (
            ROOT / "fh6garage" / "v1_3_2_memory_thread_safety_patch.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("_memory_state._on_memory_finished =", source)
        self.assertIn("MainWindow._fh6_memory_result_guard = _guard_memory_result", source)
        self.assertIn('getattr(self.window, "_fh6_memory_result_guard", None)', bridge_source)
        self.assertIn("_memory_ui._on_memory_finished(self.window, result)", bridge_source)
        self.assertIn("QMessageBox.StandardButton.No", source)


if __name__ == "__main__":
    unittest.main()
