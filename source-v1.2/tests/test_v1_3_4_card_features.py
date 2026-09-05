from __future__ import annotations

import types
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication, QFrame, QGridLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from fh6garage.i18n import set_language
from fh6garage.ui import CopyValueLabel
from fh6garage.v1_3_4_card_features_patch import (
    _duplicate_card_groups,
    _duplicate_filter_active,
    _install_livery_lock,
    _install_metadata_toggle,
    _layout_duplicate_groups,
    _lock_pref_key,
    _recent_duplicate_groups,
)


_APP = QApplication.instance() or QApplication([])


class _Preferences:
    def __init__(self, values: dict[str, bool] | None = None) -> None:
        self.values = dict(values or {})
        self.write_count = 0

    def get_bool(self, key: str, default: bool = False) -> bool:
        value = self.values.get(key, default)
        return value if isinstance(value, bool) else default

    def set_bool(self, key: str, value: bool) -> None:
        self.values[key] = bool(value)
        self.write_count += 1


class _Filter:
    def __init__(self, modes: set[int]) -> None:
        self.modes = set(modes)

    def selected_modes(self) -> set[int]:
        return set(self.modes)


class V134CardFeaturesTests(unittest.TestCase):
    def setUp(self) -> None:
        set_language("ko")

    @staticmethod
    def _metadata_card() -> tuple[QFrame, QGridLayout, CopyValueLabel, QLabel, CopyValueLabel, CopyValueLabel]:
        card = QFrame()
        outer = QVBoxLayout(card)
        grid = QGridLayout()
        vehicle = CopyValueLabel("차량", "1969 Toyota 2000 GT", card)
        source = QLabel("출처:", card)
        source.setObjectName("fh6AcquisitionPlaceholder")
        creator = CopyValueLabel("제작", "guutara1158", card)
        title = CopyValueLabel("제목", "hokusai", card)
        grid.addWidget(vehicle, 0, 0)
        grid.addWidget(source, 0, 1)
        grid.addWidget(creator, 1, 0)
        grid.addWidget(title, 1, 1)
        outer.addLayout(grid)
        return card, grid, vehicle, source, creator, title

    @staticmethod
    def _grid_position(grid: QGridLayout, widget: QWidget) -> tuple[int, int, int, int]:
        return grid.getItemPosition(grid.indexOf(widget))

    def test_metadata_toggle_is_common_and_reallocates_right_column(self) -> None:
        prefs = _Preferences()
        window = types.SimpleNamespace(local_preferences=prefs)
        card1, grid1, vehicle1, source1, _creator1, title1 = self._metadata_card()
        card2, grid2, vehicle2, source2, _creator2, title2 = self._metadata_card()

        _install_metadata_toggle(window, card1)
        _install_metadata_toggle(window, card2)

        toggle1 = card1.findChild(QToolButton, "fh6MetadataToggleButton")
        toggle2 = card2.findChild(QToolButton, "fh6MetadataToggleButton")
        self.assertIsNotNone(toggle1)
        self.assertIsNotNone(toggle2)
        self.assertEqual(toggle1.text(), "›")
        self.assertEqual(self._grid_position(grid1, vehicle1), (0, 0, 1, 1))
        self.assertEqual(self._grid_position(grid1, source1), (0, 2, 1, 1))

        toggle1.click()
        _APP.processEvents()

        self.assertTrue(prefs.values["card_metadata_right_collapsed"])
        self.assertTrue(source1.isHidden())
        self.assertTrue(title1.isHidden())
        self.assertTrue(source2.isHidden())
        self.assertTrue(title2.isHidden())
        self.assertEqual(toggle1.text(), "‹")
        self.assertEqual(toggle2.text(), "‹")
        self.assertEqual(self._grid_position(grid1, vehicle1), (0, 0, 1, 2))
        self.assertEqual(self._grid_position(grid2, vehicle2), (0, 0, 1, 2))

        toggle2.click()
        _APP.processEvents()
        self.assertFalse(prefs.values["card_metadata_right_collapsed"])
        self.assertFalse(source1.isHidden())
        self.assertFalse(source2.isHidden())

    def test_livery_lock_disables_only_move_and_persists_on_user_toggle(self) -> None:
        prefs = _Preferences()
        window = types.SimpleNamespace(local_preferences=prefs)
        card = QFrame()
        move = QToolButton(card)
        move.setToolTip("original move")
        lock = QToolButton(card)
        lock.setCheckable(True)
        card._fh6_game_move_button = move
        card._fh6_lock_placeholder_button = lock

        _install_livery_lock(window, card, "item-a")
        self.assertTrue(move.isEnabled())
        self.assertEqual(prefs.write_count, 0)

        lock.click()
        self.assertFalse(move.isEnabled())
        self.assertTrue(prefs.values[_lock_pref_key("item-a")])
        self.assertTrue(bool(card.property("fh6MoveLocked")))
        self.assertIn("게임에서 직접", lock.toolTip())

        lock.click()
        self.assertTrue(move.isEnabled())
        self.assertFalse(prefs.values[_lock_pref_key("item-a")])
        self.assertEqual(move.toolTip(), "original move")

    def test_persisted_lock_restore_does_not_write_preferences(self) -> None:
        prefs = _Preferences({_lock_pref_key("item-b"): True})
        window = types.SimpleNamespace(local_preferences=prefs)
        card = QFrame()
        move = QToolButton(card)
        lock = QToolButton(card)
        lock.setCheckable(True)
        card._fh6_game_move_button = move
        card._fh6_lock_placeholder_button = lock

        _install_livery_lock(window, card, "item-b")
        self.assertTrue(lock.isChecked())
        self.assertFalse(move.isEnabled())
        self.assertEqual(prefs.write_count, 0)

    def test_duplicate_filter_detection_and_hash_grouping(self) -> None:
        cards: list[QFrame] = []
        records: dict[str, object] = {}
        for key, digest in (("a1", "aaa"), ("a2", "AAA"), ("b1", "bbb"), ("b2", "bbb")):
            card = QFrame()
            card.setProperty("annotationKey", key)
            cards.append(card)
            records[key] = types.SimpleNamespace(kind="Livery", content_sha256=digest)

        host = QWidget()
        layout = QGridLayout(host)
        window = types.SimpleNamespace(
            livery_check_filter=_Filter({9}),
            livery_grid_layout=layout,
            _livery_group_headers={},
            _fh6_grid_column_count=lambda _content_type: 2,
            _record_for_content_key=lambda _content_type, key: records[key],
            _fh6_v132_is_livery_hidden=lambda _key: False,
        )

        self.assertTrue(_duplicate_filter_active(window))
        groups = _duplicate_card_groups(window, cards)
        self.assertEqual([len(group_cards) for _key, group_cards in groups], [2, 2])

        _layout_duplicate_groups(window, cards)
        self.assertEqual(len(window._livery_group_headers), 2)
        self.assertTrue(all(header.text() == "동일 리버리 · 2개" for header in window._livery_group_headers.values()))

    def test_recent_duplicate_entries_group_by_kind_and_content_hash(self) -> None:
        entries = [
            types.SimpleNamespace(kind="Livery", content_sha256="aaa", identity="1"),
            types.SimpleNamespace(kind="Livery", content_sha256="AAA", identity="2"),
            types.SimpleNamespace(kind="SoulBoundLivery", content_sha256="aaa", identity="3"),
        ]
        groups = _recent_duplicate_groups(entries)
        self.assertEqual([len(items) for _key, items in groups], [2, 1])

    def test_feature_patch_runs_after_card_layout_and_before_thread_finalizer(self) -> None:
        source = (Path(__file__).parents[1] / "app.py").read_text(encoding="utf-8")
        layout = source.index("apply_v1_3_4_card_action_layout_patch(MainWindow)")
        features = source.index("apply_v1_3_4_card_features_patch(MainWindow)")
        finalizer = source.index("apply_v1_3_2_thread_affinity_fix(MainWindow)")
        self.assertLess(layout, features)
        self.assertLess(features, finalizer)


if __name__ == "__main__":
    unittest.main()
