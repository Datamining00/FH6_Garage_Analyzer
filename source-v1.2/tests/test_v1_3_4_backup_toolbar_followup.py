from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QPushButton, QWidget

from fh6garage.models import HeaderInfo, LiveryRecord
from fh6garage.v1_3_4_backup_toolbar_followup_patch import (
    _game_only_export_records,
    _set_exclusive_pair,
    _status_counts,
)


_APP = QApplication.instance() or QApplication([])


class BackupToolbarFollowupTests(unittest.TestCase):
    @staticmethod
    def _record(kind: str, name: str = "Livery_1") -> LiveryRecord:
        return LiveryRecord(
            container_name=name,
            container_path=Path("C:/dummy") / name,
            kind=kind,
            header=HeaderInfo(
                name="Test",
                creator="Creator",
                car_id=1,
                description="Description",
            ),
        )

    def test_source_and_location_pairs_are_exactly_exclusive(self) -> None:
        owner = QWidget()
        first = QPushButton(owner)
        second = QPushButton(owner)
        first.setCheckable(True)
        second.setCheckable(True)
        first.setChecked(True)
        second.setChecked(True)

        _set_exclusive_pair(owner, first, second, "group")
        self.assertTrue(first.isChecked())
        self.assertFalse(second.isChecked())

        second.click()
        self.assertFalse(first.isChecked())
        self.assertTrue(second.isChecked())

        second.click()
        self.assertFalse(first.isChecked())
        self.assertTrue(second.isChecked())

    def test_status_counts_mean_total_backup_game_only_and_both(self) -> None:
        backup = self._record("Livery", "backup")
        game = self._record("Livery", "game")
        both = self._record("SoulBoundLivery", "both")
        items = [(object(), backup, "backup"), (None, game, "game"), (object(), both, "both")]
        with patch(
            "fh6garage.v1_3_4_backup_toolbar_followup_patch._perf._backup_items",
            return_value=items,
        ):
            self.assertEqual(_status_counts(object()), (2, 1, 1))

    def test_bulk_export_targets_game_only_selected_source(self) -> None:
        owner = QWidget()
        owner.backup_auction_toggle = QPushButton(owner)
        owner.backup_auction_toggle.setCheckable(True)
        owner.backup_auction_toggle.setChecked(False)
        owner.backup_search = None
        owner._car_label = lambda car_id: f"Car {car_id}"

        livery = self._record("Livery", "game-livery")
        auction = self._record("SoulBoundLivery", "game-auction")
        items = [(None, livery, "game"), (None, auction, "game")]
        with patch(
            "fh6garage.v1_3_4_backup_toolbar_followup_patch._perf._backup_items",
            return_value=items,
        ):
            self.assertEqual(_game_only_export_records(owner), [livery])
            owner.backup_auction_toggle.setChecked(True)
            self.assertEqual(_game_only_export_records(owner), [auction])

    def test_patch_contract_contains_requested_toolbar_and_status(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (root / "fh6garage" / "v1_3_4_backup_toolbar_followup_patch.py").read_text(encoding="utf-8")
        wording = (root / "fh6garage" / "v1_3_4_backup_action_wording_patch.py").read_text(encoding="utf-8")
        app = (root / "app.py").read_text(encoding="utf-8")

        self.assertIn("QButtonGroup", source)
        self.assertIn('f"전체 백업 {total_backup} \\\\ 게임 {game_only} \\\\ 게임+백업 {both}"', source)
        self.assertIn('QPushButton(_txt("내보내기", "Export"))', source)
        self.assertIn("row.insertWidget(index + 1", source)
        self.assertIn("apply_v1_3_4_backup_toolbar_followup_patch(MainWindow)", wording)
        self.assertLess(
            app.index("apply_v1_3_4_backup_action_wording_patch(MainWindow)"),
            app.index("apply_v1_3_2_thread_affinity_fix(MainWindow)"),
        )


if __name__ == "__main__":
    unittest.main()
