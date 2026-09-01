from __future__ import annotations

import unittest
from pathlib import Path


class V132ScanPostprocessingModuleContractTests(unittest.TestCase):
    def setUp(self) -> None:
        root = Path(__file__).resolve().parents[1]
        self.compat = (root / "fh6garage" / "v1_3_2_thread_affinity_patch.py").read_text(encoding="utf-8")
        self.scan = (root / "fh6garage" / "v1_3_2_scan_postprocessing.py").read_text(encoding="utf-8")

    def test_compatibility_module_reexports_scan_api(self) -> None:
        self.assertIn("from .v1_3_2_scan_postprocessing import (", self.compat)
        self.assertIn("apply_v1_3_2_scan_postprocessing", self.compat)
        self.assertIn("assign_auction_thumbnails", self.compat)

    def test_scan_implementation_moved_out_of_affinity_module(self) -> None:
        self.assertNotIn("def apply_v1_3_2_scan_postprocessing", self.compat)
        self.assertNotIn("def assign_auction_thumbnails", self.compat)
        self.assertIn("def apply_v1_3_2_scan_postprocessing", self.scan)
        self.assertIn("def assign_auction_thumbnails", self.scan)

    def test_compatibility_module_reexports_affinity_fix(self) -> None:
        self.assertIn(
            "from .v1_3_2_thread_affinity_fix import apply_v1_3_2_thread_affinity_fix",
            self.compat,
        )
        self.assertNotIn("_ORIGINAL_SCAN_FINISHED = _UiMainWindow._scan_finished", self.compat)


if __name__ == "__main__":
    unittest.main()
