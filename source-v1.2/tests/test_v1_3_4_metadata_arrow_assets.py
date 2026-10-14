from __future__ import annotations

import unittest
from pathlib import Path

from PySide6.QtGui import QImage

from fh6garage.card_icons import ICON_FILES


ROOT = Path(__file__).resolve().parents[1]
CARD_ROOT = ROOT / "icons" / "cards"


class V134MetadataArrowAssetTests(unittest.TestCase):
    def test_metadata_arrow_assets_are_registered_20px_pngs(self) -> None:
        expected = {
            "collapse_right": "17_collapse_right.png",
            "expand_left": "18_expand_left.png",
        }
        for kind, filename in expected.items():
            self.assertEqual(ICON_FILES[kind], filename)
            image = QImage(str(CARD_ROOT / filename))
            self.assertFalse(image.isNull())
            self.assertEqual((image.width(), image.height()), (20, 20))
            self.assertTrue(image.hasAlphaChannel())


if __name__ == "__main__":
    unittest.main()
