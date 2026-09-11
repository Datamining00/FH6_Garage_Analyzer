from __future__ import annotations

import unittest
from pathlib import Path


class RefreshInteractionRegressionContractTests(unittest.TestCase):
    def setUp(self) -> None:
        root = Path(__file__).resolve().parents[1]
        self.ui = (root / "fh6garage" / "ui.py").read_text(encoding="utf-8")
        self.post = (root / "fh6garage" / "v1_3_2_scan_postprocessing.py").read_text(encoding="utf-8")

    @staticmethod
    def _between(source: str, start: str, end: str) -> str:
        return source.split(start, 1)[1].split(end, 1)[0]

    def test_full_refresh_always_reloads_database_and_starts_a_scan(self) -> None:
        body = self._between(self.ui, "def refresh_scan(self) -> None:", "def start_scan(self, path: Path) -> None:")
        self.assertIn("self.car_db.reload()", body)
        self.assertIn("self._refresh_db_status()", body)
        self.assertIn("self.start_scan(Path(self.path_edit.text()))", body)
        self.assertNotIn("return", body)

    def test_scan_cleanup_releases_worker_state_for_second_refresh(self) -> None:
        body = self._between(self.ui, "def _scan_cleanup(self) -> None:", "@Slot(object)\n    def _scan_finished")
        self.assertIn("self._scan_thread = None", body)
        self.assertIn("self._scan_worker = None", body)

    def test_scan_completion_populates_immediately_without_sort_interaction(self) -> None:
        body = self._between(self.ui, "def _scan_finished(self, result: ScanResult) -> None:", "@Slot(str)\n    def _scan_failed")
        self.assertLess(body.index("self.result = result"), body.index("self._populate_all()"))
        self.assertNotIn("_set_saved_content_sort_mode", body)
        self.assertNotIn("_sorted_saved_content", body)

    def test_base_population_builds_livery_and_tuning_views_on_scan_completion(self) -> None:
        body = self._between(self.ui, "def _populate_all(self) -> None:", "def _configure_dashboard_table")
        self.assertIn("self._populate_livery_table()", body)
        self.assertIn("self._populate_tuning_table()", body)
        self.assertLess(body.index("self._populate_livery_table()"), body.index("self._populate_tuning_table()"))

    def test_sort_is_a_followup_rebuild_not_a_prerequisite_for_initial_population(self) -> None:
        body = self._between(self.ui, "def _set_saved_content_sort_mode(", "def _update_sort_button_labels")
        self.assertIn("if self.result is not None:", body)
        self.assertIn("self._populate_livery_table()", body)
        self.assertIn("self._populate_tuning_table()", body)

    def test_final_scan_postprocessing_keeps_population_before_deferred_auction_cards(self) -> None:
        body = self._between(self.post, "def patched_populate_all(self) -> None:", "MainWindow._populate_all = patched_populate_all")
        self.assertLess(body.index("_prepare_v132_auction_thumbnails"), body.index("current_populate_all(self)"))
        self.assertLess(body.index("_rebuild_v132_indexes_with_metrics"), body.index("current_populate_all(self)"))
        self.assertLess(body.index("current_populate_all(self)"), body.index("_schedule_v132_auction_cards"))
        self.assertLess(body.index("_schedule_v132_auction_cards"), body.index("_write_v132_population_performance"))


if __name__ == "__main__":
    unittest.main()
