from __future__ import annotations

import unittest
from pathlib import Path

from fh6garage import v1_3_4_backup_export_patch as backup_ui
from fh6garage import v1_3_4_backup_loading_resilience_patch as resilience
from fh6garage import v1_3_4_backup_visual_stability_patch as stability


class _FakeWidget:
    def __init__(self) -> None:
        self.enabled_calls: list[bool] = []
        self.update_calls = 0

    def setUpdatesEnabled(self, enabled: bool) -> None:
        self.enabled_calls.append(bool(enabled))

    def update(self) -> None:
        self.update_calls += 1


class _FakeScroll(_FakeWidget):
    def __init__(self, viewport: _FakeWidget) -> None:
        super().__init__()
        self._viewport = viewport

    def viewport(self) -> _FakeWidget:
        return self._viewport


class _FakeWindow:
    def __init__(self) -> None:
        self.viewport = _FakeWidget()
        self.backup_grid_scroll = _FakeScroll(self.viewport)
        self.backup_grid_host = _FakeWidget()
        self._fh6_backup_relayout_active = False
        self._fh6_backup_relayout_generation = 1


class BackupVisualStabilityTests(unittest.TestCase):
    def test_grid_updates_freeze_and_thaw_all_backup_surfaces(self) -> None:
        window = _FakeWindow()
        stability._set_backup_grid_updates(window, False)
        self.assertEqual(window.backup_grid_scroll.enabled_calls, [False])
        self.assertEqual(window.viewport.enabled_calls, [False])
        self.assertEqual(window.backup_grid_host.enabled_calls, [False])

        stability._set_backup_grid_updates(window, True)
        self.assertEqual(window.backup_grid_scroll.enabled_calls, [False, True])
        self.assertEqual(window.viewport.enabled_calls, [False, True])
        self.assertEqual(window.backup_grid_host.enabled_calls, [False, True])
        self.assertEqual(window.backup_grid_scroll.update_calls, 1)
        self.assertEqual(window.viewport.update_calls, 1)
        self.assertEqual(window.backup_grid_host.update_calls, 1)

    def test_patch_replaces_visible_relayout_after_resilience(self) -> None:
        class MainWindow:
            pass

        old_finish = resilience._finish_relayout
        old_relayout = backup_ui._relayout_backup
        try:
            stability.apply_v1_3_4_backup_visual_stability_patch(MainWindow)
            self.assertIs(resilience._finish_relayout, stability._finish_relayout_without_jitter)
            self.assertIs(backup_ui._relayout_backup, stability._relayout_without_jitter)
        finally:
            resilience._finish_relayout = old_finish
            backup_ui._relayout_backup = old_relayout

    def test_patch_order_is_resilience_then_visual_stability_then_profiler(self) -> None:
        root = Path(__file__).resolve().parents[1]
        wording = (root / "fh6garage" / "v1_3_4_backup_action_wording_patch.py").read_text(encoding="utf-8")
        source = (root / "fh6garage" / "v1_3_4_backup_visual_stability_patch.py").read_text(encoding="utf-8")

        self.assertLess(
            wording.index("apply_v1_3_4_backup_loading_resilience_patch(MainWindow)"),
            wording.index("apply_v1_3_4_backup_visual_stability_patch(MainWindow)"),
        )
        self.assertLess(
            wording.index("apply_v1_3_4_backup_visual_stability_patch(MainWindow)"),
            wording.index("apply_v1_3_4_performance_probe_patch(MainWindow)"),
        )
        self.assertIn("setUpdatesEnabled", source)
        self.assertNotIn("processEvents", source)


if __name__ == "__main__":
    unittest.main()
