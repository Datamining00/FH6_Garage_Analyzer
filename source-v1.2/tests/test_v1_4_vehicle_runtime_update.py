from __future__ import annotations

import unittest
from pathlib import Path


class V14VehicleRuntimeUpdateTests(unittest.TestCase):
    def test_user_update_uses_single_runtime_snapshot(self):
        text = Path("fh6garage/v1_4_vehicle_runtime_update_patch.py").read_text(encoding="utf-8")
        self.assertIn('USER_DATA_RUNTIME_URL = f"{_source.USER_DATA_BASE_URL}/runtime.json"', text)
        self.assertIn('USER_DATA_RUNTIME_FORMAT = "fh6-assistant-runtime-v1"', text)
        self.assertEqual(text.count("_source._download_json("), 1)
        self.assertNotIn("USER_DATA_MANIFEST_URL", text)
        self.assertNotIn("USER_DATA_NAMES_URL", text)
        self.assertNotIn("USER_DATA_ACQUISITION_URL", text)
        self.assertNotIn("USER_DATA_DLC_URL", text)

    def test_runtime_snapshot_validates_all_three_tables(self):
        text = Path("fh6garage/v1_4_vehicle_runtime_update_patch.py").read_text(encoding="utf-8")
        self.assertIn('payload.get("car_names")', text)
        self.assertIn('payload.get("acquisition")', text)
        self.assertIn('payload.get("dlc")', text)
        self.assertIn("acquisition coverage mismatch", text)
        self.assertIn("DLC contains unknown Car IDs", text)
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
