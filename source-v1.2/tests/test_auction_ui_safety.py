from __future__ import annotations

import unittest
from pathlib import Path

from fh6garage.auction_ui_safety import is_auction_livery
from fh6garage.models import HeaderInfo, LiveryRecord

ROOT = Path(__file__).resolve().parents[1]


def _record(kind: str) -> LiveryRecord:
    return LiveryRecord(
        container_name=f"{kind}_0368_test",
        container_path=Path("."),
        kind=kind,
        header=HeaderInfo(car_id=368),
    )


class AuctionUiSafetyTests(unittest.TestCase):
    def test_only_soulbound_livery_is_auction_navigation_record(self) -> None:
        self.assertTrue(is_auction_livery(_record("SoulBoundLivery")))
        self.assertFalse(is_auction_livery(_record("Livery")))
        self.assertFalse(is_auction_livery(None))

    def test_navigation_and_duplicate_checks_reject_auction_records(self) -> None:
        source = (ROOT / "fh6garage" / "ui.py").read_text(encoding="utf-8")
        self.assertIn("is_auction_livery(record)", source)
        self.assertIn("not is_auction_livery(record)", source)

    def test_auction_card_never_creates_game_move_control(self) -> None:
        source = (ROOT / "fh6garage" / "ui.py").read_text(encoding="utf-8")
        self.assertIn('content_type == "livery" and is_auction_livery(record)', source)
        self.assertIn('game_move_button = None', source)

    def test_runtime_patch_is_removed(self) -> None:
        app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertNotIn("apply_v1_3_2_safety_patches", app_source)
        self.assertFalse((ROOT / "fh6garage" / "v1_3_2_safety_patch.py").exists())


if __name__ == "__main__":
    unittest.main()
