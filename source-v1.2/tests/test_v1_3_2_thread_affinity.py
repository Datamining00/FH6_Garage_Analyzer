from __future__ import annotations

import unittest
from pathlib import Path


class V132ThreadAffinityContractTests(unittest.TestCase):
    def test_app_applies_thread_fix_last(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (root / "app.py").read_text(encoding="utf-8")
        self.assertIn("apply_v1_3_2_thread_affinity_fix(MainWindow)", source)
        self.assertNotIn("apply_v1_3_2_diagnostic_patches(MainWindow)", source)
        self.assertNotIn("apply_v1_3_2_card_parent_patches(MainWindow)", source)
        self.assertLess(
            source.index("apply_v1_3_2_list_fixes(MainWindow)"),
            source.index("apply_v1_3_2_thread_affinity_fix(MainWindow)"),
        )

    def test_original_qt_slot_is_restored(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (root / "fh6garage" / "v1_3_2_thread_affinity_patch.py").read_text(encoding="utf-8")
        self.assertIn("_ORIGINAL_SCAN_FINISHED = _UiMainWindow._scan_finished", source)
        self.assertIn("MainWindow._scan_finished = _ORIGINAL_SCAN_FINISHED", source)
        self.assertNotIn("def patched_scan_finished", source)

    def test_postprocessing_moved_to_populate_all(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (root / "fh6garage" / "v1_3_2_thread_affinity_patch.py").read_text(encoding="utf-8")
        self.assertIn("def patched_populate_all", source)
        self.assertIn("assign_auction_thumbnails", source)
        self.assertIn("_fh6_v132_initial_scan_build = True", source)
        self.assertIn("QTimer.singleShot(0, scheduler)", source)

    def test_both_content_types_receive_constant_time_indexes(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (root / "fh6garage" / "v1_3_2_thread_affinity_patch.py").read_text(encoding="utf-8")
        self.assertIn("tuning_by_key", source)
        self.assertIn('"livery": by_key', source)
        self.assertIn('"tuning": tuning_by_key', source)
        self.assertIn("_fh6_record_index_ready = True", source)

    def test_pre_car_startup_work_is_split_into_diagnostics(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (root / "fh6garage" / "v1_3_2_thread_affinity_patch.py").read_text(encoding="utf-8")
        self.assertIn("startup.populate.pre_car.auction_thumbnail_match", source)
        self.assertIn("startup.populate.pre_car.record_indexes", source)

    def test_base_scan_callback_is_qt_slot(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (root / "fh6garage" / "ui.py").read_text(encoding="utf-8")
        self.assertIn("@Slot(object)\n    def _scan_finished", source)


if __name__ == "__main__":
    unittest.main()
