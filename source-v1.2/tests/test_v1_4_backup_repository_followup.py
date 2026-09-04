from __future__ import annotations

import unittest
from pathlib import Path


class V14BackupRepositoryFollowupTests(unittest.TestCase):
    def test_followup_blocks_overlapping_backup_operations(self):
        text = Path("fh6garage/v1_4_backup_repository_followup_patch.py").read_text(encoding="utf-8")
        self.assertIn('_fh6_backup_load_running', text)
        self.assertIn('_fh6_export_running', text)
        self.assertIn('_fh6_import_running', text)
        self.assertIn('_fh6_external_import_running', text)
        self.assertIn('_watch._refresh_external_change = refresh_external_change', text)
        self.assertIn('_lazy._backup_controls = backup_controls', text)

    def test_v14_layer_is_installed_before_final_performance_layer(self):
        text = Path("fh6garage/v1_3_4_backup_action_wording_patch.py").read_text(encoding="utf-8")
        base = text.index("apply_v1_4_backup_repository_patch(MainWindow)")
        followup = text.index("apply_v1_4_backup_repository_followup_patch(MainWindow)")
        identity = text.index("apply_v1_4_identity_patch(MainWindow)")
        perf = text.index("apply_v1_3_4_performance_probe_patch(MainWindow)")
        self.assertLess(base, followup)
        self.assertLess(followup, identity)
        self.assertLess(identity, perf)


if __name__ == "__main__":
    unittest.main()
