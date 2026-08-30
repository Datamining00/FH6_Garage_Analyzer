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

    def test_recent_changes_move_next_to_livery_filter_and_stay_visible(self):
        text = Path("fh6garage/v1_4_ui_completion_patch.py").read_text(encoding="utf-8")
        self.assertIn("search_row.indexOf(filter_button)", text)
        self.assertIn("insertWidget(index + 1", text)
        self.assertIn("banner.show()", text)
        self.assertIn("return 0, 0, 0", text)
        self.assertIn("최근 변동", text)

    def test_completion_layer_is_before_profiler(self):
        text = Path("fh6garage/v1_3_4_backup_action_wording_patch.py").read_text(encoding="utf-8")
        ui = text.index("apply_v1_4_ui_completion_patch(MainWindow)")
        perf = text.index("apply_v1_3_4_performance_probe_patch(MainWindow)")
        self.assertLess(ui, perf)


if __name__ == "__main__":
    unittest.main()
