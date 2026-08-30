from __future__ import annotations

import unittest
from pathlib import Path


class V14UiCompletionTests(unittest.TestCase):
    def test_locked_filter_is_livery_only(self):
        completion = Path("fh6garage/v1_4_ui_completion_patch.py").read_text(encoding="utf-8")
        backup = Path("fh6garage/v1_4_backup_repository_patch.py").read_text(encoding="utf-8")
        self.assertIn("livery_check_filter", completion)
        self.assertIn("잠금된 리버리", completion)
        self.assertIn("_LOCKED_LIVERY_FILTER_MODE = 15", completion)
        self.assertIn("_remove_backup_locked_filter", completion)
        self.assertIn("backup_locked_filter_action", backup)

    def test_recent_changes_move_to_display_row_and_stay_visible(self):
        text = Path("fh6garage/v1_4_ui_completion_patch.py").read_text(encoding="utf-8")
        self.assertIn("controls.itemAt(1)", text)
        self.assertIn("display_row.addWidget(banner, 1", text)
        self.assertNotIn("search_row.indexOf(filter_button)", text)
        self.assertIn("banner.show()", text)
        self.assertIn("return 0, 0, 0", text)

    def test_recent_change_button_uses_plain_colored_numbers(self):
        text = Path("fh6garage/v1_4_ui_completion_patch.py").read_text(encoding="utf-8")
        self.assertIn('_RECENT_ADDED_COLOR = "#39e75f"', text)
        self.assertIn('_RECENT_REMOVED_COLOR = "#ff4d5a"', text)
        self.assertIn('_RECENT_DUPLICATE_COLOR = "#ffe600"', text)
        self.assertIn('label = QLabel("0", view)', text)
        self.assertIn('labels[0].setText(str(added))', text)
        self.assertIn('labels[1].setText(str(removed))', text)
        self.assertIn('labels[2].setText(str(duplicate))', text)
        self.assertNotIn('view.setText(f"+{added}', text)

    def test_completion_layer_is_before_profiler(self):
        text = Path("fh6garage/v1_3_4_backup_action_wording_patch.py").read_text(encoding="utf-8")
        ui = text.index("apply_v1_4_ui_completion_patch(MainWindow)")
        perf = text.index("apply_v1_3_4_performance_probe_patch(MainWindow)")
        self.assertLess(ui, perf)


if __name__ == "__main__":
    unittest.main()
