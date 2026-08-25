from __future__ import annotations

import unittest
from pathlib import Path


class V132ThreadAffinityContractTests(unittest.TestCase):
    def test_app_no_longer_applies_thread_runtime_fix(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (root / "app.py").read_text(encoding="utf-8")
        self.assertNotIn("apply_v1_3_2_thread_affinity_fix(MainWindow)", source)
        self.assertNotIn("apply_v1_3_2_diagnostic_patches(MainWindow)", source)
        self.assertNotIn("apply_v1_3_2_card_parent_patches(MainWindow)", source)
        self.assertIn("window = MainWindow(project_root=root)", source)

    def test_original_qt_slot_is_never_replaced(self) -> None:
        root = Path(__file__).resolve().parents[1]
        package = root / "fh6garage"
        self.assertFalse((package / "v1_3_2_thread_affinity_patch.py").exists())
        for name in ("v1_3_2_patch.py", "v1_3_2_list_fix.py"):
            source = (package / name).read_text(encoding="utf-8")
            self.assertNotIn("MainWindow._scan_finished =", source)

    def test_postprocessing_is_integrated_into_populate_all(self) -> None:
        root = Path(__file__).resolve().parents[1]
        ui_source = (root / "fh6garage" / "ui.py").read_text(encoding="utf-8")
        processing_source = (
            root / "fh6garage" / "scan_result_processing.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "populate_scan_result_ui(self, self._populate_all_content)",
            ui_source,
        )
        self.assertIn("def assign_auction_thumbnails", processing_source)
        self.assertIn("_fh6_v132_initial_scan_build = True", processing_source)
        self.assertIn("QTimer.singleShot(0, scheduler)", processing_source)

    def test_both_content_types_receive_constant_time_indexes(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (root / "fh6garage" / "saved_content_cards.py").read_text(encoding="utf-8")
        self.assertIn("tuning_by_key", source)
        self.assertIn('"livery": livery_by_key', source)
        self.assertIn('"tuning": tuning_by_key', source)
        self.assertIn("_fh6_record_index_ready = True", source)

    def test_base_scan_callback_is_qt_slot(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (root / "fh6garage" / "ui.py").read_text(encoding="utf-8")
        self.assertIn("@Slot(object)\n    def _scan_finished", source)


if __name__ == "__main__":
    unittest.main()
