from __future__ import annotations

import unittest
from pathlib import Path


class V14InitialVehicleSourceContractTests(unittest.TestCase):
    def test_fresh_v14_install_has_explicit_two_source_choice(self):
        text = Path("fh6garage/v1_4_initial_vehicle_source_patch.py").read_text(encoding="utf-8")
        self.assertIn('box.addButton("저장소1(HDR)"', text)
        self.assertIn('box.addButton("저장소2(내 차량 데이터)"', text)
        self.assertIn("_choose_initial_source(self)", text)
        self.assertIn("self.settings.setValue(_source.VEHICLE_DATA_SOURCE_KEY, selected)", text)

    def test_smoke_test_bypasses_modal_without_persisting_choice(self):
        text = Path("fh6garage/v1_4_initial_vehicle_source_patch.py").read_text(encoding="utf-8")
        self.assertIn('os.environ.get("FH6_ASSISTANT_SMOKE_TEST_MS", "").strip()', text)
        smoke_branch = text.split('if os.environ.get("FH6_ASSISTANT_SMOKE_TEST_MS", "").strip():', 1)[1].split('else:', 1)[0]
        self.assertIn("selected = _source.HDR_SOURCE", smoke_branch)
        self.assertNotIn("settings.setValue", smoke_branch)

    def test_saved_choice_bypasses_first_run_prompt(self):
        text = Path("fh6garage/v1_4_initial_vehicle_source_patch.py").read_text(encoding="utf-8")
        body = text.split("def patched_init", 1)[1]
        self.assertIn("if not selected:", body)
        self.assertLess(body.index("if not selected:"), body.index("_choose_initial_source(self)"))

    def test_selected_source_rebuilds_the_actual_car_database(self):
        text = Path("fh6garage/v1_4_initial_vehicle_source_patch.py").read_text(encoding="utf-8")
        self.assertIn("SourceAwareCarDatabase", text)
        self.assertIn("source=source", text)
        self.assertIn("user_data_path=user_data_path", text)
        self.assertIn("self.car_db = _selected_database(self, selected, user_data_path)", text)

    def test_missing_user_dataset_falls_back_to_hdr_and_persists_fallback(self):
        text = Path("fh6garage/v1_4_initial_vehicle_source_patch.py").read_text(encoding="utf-8")
        self.assertIn("self.car_db.status.built_in_count < 500", text)
        self.assertIn("selected = _source.HDR_SOURCE", text)
        self.assertIn("self.settings.setValue(_source.VEHICLE_DATA_SOURCE_KEY, selected)", text)

    def test_first_run_patch_is_installed_after_update_thread_bridge(self):
        text = Path("fh6garage/v1_4_vehicle_update_thread_bridge_patch.py").read_text(encoding="utf-8")
        self.assertIn("apply_v1_4_initial_vehicle_source_patch(MainWindow)", text)
        self.assertLess(
            text.index("MainWindow.start_car_db_update = start_car_db_update"),
            text.index("apply_v1_4_initial_vehicle_source_patch(MainWindow)"),
        )

    def test_update_completion_keeps_source_aware_database(self):
        text = Path("fh6garage/v1_4_vehicle_update_finish_ui_patch.py").read_text(encoding="utf-8")
        self.assertIn("SourceAwareCarDatabase", text)
        self.assertIn("source=source", text)
        self.assertNotIn("self.car_db = CarDatabase(", text)


if __name__ == "__main__":
    unittest.main()
