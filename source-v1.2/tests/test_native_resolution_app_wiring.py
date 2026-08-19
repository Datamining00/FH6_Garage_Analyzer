from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class NativeResolutionAppWiringTests(unittest.TestCase):
    def test_app_uses_native_resolution_test_and_not_web_canvas(self) -> None:
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn('app.setApplicationVersion("1.4 Native Resolution Test")', source)
        self.assertIn("apply_v1_4_native_resolution_test_patch(MainWindow)", source)
        self.assertNotIn("apply_v1_4_web_canvas_test_patch(MainWindow)", source)

    def test_test_metadata_does_not_replace_final_v14_metadata(self) -> None:
        test_meta = (ROOT / "version_info_native_resolution_test.txt").read_text(encoding="utf-8")
        final_meta = (ROOT / "version_info.txt").read_text(encoding="utf-8")
        self.assertIn("FH6 Assistant v1.4 Native Resolution Test.exe", test_meta)
        self.assertIn("FH6 Assistant v1.4.exe", final_meta)
        self.assertIn("filevers=(1, 4, 0, 0)", final_meta)


if __name__ == "__main__":
    unittest.main()
