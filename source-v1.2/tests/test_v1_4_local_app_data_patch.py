from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fh6garage.v1_4_local_app_data_patch import default_backup_root


class V14LocalAppDataTests(unittest.TestCase):
    def test_default_backup_root_uses_established_fh6garageanalyzer_root(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.dict(os.environ, {"LOCALAPPDATA": td}, clear=False):
                expected = Path(td) / "FH6GarageAnalyzer" / "backup"
                self.assertEqual(default_backup_root(), expected)

    def test_qstandardpaths_is_not_used_by_completion_layer(self):
        text = Path("fh6garage/v1_4_local_app_data_patch.py").read_text(encoding="utf-8")
        self.assertNotIn("QStandardPaths", text)
        self.assertIn('app_data_dir() / "backup"', text)

    def test_completion_layers_run_before_performance_probe(self):
        text = Path("fh6garage/v1_3_4_backup_action_wording_patch.py").read_text(encoding="utf-8")
        local_pos = text.index("apply_v1_4_local_app_data_patch(MainWindow)")
        acquisition_pos = text.index("apply_v1_4_acquisition_ui_patch(MainWindow)")
        perf_pos = text.index("apply_v1_3_4_performance_probe_patch(MainWindow)")
        self.assertLess(local_pos, perf_pos)
        self.assertLess(acquisition_pos, perf_pos)


if __name__ == "__main__":
    unittest.main()
