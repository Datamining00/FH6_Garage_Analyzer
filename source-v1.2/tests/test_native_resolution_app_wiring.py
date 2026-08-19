from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class NativeResolutionAppWiringTests(unittest.TestCase):
    def test_app_uses_final_preview_ui_after_quality_pipeline(self) -> None:
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn('app.setApplicationVersion("1.4 Preview UX Test")', source)
        self.assertIn("apply_v1_4_native_resolution_test_patch(MainWindow)", source)
        self.assertIn("apply_v1_4_quality_pipeline_patch(MainWindow)", source)
        self.assertIn("apply_v1_4_preview_final_ui_patch(MainWindow)", source)
        self.assertNotIn("apply_v1_4_web_canvas_test_patch(MainWindow)", source)
        self.assertNotIn("apply_v1_4_projection_quality_test_patch(MainWindow)", source)
        self.assertLess(
            source.index("apply_v1_4_quality_pipeline_patch(MainWindow)"),
            source.index("apply_v1_4_preview_final_ui_patch(MainWindow)"),
        )

    def test_test_metadata_does_not_replace_final_v14_metadata(self) -> None:
        test_meta = (ROOT / "version_info_preview_ux_test.txt").read_text(encoding="utf-8")
        final_meta = (ROOT / "version_info.txt").read_text(encoding="utf-8")
        self.assertIn("FH6 Assistant v1.4 Preview UX Test.exe", test_meta)
        self.assertIn("FH6 Assistant v1.4.exe", final_meta)
        self.assertIn("filevers=(1, 4, 0, 0)", final_meta)


if __name__ == "__main__":
    unittest.main()
