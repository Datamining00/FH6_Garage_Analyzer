from __future__ import annotations

import unittest
from pathlib import Path


class V132VisibilityContractTests(unittest.TestCase):
    def _source(self) -> str:
        root = Path(__file__).resolve().parents[1]
        return (
            root / "fh6garage" / "v1_3_2_visibility_patch.py"
        ).read_text(encoding="utf-8")

    def test_patch_is_installed_before_thread_affinity_fix(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (root / "app.py").read_text(encoding="utf-8")
        visibility = source.index("apply_v1_3_2_visibility_patches(MainWindow)")
        thread_fix = source.index("apply_v1_3_2_thread_affinity_fix(MainWindow)")
        self.assertLess(visibility, thread_fix)

    def test_applied_auction_rule_requires_real_current_webp(self) -> None:
        source = self._source()
        self.assertIn('record.kind != "SoulBoundLivery"', source)
        self.assertIn("path = record.thumbnail_path", source)
        self.assertIn("path.is_file()", source)
        self.assertNotIn("container_download_timestamp", source)

    def test_hidden_liveries_are_removed_from_navigation_sessions(self) -> None:
        source = self._source()
        self.assertIn("_fh6_hidden_navigation_scope", source)
        self.assertIn("original_reset_game_navigation_sessions", source)
        self.assertIn("if content_type == \"livery\" and is_hidden(self, key)", source)

    def test_hidden_filter_is_default_exclusion_and_explicit_recovery(self) -> None:
        source = self._source()
        self.assertIn("_HIDDEN_MODE = 11", source)
        self.assertIn("hidden_only = _HIDDEN_MODE in modes", source)
        self.assertIn("elif hidden:", source)
        self.assertIn("table.setRowHidden(row, True)", source)

    def test_auction_applied_and_unapplied_filters_are_mutually_exclusive(self) -> None:
        source = self._source()
        self.assertIn("_AUCTION_APPLIED_MODE = 12", source)
        self.assertIn("_AUCTION_UNAPPLIED_MODE = 13", source)
        self.assertIn("other.blockSignals(True)", source)
        self.assertIn("other.setChecked(False)", source)

    def test_hide_button_is_above_description_in_livery_info(self) -> None:
        source = self._source()
        hide_row = source.index("layout.addLayout(hide_row)")
        description = source.index('layout.addWidget(QLabel(tr("detail.description")))')
        uploaded = source.index('layout.addWidget(QLabel(tr("detail.uploaded", date=uploaded)))')
        self.assertLess(hide_row, description)
        self.assertLess(description, uploaded)
        self.assertIn("_eye_slash_pixmap", source)


if __name__ == "__main__":
    unittest.main()
