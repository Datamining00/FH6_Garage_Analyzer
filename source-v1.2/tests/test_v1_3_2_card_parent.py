from __future__ import annotations

import unittest
from pathlib import Path


class V132CardParentContractTests(unittest.TestCase):
    def test_obsolete_card_parent_patch_is_not_applied(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (root / "app.py").read_text(encoding="utf-8")
        self.assertNotIn("apply_v1_3_2_card_parent_patches(MainWindow)", source)
        self.assertNotIn("apply_v1_3_2_thread_affinity_fix(MainWindow)", source)

    def test_legacy_patch_file_remains_inert(self) -> None:
        root = Path(__file__).resolve().parents[1]
        patch = root / "fh6garage" / "v1_3_2_card_parent_patch.py"
        self.assertTrue(patch.exists())
        app_source = (root / "app.py").read_text(encoding="utf-8")
        self.assertNotIn("v1_3_2_card_parent_patch", app_source)


if __name__ == "__main__":
    unittest.main()
