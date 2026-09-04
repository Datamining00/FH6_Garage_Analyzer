from __future__ import annotations

import unittest
from pathlib import Path


class LiveryBackupFilterContractTests(unittest.TestCase):
    def test_filter_adds_not_backed_up_mode_and_uses_cached_presence(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (root / "fh6garage" / "v1_3_4_livery_backup_filter_patch.py").read_text(encoding="utf-8")
        self.assertIn('_NOT_BACKED_UP_MODE = 14', source)
        self.assertIn('"백업되지 않음"', source)
        self.assertIn('_perf._presence_snapshot(window)', source)
        self.assertIn('_perf._record_backed_up(record, containers, identities)', source)
        self.assertIn('button._actions[_NOT_BACKED_UP_MODE] = row', source)

    def test_filter_repacks_existing_visible_cards_without_tuning_changes(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (root / "fh6garage" / "v1_3_4_livery_backup_filter_patch.py").read_text(encoding="utf-8")
        self.assertIn('if not card.isVisible():', source)
        self.assertIn('window._clear_livery_grid_layout()', source)
        self.assertIn('window._layout_visible_grid_cards("livery", visible)', source)
        self.assertNotIn('_relayout_tuning_grid', source)

    def test_filter_is_installed_after_final_backup_toolbar_layer(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (root / "fh6garage" / "v1_3_4_backup_action_wording_patch.py").read_text(encoding="utf-8")
        toolbar = source.index('apply_v1_3_4_backup_toolbar_followup_patch(MainWindow)')
        backup_filter = source.index('apply_v1_3_4_livery_backup_filter_patch(MainWindow)')
        self.assertLess(toolbar, backup_filter)


if __name__ == "__main__":
    unittest.main()
