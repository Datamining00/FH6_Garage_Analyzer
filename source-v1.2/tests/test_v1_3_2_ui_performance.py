from __future__ import annotations

import os
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFrame, QLineEdit, QWidget

from fh6garage.models import HeaderInfo, LiveryRecord
from fh6garage.saved_content_cards import (
    _populate_livery_grid_reusing_cards,
)


ROOT = Path(__file__).resolve().parents[1]


class _Annotations:
    def get(self, _key: str):
        return SimpleNamespace(
            note="",
            checked=False,
            triangle=False,
            excluded=False,
        )


class _FakeWindow:
    def __init__(self) -> None:
        self.annotations = _Annotations()
        self.livery_search = QLineEdit()
        self.livery_grid_host = QWidget()
        self.tuning_grid_host = QWidget()
        self._livery_grid_cards = []
        self._livery_card_by_key = {}
        self._tuning_grid_cards = []
        self._tuning_card_by_key = {}
        self._livery_group_headers = {}
        self._tuning_group_headers = {}
        self._fh6_ui_cache_result_token = None
        self._fh6_ui_cache_scope = ""
        self._fh6_ui_record_signatures = {"livery": {}, "tuning": {}}
        self._fh6_ui_livery_cards_created = 0
        self._fh6_ui_livery_cards_reused = 0
        self._fh6_ui_tuning_cards_created = 0
        self._fh6_ui_tuning_cards_reused = 0
        self._fh6_ui_cards_discarded = 0
        self._fh6_v132_auction_build_generation = 0
        self.records: list[LiveryRecord] = []
        self.result = SimpleNamespace(
            metadata=SimpleNamespace(save_root=Path("save")),
            liveries=[],
            tunings=[],
        )
        self.relayout_orders: list[list[str]] = []
        self.unloaded: list[str] = []

    def _clear_livery_grid_layout(self) -> None:
        return

    def _clear_tuning_grid_layout(self) -> None:
        return

    def _sorted_liveries(self) -> list[LiveryRecord]:
        return list(self.records)

    def _annotation_key(self, record: LiveryRecord) -> str:
        return record.container_name

    def _content_annotation_key(self, _content_type: str, record) -> str:
        return record.container_name

    def install_scan(
        self,
        records: list[LiveryRecord],
        *,
        root: str = "save",
    ) -> None:
        self.records = list(records)
        self.result = SimpleNamespace(
            metadata=SimpleNamespace(save_root=Path(root)),
            liveries=list(records),
            tunings=[],
        )

    def _make_livery_card(self, _record: LiveryRecord, key: str) -> QFrame:
        card = QFrame()
        card.setObjectName(key)
        return card

    def _keep_busy_responsive(self, _index: int) -> None:
        return

    def _livery_search_text(self, record: LiveryRecord, note: str = "") -> str:
        return f"{record.header.name} {note}".lower()

    def _saved_content_search_text(self, record, note: str = "") -> str:
        return f"{record.header.name} {note}".lower()

    def _car_label(self, car_id) -> str:
        return f"Car {car_id}"

    def _relayout_livery_grid(self, _text: str = "") -> None:
        self.relayout_orders.append(
            [card.objectName() for card in self._livery_grid_cards]
        )

    def _unload_livery_card_thumbnail(self, card: QFrame) -> None:
        self.unloaded.append(card.objectName())


def _record(name: str, car_id: int) -> LiveryRecord:
    return LiveryRecord(
        container_name=name,
        container_path=Path(name),
        kind="Livery",
        header=HeaderInfo(
            name=name,
            creator="Creator",
            car_id=car_id,
            guid=f"guid-{name}",
        ),
    )


