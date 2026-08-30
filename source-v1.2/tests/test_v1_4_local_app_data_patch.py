from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fh6garage import v1_3_4_backup_lazy_watch_patch as watch_patch
from fh6garage import v1_4_backup_repository_patch as repository_patch
from fh6garage.v1_4_local_app_data_patch import default_backup_root


class V14LocalAppDataTests(unittest.TestCase):
    def test_default_backup_root_uses_established_fh6garageanalyzer_root(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.dict(os.environ, {"LOCALAPPDATA": td}, clear=False):
                expected = Path(td) / "FH6GarageAnalyzer" / "backup"
                self.assertEqual(default_backup_root(), expected)

    def test_qstandardpaths_is_not_used_by_completion_layer(self):
        text = Path("fh6garage/v1_4_local_app_data_patch.py").read_text(encoding="utf-8")
        repository = Path("fh6garage/v1_4_backup_repository_patch.py").read_text(encoding="utf-8")
        self.assertNotIn("QStandardPaths", text)
        self.assertNotIn("QStandardPaths", repository)
        self.assertIn('app_data_dir() / "backup"', text)
        self.assertIn('app_data_dir() / "backup"', repository)

    def test_completion_layer_replaces_repository_default_resolver(self):
        text = Path("fh6garage/v1_4_local_app_data_patch.py").read_text(encoding="utf-8")
        self.assertIn("_repository._default_backup_root = default_backup_root", text)

    def test_watcher_uses_active_backup_repository_and_index(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "custom-backup"
            root.mkdir()
            index = root / watch_patch.INDEX_NAME
            index.write_text("{}", encoding="utf-8")
            with patch.object(watch_patch._backup_ui, "_backup_root", return_value=root):
                paths = watch_patch._watch_paths(object())
            self.assertEqual(paths[0], str(root.resolve()))
            self.assertEqual(paths[1], str(index.resolve()))

    def test_watcher_path_edit_reconfigures_active_repository(self):
        text = Path("fh6garage/v1_3_4_backup_lazy_watch_patch.py").read_text(encoding="utf-8")
        self.assertIn("root = _backup_ui._backup_root(window)", text)
        self.assertIn("path_edit.textChanged.connect", text)
        self.assertIn("_configure_watcher(owner)", text)

    def test_repository_default_and_local_appdata_default_match(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.dict(os.environ, {"LOCALAPPDATA": td}, clear=False):
                self.assertEqual(repository_patch._default_backup_root(), default_backup_root())

    def test_completion_layers_run_before_performance_probe(self):
        text = Path("fh6garage/v1_3_4_backup_action_wording_patch.py").read_text(encoding="utf-8")
        local_pos = text.index("apply_v1_4_local_app_data_patch(MainWindow)")
        acquisition_pos = text.index("apply_v1_4_acquisition_ui_patch(MainWindow)")
        perf_pos = text.index("apply_v1_3_4_performance_probe_patch(MainWindow)")
        self.assertLess(local_pos, perf_pos)
        self.assertLess(acquisition_pos, perf_pos)


if __name__ == "__main__":
    unittest.main()
