from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RefreshStateRetentionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ui = (ROOT / "fh6garage" / "ui.py").read_text(encoding="utf-8")
        cls.memory = (
            ROOT / "fh6garage" / "v1_3_2_memory_state_patch.py"
        ).read_text(encoding="utf-8")
        cls.coordination = (
            ROOT / "fh6garage" / "v1_3_2_memory_filter_coordination_patch.py"
        ).read_text(encoding="utf-8")

    def test_full_refresh_does_not_reset_user_view_controls(self) -> None:
        refresh = self.ui.split("def refresh_scan", 1)[1].split("def start_scan", 1)[0]
        for forbidden in (
            "livery_search.clear",
            "tuning_search.clear",
            "_livery_sort_mode =",
            "_tuning_sort_mode =",
            "_livery_sort_descending =",
            "_tuning_sort_descending =",
            "group_button.setChecked",
            "creator_group_button.setChecked",
            "verticalScrollBar().setValue(0)",
        ):
            self.assertNotIn(forbidden, refresh)
        self.assertIn("self.car_db.reload()", refresh)
        self.assertIn("self.start_scan(Path(self.path_edit.text()))", refresh)

    def test_scan_completion_keeps_search_sort_group_and_scroll_state(self) -> None:
        finished = self.ui.split("def _scan_finished", 1)[1].split("def _scan_failed", 1)[0]
        self.assertIn("self.result = result", finished)
        self.assertIn("self._populate_all()", finished)
        for forbidden in (
            "livery_search.clear",
            "tuning_search.clear",
            "_livery_sort_mode =",
            "_tuning_sort_mode =",
            "group_button.setChecked",
            "creator_group_button.setChecked",
            "verticalScrollBar().setValue(0)",
        ):
            self.assertNotIn(forbidden, finished)

    def test_group_preferences_are_persisted_and_mutually_exclusive(self) -> None:
        vehicle = self.ui.split("def _set_vehicle_grouping", 1)[1].split(
            "@Slot(str, bool)\n    def _set_creator_grouping", 1
        )[0]
        creator = self.ui.split("def _set_creator_grouping", 1)[1].split(
            "@Slot()\n    def choose_save_folder", 1
        )[0]
        self.assertIn('f"{content_type}_group_by_vehicle"', vehicle)
        self.assertIn("self.local_preferences.set_bool", vehicle)
        self.assertIn('f"{content_type}_group_by_creator"', creator)
        self.assertIn("self.local_preferences.set_bool", creator)
        self.assertIn("other.setChecked(False)", vehicle)
        self.assertIn("other.setChecked(False)", creator)

    def test_sort_state_survives_refresh_but_sort_action_intentionally_resets_scroll(self) -> None:
        sorter = self.ui.split("def _set_saved_content_sort_mode", 1)[1].split(
            "def _update_sort_button_labels", 1
        )[0]
        self.assertIn("self._livery_sort_mode = mode", sorter)
        self.assertIn("self._tuning_sort_mode = mode", sorter)
        self.assertIn("self.livery_grid_scroll.verticalScrollBar().setValue(0)", sorter)
        self.assertIn("self.tuning_grid_scroll.verticalScrollBar().setValue(0)", sorter)

    def test_unusable_or_rejected_memory_result_keeps_last_good_state(self) -> None:
        finish = self.memory.split("def _on_memory_finished", 1)[1].split(
            "def _on_memory_failed", 1
        )[0]
        assignment = finish.index("window._fh6_memory_state = state")
        unusable = finish.index("if not result.usable:")
        rejected = finish.index("if answer != QMessageBox.StandardButton.Yes:")
        self.assertLess(unusable, assignment)
        self.assertLess(rejected, assignment)
        self.assertIn("마지막 정상 스캔 결과를 유지합니다", finish)
        self.assertIn("마지막 정상 적용 결과를 유지합니다", finish)

    def test_suspicious_snapshot_guard_runs_before_state_replacement(self) -> None:
        guard = self.coordination.split("def _guard_memory_result", 1)[1].split(
            "def _clear_legacy_auction_state_filter", 1
        )[0]
        self.assertIn("_snapshot_drop_diagnostic(window, result)", guard)
        self.assertNotIn("window._fh6_memory_state =", guard)
        confirm = self.coordination.split("def _confirm_suspicious_snapshot_drop", 1)[1].split(
            "def _guard_memory_result", 1
        )[0]
        self.assertIn("QMessageBox.StandardButton.No", confirm)


if __name__ == "__main__":
    unittest.main()
