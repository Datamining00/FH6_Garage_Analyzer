from __future__ import annotations

import unittest
from pathlib import Path


class BackupActionWordingTests(unittest.TestCase):
    def test_backup_tab_uses_backup_wording(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (
            root / "fh6garage" / "v1_3_4_backup_action_wording_patch.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"백업하기"', source)
        self.assertIn("게임 쪽 원본", source)
        self.assertNotIn("delete.setEnabled(False)", source)
        self.assertIn("_fh6_export_delete_source_requested", source)
        self.assertIn("폴더 지문", source)

    def test_wording_patch_stays_before_final_thread_affinity_fix(self) -> None:
        root = Path(__file__).resolve().parents[1]
        app = (root / "app.py").read_text(encoding="utf-8")
        performance = app.index(
            "apply_v1_3_4_backup_export_performance_ui_patch(MainWindow)"
        )
        wording = app.index("apply_v1_3_4_backup_action_wording_patch(MainWindow)")
        affinity = app.index("apply_v1_3_2_thread_affinity_fix(MainWindow)")
        self.assertLess(performance, wording)
        self.assertLess(wording, affinity)


if __name__ == "__main__":
    unittest.main()
