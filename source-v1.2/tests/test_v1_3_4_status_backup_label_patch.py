from __future__ import annotations

import inspect
import unittest

from fh6garage import v1_3_4_backup_action_wording_patch as action_patch
from fh6garage import v1_3_4_status_backup_label_patch as patch


class StatusBackupLabelPatchTests(unittest.TestCase):
    def test_requested_korean_labels_are_exact(self) -> None:
        source = inspect.getsource(patch)
        self.assertIn("현재 미적용 · 동일 차량에 다른 리버리가 적용 중", source)
        self.assertIn("적용된 리버리 없음", source)
        self.assertIn("백업 폴더에만 존재", source)
        self.assertIn("게임 및 백업에 존재", source)

    def test_gray_only_filter_uses_paint_state(self) -> None:
        source = inspect.getsource(patch.apply_v1_3_4_status_backup_label_patch)
        self.assertIn('FILTER_NO_APPLIED_FOR_CAR', source)
        self.assertIn('_memory._paint_state_for_record(window, record) == "unapplied"', source)

    def test_new_toggle_is_inserted_after_unapplied_toggle(self) -> None:
        source = inspect.getsource(patch._install_no_applied_toggle)
        self.assertIn('row.indexOf(unapplied)', source)
        self.assertIn('index + 1', source)
        self.assertIn('livery_no_applied_toggle', source)

    def test_backup_heading_is_removed_without_touching_sidebar_navigation(self) -> None:
        source = inspect.getsource(patch._remove_backup_page_heading)
        self.assertIn('root.takeAt(0)', source)
        self.assertIn('_hide_layout_tree', source)
        self.assertNotIn('backup_nav_button', source)

    def test_patch_is_installed_by_final_backup_chain(self) -> None:
        source = inspect.getsource(action_patch.apply_v1_3_4_backup_action_wording_patch)
        self.assertIn('apply_v1_3_4_status_backup_label_patch(MainWindow)', source)
        self.assertLess(
            source.index('apply_v1_3_4_livery_backup_filter_patch(MainWindow)'),
            source.index('apply_v1_3_4_status_backup_label_patch(MainWindow)'),
        )
        self.assertLess(
            source.index('apply_v1_3_4_status_backup_label_patch(MainWindow)'),
            source.index('apply_v1_3_4_performance_probe_patch(MainWindow)'),
        )


if __name__ == "__main__":
    unittest.main()
