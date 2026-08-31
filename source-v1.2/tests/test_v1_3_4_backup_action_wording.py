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

    def test_wording_patch_has_no_hidden_followup_install(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (
            root / "fh6garage" / "v1_3_4_backup_action_wording_patch.py"
        ).read_text(encoding="utf-8")
        wording_start = source.index("def apply_v1_3_4_backup_action_wording_patch")
        followup_start = source.index("def apply_v1_3_4_v1_4_followup_patches")
        wording_body = source[wording_start:followup_start]
        self.assertNotIn("apply_v1_3_4_backup_import_refinement_patch(MainWindow)", wording_body)
        self.assertNotIn("apply_v1_4_identity_patch(MainWindow)", wording_body)

    def test_followup_stack_keeps_verified_order(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (
            root / "fh6garage" / "v1_3_4_backup_action_wording_patch.py"
        ).read_text(encoding="utf-8")
        followup_start = source.index("def apply_v1_3_4_v1_4_followup_patches")
        followup = source[followup_start:]
        first = followup.index("apply_v1_3_4_backup_import_refinement_patch(MainWindow)")
        repository = followup.index("apply_v1_4_backup_repository_patch(MainWindow)")
        last = followup.index("apply_v1_3_4_performance_probe_patch(MainWindow)")
        self.assertLess(first, repository)
        self.assertLess(repository, last)

    def test_app_exposes_followup_boundary_before_final_thread_fix(self) -> None:
        root = Path(__file__).resolve().parents[1]
        app = (root / "app.py").read_text(encoding="utf-8")
        wording = app.index("apply_v1_3_4_backup_action_wording_patch(MainWindow)")
        followup = app.index("apply_v1_3_4_v1_4_followup_patches(MainWindow)")
        affinity = app.index("apply_v1_3_2_thread_affinity_fix(MainWindow)")
        self.assertLess(wording, followup)
        self.assertLess(followup, affinity)


if __name__ == "__main__":
    unittest.main()
