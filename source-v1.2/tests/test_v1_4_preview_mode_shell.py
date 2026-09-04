from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "fh6garage"
BASE_SHELL = PACKAGE / "v1_4_preview_mode_shell_base.py"
PUBLIC_SHELL = PACKAGE / "v1_4_preview_mode_shell_patch.py"


class PreviewModeShellContractTests(unittest.TestCase):
    def test_preserved_stage_one_shell_has_exact_three_mode_structure(self) -> None:
        source = BASE_SHELL.read_text(encoding="utf-8")
        self.assertIn("def _show_livery_preview_shell", source)
        self.assertIn("QStackedWidget", source)
        self.assertIn('_txt("썸네일", "Thumbnail")', source)
        self.assertIn('_txt("이미지", "Image")', source)
        self.assertIn('"3D"', source)
        self.assertIn("content_stack.addWidget(thumbnail_view)", source)
        self.assertIn("content_stack.addWidget(image_page)", source)
        self.assertIn("content_stack.addWidget(three_d_page)", source)
        self.assertIn("content_stack.setCurrentIndex(0)", source)
        self.assertIn("options_stack.setCurrentIndex(0)", source)
        self.assertIn("mode_buttons[0].setChecked(True)", source)

    def test_thumbnail_mode_preserves_337_zoom_viewer(self) -> None:
        source = BASE_SHELL.read_text(encoding="utf-8")
        self.assertIn("path = record.thumbnail_path", source)
        self.assertIn("ZoomableImageView(QPixmap.fromImage(image))", source)
        self.assertIn('_secondary_button("100%")', source)
        self.assertIn("viewer.zoom_by(0.8)", source)
        self.assertIn("viewer.zoom_by(1.25)", source)
        self.assertIn("viewer.fit_image", source)
        self.assertIn("viewer.actual_size", source)

    def test_stage_one_image_and_3d_placeholders_are_preserved_in_base(self) -> None:
        source = BASE_SHELL.read_text(encoding="utf-8")
        self.assertIn("이미지 렌더러는 다음 검증 단계에서 연결됩니다.", source)
        self.assertIn("3D 백엔드는 다음 검증 단계에서 연결됩니다.", source)
        self.assertIn('eligibility.addItem("Legacy", "legacy")', source)
        self.assertIn('eligibility.addItem("Strict", "strict")', source)
        self.assertIn("eligibility.setCurrentIndex(0)", source)
        self.assertNotIn("from .preview3d", source)
        self.assertNotIn("from OpenGL", source)
        self.assertNotIn("import numpy", source)
        self.assertNotIn("convert_vehicle", source)
        self.assertNotIn("load_kfps_glb", source)

    def test_stage_two_b_public_shell_adds_only_lazy_3d_connection(self) -> None:
        source = PUBLIC_SHELL.read_text(encoding="utf-8")
        self.assertIn("from . import v1_4_preview_mode_shell_base as _base", source)
        self.assertIn("from .preview3d.integration import _prepare_preview_3d", source)
        self.assertIn('prepared = {"requested": False}', source)
        self.assertIn("QTimer.singleShot(0, invoke_backend)", source)
        self.assertIn('eligibility.findData("strict")', source)
        self.assertNotIn("from OpenGL", source)
        self.assertNotIn("import numpy", source)

    def test_non_livery_preview_stays_on_exact_337_path(self) -> None:
        source = BASE_SHELL.read_text(encoding="utf-8")
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

    def test_stage_two_b_declares_3d_runtime_dependencies(self) -> None:
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("PyOpenGL", requirements)
        self.assertIn("numpy", requirements.lower())
        self.assertIn("Pillow", requirements)


if __name__ == "__main__":
    unittest.main()
