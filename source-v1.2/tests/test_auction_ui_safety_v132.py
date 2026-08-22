from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from fh6garage.models import HeaderInfo, LiveryRecord
from fh6garage.v1_3_2_safety_patch import apply_v1_3_2_safety_patches


class _DummyButton:
    def __init__(self) -> None:
        self.hidden = False
        self.parent = object()
        self.deleted = False
        self.reparented = False

    def hide(self) -> None:
        self.hidden = True

    def setParent(self, parent) -> None:
        self.reparented = True
        self.parent = parent

    def deleteLater(self) -> None:
        self.deleted = True


class _DummyMainWindow:
    def __init__(self, records: dict[str, LiveryRecord]) -> None:
        self.records = records
        self.navigation_calls: list[tuple[str, str]] = []
        self.last_button = None

    def _is_duplicate_livery(self, record) -> bool:
        return True

    def _make_saved_content_card(self, content_type, record, key):
        button = _DummyButton()
        self.last_button = button
        return SimpleNamespace(_fh6_game_move_button=button)

    def _request_game_navigation(self, content_type: str, key: str) -> None:
        self.navigation_calls.append((content_type, key))

    def _record_for_content_key(self, content_type: str, key: str):
        return self.records.get(key)


def _record(kind: str) -> LiveryRecord:
    return LiveryRecord(
        container_name=f"{kind}_0368_test",
        container_path=Path("."),
        kind=kind,
        header=HeaderInfo(car_id=368),
    )


class AuctionUiSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        apply_v1_3_2_safety_patches(_DummyMainWindow)

    def test_auction_card_move_control_is_removed_without_reparenting(self) -> None:
        auction = _record("SoulBoundLivery")
        window = _DummyMainWindow({"auction": auction})
        card = window._make_saved_content_card("livery", auction, "auction")
        button = window.last_button
        self.assertIsNotNone(button)
        self.assertTrue(button.hidden)
        self.assertFalse(button.reparented)
        self.assertIsNotNone(button.parent)
        self.assertTrue(button.deleted)
        self.assertIsNone(card._fh6_game_move_button)

    def test_my_design_card_keeps_move_control(self) -> None:
        normal = _record("Livery")
        window = _DummyMainWindow({"normal": normal})
        card = window._make_saved_content_card("livery", normal, "normal")
        self.assertIs(card._fh6_game_move_button, window.last_button)
        self.assertFalse(window.last_button.hidden)
        self.assertFalse(window.last_button.deleted)
        self.assertFalse(window.last_button.reparented)

    def test_auction_navigation_request_is_blocked(self) -> None:
        auction = _record("SoulBoundLivery")
        normal = _record("Livery")
        window = _DummyMainWindow({"auction": auction, "normal": normal})

        window._request_game_navigation("livery", "auction")
        self.assertEqual(window.navigation_calls, [])

        window._request_game_navigation("livery", "normal")
        self.assertEqual(window.navigation_calls, [("livery", "normal")])

    def test_auction_is_never_a_my_design_duplicate(self) -> None:
        auction = _record("SoulBoundLivery")
        normal = _record("Livery")
        window = _DummyMainWindow({})
        self.assertFalse(window._is_duplicate_livery(auction))
        self.assertTrue(window._is_duplicate_livery(normal))


if __name__ == "__main__":
    unittest.main()
