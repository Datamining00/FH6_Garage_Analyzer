from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFrame, QVBoxLayout, QWidget

from fh6garage import v1_3_2_auction_unapplied_recent_frame_fix as patch


ROOT = Path(__file__).resolve().parents[1]


class _Filter:
    def __init__(self, modes=()):
        self._modes = set(modes)

    def selected_modes(self):
        return set(self._modes)


class AuctionUnappliedRecentFrameFixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _window(self, record, *, applied: bool, modes=()):
        return SimpleNamespace(
            livery_check_filter=_Filter(modes),
            _record_for_content_key=lambda content_type, key: record,
            _fh6_v132_is_auction_applied=lambda candidate: applied,
        )

    def _card(self):
        card = QFrame()
        card.setProperty("annotationKey", "auction-key")
        return card

    def test_unmatched_soulbound_is_hidden_without_explicit_filter(self) -> None:
        record = SimpleNamespace(kind="SoulBoundLivery")
        owner = self._window(record, applied=False, modes=())
        self.assertFalse(
            patch._default_auction_visibility_allowed(owner, self._card(), True)
        )

    def test_unmatched_soulbound_is_visible_with_unapplied_filter(self) -> None:
        record = SimpleNamespace(kind="SoulBoundLivery")
        owner = self._window(
            record,
            applied=False,
            modes={patch._AUCTION_UNAPPLIED_MODE},
        )
        self.assertTrue(
            patch._default_auction_visibility_allowed(owner, self._card(), True)
        )

    def test_matched_soulbound_remains_visible_by_default(self) -> None:
        record = SimpleNamespace(kind="SoulBoundLivery")
        owner = self._window(record, applied=True, modes=())
        self.assertTrue(
            patch._default_auction_visibility_allowed(owner, self._card(), True)
        )

    def test_non_auction_livery_is_not_affected(self) -> None:
        record = SimpleNamespace(kind="Livery")
        owner = self._window(record, applied=False, modes=())
        self.assertTrue(
            patch._default_auction_visibility_allowed(owner, self._card(), True)
        )

    def test_existing_filter_rejection_is_never_overridden(self) -> None:
        record = SimpleNamespace(kind="SoulBoundLivery")
        owner = self._window(
            record,
            applied=False,
            modes={patch._AUCTION_UNAPPLIED_MODE},
        )
        self.assertFalse(
            patch._default_auction_visibility_allowed(owner, self._card(), False)
        )

    def test_recent_current_and_archive_cards_receive_visible_frame(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        current = QFrame()
        current.setObjectName("panel")
        archive = QFrame()
        archive.setObjectName("card")
        unrelated = QFrame()
        unrelated.setObjectName("other")
        layout.addWidget(current)
        layout.addWidget(archive)
        layout.addWidget(unrelated)

        patch._strengthen_recent_card_frames(root)

        for frame in (current, archive):
            self.assertTrue(bool(frame.property("fh6RecentStrongFrame")))
            self.assertIn("#cfd3dd", frame.styleSheet())
            self.assertIn("border:1px solid", frame.styleSheet())
        self.assertFalse(bool(unrelated.property("fh6RecentStrongFrame")))

    def test_patch_order_keeps_thread_affinity_final(self) -> None:
        app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        fix_pos = app_source.index(
            "apply_v1_3_2_auction_unapplied_recent_frame_fix(MainWindow)"
        )
        thread_pos = app_source.index("apply_v1_3_2_thread_affinity_fix(MainWindow)")
        self.assertLess(fix_pos, thread_pos)


if __name__ == "__main__":
    unittest.main()
