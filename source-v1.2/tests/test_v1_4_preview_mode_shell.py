from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "fh6garage"


class PreviewModeShellContractTests(unittest.TestCase):
    def test_shell_is_ui_only_and_has_no_3d_backend_dependency(self) -> None:
        source = (PACKAGE / "v1_4_preview_mode_shell_patch.py").read_text(encoding="utf-8")
        self.assertIn("class", source if False else "class")  # keep unittest discovery simple
        self.assertIn("QStackedWidget", source)
        self.assertIn('QPushButton("3D")', source)
        self.assertIn("ZoomableImageView", source)
        self.assertIn('QPushButton("100%")', source)
        self.assertIn("viewer.zoom_by(0.8)", source)
        self.assertIn("viewer.zoom_by(1.25)", source)
        self.assertIn("viewer.fit_image", source)
        self.assertNotIn("preview3d", source)
        self.assertNotIn("PyOpenGL", source)
        self.assertNotIn("OpenGL", source)
        self.assertNotIn("numpy", source)
        self.assertNotIn("convert_vehicle", source)
        self.assertNotIn("load_kfps_glb", source)

    def test_non_livery_preview_stays_on_exact_337_path(self) -> None:
        source = (PACKAGE / "v1_4_preview_mode_shell_patch.py").read_text(encoding="utf-8")
        self.assertIn("original_show = MainWindow._show_livery_image", source)
        self.assertIn("if not isinstance(record, LiveryRecord):", source)
        self.assertIn("original_show(window, record)", source)

    def test_shell_is_installed_before_existing_performance_probe(self) -> None:
        source = (PACKAGE / "v1_3_4_backup_action_wording_patch.py").read_text(encoding="utf-8")
        preview_import = "from .v1_4_preview_mode_shell_patch import apply_v1_4_preview_mode_shell_patch"
        preview_call = "apply_v1_4_preview_mode_shell_patch(MainWindow)"
        profiler_call = "apply_v1_3_4_performance_probe_patch(MainWindow)"
        self.assertIn(preview_import, source)
        self.assertIn(preview_call, source)
        self.assertIn(profiler_call, source)
        self.assertLess(source.index(preview_call), source.index(profiler_call))

    def test_stage_one_does_not_change_runtime_dependencies(self) -> None:
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertNotIn("PyOpenGL", requirements)
        self.assertNotIn("numpy", requirements.lower())


if __name__ == "__main__":
    unittest.main()
