from __future__ import annotations

import unittest
from pathlib import Path


class V14VehicleRuntimeUpdateTests(unittest.TestCase):
    def test_user_update_uses_single_gist_snapshot(self):
        text = Path("fh6garage/v1_4_vehicle_runtime_update_patch.py").read_text(encoding="utf-8")
        self.assertIn('USER_DATA_GIST_ID = "30fe44689fad7ba5e99e2381927b7730"', text)
        self.assertIn('USER_DATA_GIST_FILENAME = "FH6 Vehicle Data.json"', text)
        self.assertIn('https://gist.githubusercontent.com/Datamining00/', text)
        self.assertIn('quote(USER_DATA_GIST_FILENAME)', text)
        self.assertEqual(text.count("_source._download_json("), 1)
        self.assertNotIn("USER_DATA_MANIFEST_URL", text)
        self.assertNotIn("USER_DATA_NAMES_URL", text)
        self.assertNotIn("USER_DATA_ACQUISITION_URL", text)
        self.assertNotIn("USER_DATA_DLC_URL", text)

    def test_gist_request_bypasses_intermediary_cache(self):
        text = Path("fh6garage/v1_4_vehicle_runtime_update_patch.py").read_text(encoding="utf-8")
        self.assertIn("def _latest_gist_raw_url()", text)
        self.assertIn('?ts={_source._utc_now()}', text)
        self.assertIn("request_url = _latest_gist_raw_url()", text)
        self.assertIn("_source._download_json(request_url, timeout)", text)

    def test_gist_snapshot_validates_vehicle_and_supplemental_fields(self):
        text = Path("fh6garage/v1_4_vehicle_runtime_update_patch.py").read_text(encoding="utf-8")
        self.assertIn('raw_info.get("id")', text)
        self.assertIn('raw_info.get("acquisition")', text)
        self.assertIn('raw_info.get("dlc", False)', text)
        self.assertIn('raw_info.get("dlc_name")', text)
        self.assertIn("duplicate Car ID in Gist data", text)
        self.assertIn("DLC name missing for Car ID", text)
        self.assertIn("_source._atomic_write_json", text)

    def test_runtime_patch_replaces_worker_fetch_before_finish_patch(self):
        runtime = Path("fh6garage/v1_4_vehicle_runtime_update_patch.py").read_text(encoding="utf-8")
        self.assertIn("_source._fetch_user_vehicle_update = _fetch_runtime_vehicle_update", runtime)

        chain = Path("fh6garage/v1_3_4_backup_action_wording_patch.py").read_text(encoding="utf-8")
        source = chain.rindex("apply_v1_4_vehicle_data_source_patch(MainWindow)")
        runtime_pos = chain.rindex("apply_v1_4_vehicle_runtime_update_patch(MainWindow)")
        finish = chain.rindex("apply_v1_4_vehicle_update_finish_ui_patch(MainWindow)")
        profiler = chain.rindex("apply_v1_3_4_performance_probe_patch(MainWindow)")
        self.assertLess(source, runtime_pos)
        self.assertLess(runtime_pos, finish)
        self.assertLess(finish, profiler)


if __name__ == "__main__":
    unittest.main()
