from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
ICON_ROOT = ROOT / "icons"
CARD_ROOT = ICON_ROOT / "cards"


class CardIconAssetTests(unittest.TestCase):
    def test_only_program_icon_and_card_directory_remain(self) -> None:
        self.assertEqual(
            sorted(path.name for path in ICON_ROOT.iterdir()),
            ["FH6_Assistant.ico", "cards"],
        )

    def test_card_icon_set_is_complete(self) -> None:
        expected = {
            "01_move.png", "02_zoom.png", "03_memo.png", "04_memo_written.png",
            "05_info.png", "06_folder.png", "07_export.png", "08_paint.png",
            "09_unlock.png", "10_lock.png", "11_visible.png", "12_hidden.png",
            "13_circle.png", "14_triangle.png", "15_x.png", "16_import.png",
            "17_collapse_right.png", "18_expand_left.png",
        }
        self.assertEqual({path.name for path in CARD_ROOT.glob("*.png")}, expected)

    def test_both_build_specs_bundle_card_directory(self) -> None:
        for name in ("FH6_Assistant_v1.3.3.spec", "FH6_Assistant_v1.3.3_portable.spec"):
            source = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn("project_root / 'icons' / 'cards'", source)
            self.assertNotIn("paint_bucket.png", source)


if __name__ == "__main__":
    unittest.main()
