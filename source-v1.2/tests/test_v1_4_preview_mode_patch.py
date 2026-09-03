from __future__ import annotations

import unittest
from pathlib import Path


class V14PreviewModePatchTests(unittest.TestCase):
    def test_preview_modes_are_thumbnail_image_and_3d(self):
        text = Path("fh6garage/v1_4_preview_mode_patch.py").read_text(encoding="utf-8")
        self.assertIn('_txt("썸네일", "Thumbnail")', text)
        self.assertIn('_txt("이미지", "Image")', text)
        self.assertIn('"3D"', text)
        self.assertIn("content_stack.setCurrentIndex(1)", text)
        self.assertIn("options_stack.setCurrentIndex(1)", text)
        self.assertIn("mode_buttons[1].setChecked(True)", text)

    def test_image_mode_keeps_existing_zoom_contract(self):
        text = Path("fh6garage/v1_4_preview_mode_patch.py").read_text(encoding="utf-8")
        self.assertIn("ZoomableImageView", text)
        self.assertIn("viewer.zoom_by(0.8)", text)
        self.assertIn("viewer.actual_size", text)
        self.assertIn("viewer.fit_image", text)
        self.assertIn("viewer.zoom_by(1.25)", text)

    def test_3d_is_lazy_and_failure_isolated(self):
        text = Path("fh6garage/v1_4_preview_mode_patch.py").read_text(encoding="utf-8")
        self.assertIn('_fh6_prepare_livery_3d_preview', text)
        self.assertIn('QTimer.singleShot(0, invoke_backend)', text)
        self.assertIn('if prepared["requested"]', text)
        self.assertIn('except Exception as exc', text)
        self.assertIn('backend failures must not break image modes', text)

    def test_legacy_is_default_3d_eligibility(self):
        text = Path("fh6garage/v1_4_preview_mode_patch.py").read_text(encoding="utf-8")
        legacy = text.index('eligibility.addItem("Legacy", "legacy")')
        strict = text.index('eligibility.addItem("Strict", "strict")')
        self.assertLess(legacy, strict)
        self.assertIn("eligibility.setCurrentIndex(0)", text)

    def test_patch_is_wired_before_performance_probe(self):
        stack = Path("fh6garage/v1_3_4_backup_action_wording_patch.py").read_text(encoding="utf-8")
        preview = stack.index("apply_v1_4_preview_mode_patch(MainWindow)")
        profiler = stack.index("apply_v1_3_4_performance_probe_patch(MainWindow)")
        self.assertLess(preview, profiler)


if __name__ == "__main__":
    unittest.main()