class V132UiPerformanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_sort_reuses_existing_card_objects(self) -> None:
        window = _FakeWindow()
        first = _record("Livery_A", 1)
        second = _record("Livery_B", 2)
        window.install_scan([first, second])

        _populate_livery_grid_reusing_cards(window)
        first_ids = {
            key: id(card) for key, card in window._livery_card_by_key.items()
        }
        self.assertEqual(window._fh6_ui_livery_cards_created, 2)
        self.assertEqual(window.relayout_orders[-1], ["Livery_A", "Livery_B"])

        window.records = [second, first]
        _populate_livery_grid_reusing_cards(window)

        second_ids = {
            key: id(card) for key, card in window._livery_card_by_key.items()
        }
        self.assertEqual(first_ids, second_ids)
        self.assertEqual(window._fh6_ui_livery_cards_created, 2)
        self.assertEqual(window._fh6_ui_livery_cards_reused, 2)
        self.assertEqual(window.relayout_orders[-1], ["Livery_B", "Livery_A"])

    def test_source_toggle_keeps_disabled_card_cached(self) -> None:
        window = _FakeWindow()
        saved = _record("MyDesign", 1)
        auction = _record("Auction", 2)
        auction.kind = "SoulBoundLivery"
        window.install_scan([saved, auction])
        _populate_livery_grid_reusing_cards(window)

        auction_card_id = id(window._livery_card_by_key["Auction"])
        window.records = [saved]
        _populate_livery_grid_reusing_cards(window)

        self.assertIn("Auction", window._livery_card_by_key)
        self.assertEqual(id(window._livery_card_by_key["Auction"]), auction_card_id)
        self.assertEqual(window.relayout_orders[-1], ["MyDesign"])
        self.assertIn("Auction", window.unloaded)

        window.records = [saved, auction]
        _populate_livery_grid_reusing_cards(window)
        self.assertEqual(id(window._livery_card_by_key["Auction"]), auction_card_id)

    def test_same_save_refresh_reuses_unchanged_card(self) -> None:
        window = _FakeWindow()
        record = _record("Livery_A", 1)
        window.install_scan([record])
        _populate_livery_grid_reusing_cards(window)
        old_card = window._livery_card_by_key["Livery_A"]

        window.install_scan([_record("Livery_A", 1)])
        _populate_livery_grid_reusing_cards(window)

        self.assertIs(window._livery_card_by_key["Livery_A"], old_card)
        self.assertEqual(window._fh6_ui_livery_cards_created, 1)

    def test_changed_record_recreates_only_its_card(self) -> None:
        window = _FakeWindow()
        first = _record("Livery_A", 1)
        second = _record("Livery_B", 2)
        window.install_scan([first, second])
        _populate_livery_grid_reusing_cards(window)
        first_card = window._livery_card_by_key["Livery_A"]
        second_card = window._livery_card_by_key["Livery_B"]

        changed = _record("Livery_A", 1)
        changed.header.name = "Changed title"
        window.install_scan([changed, _record("Livery_B", 2)])
        _populate_livery_grid_reusing_cards(window)

        self.assertIsNot(window._livery_card_by_key["Livery_A"], first_card)
        self.assertIs(window._livery_card_by_key["Livery_B"], second_card)
        self.assertEqual(window._fh6_ui_cards_discarded, 1)

    def test_removed_record_is_not_retained_in_card_cache(self) -> None:
        window = _FakeWindow()
        window.install_scan([_record("Livery_A", 1), _record("Livery_B", 2)])
        _populate_livery_grid_reusing_cards(window)

        window.install_scan([_record("Livery_A", 1)])
        _populate_livery_grid_reusing_cards(window)

        self.assertEqual(set(window._livery_card_by_key), {"Livery_A"})
        self.assertEqual(window._fh6_ui_cards_discarded, 1)

    def test_different_save_root_resets_card_cache(self) -> None:
        window = _FakeWindow()
        window.install_scan([_record("Livery_A", 1)], root="save-a")
        _populate_livery_grid_reusing_cards(window)
        old_card = window._livery_card_by_key["Livery_A"]

        window.install_scan([_record("Livery_A", 1)], root="save-b")
        _populate_livery_grid_reusing_cards(window)

        self.assertIsNot(window._livery_card_by_key["Livery_A"], old_card)

    def test_performance_and_scan_processing_are_integrated(self) -> None:
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        perf = "apply_v1_3_2_ui_performance_patches(MainWindow)"
        thread_fix = "apply_v1_3_2_thread_affinity_fix(MainWindow)"
        ui_source = (ROOT / "fh6garage" / "ui.py").read_text(encoding="utf-8")
        self.assertNotIn(perf, source)
        self.assertIn("initialize_ui_performance_state(self)", ui_source)
        self.assertNotIn(thread_fix, source)
        self.assertIn("populate_scan_result_ui(self, self._populate_all_content)", ui_source)

    def test_visible_grid_path_does_not_build_hidden_legacy_tables(self) -> None:
        source = (ROOT / "fh6garage" / "ui.py").read_text(encoding="utf-8")
        start = source.index("def _populate_livery_view")
        end = source.index("def _populate_livery_grid")
        livery_block = source[start:end]
        self.assertNotIn("_populate_saved_content_table", livery_block)
        self.assertIn("self._populate_livery_grid()", livery_block)


if __name__ == "__main__":
    unittest.main()
