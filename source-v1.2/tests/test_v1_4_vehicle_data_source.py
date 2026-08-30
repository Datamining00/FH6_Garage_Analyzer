from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fh6garage.v1_4_vehicle_data_source_patch import (
    HDR_SOURCE,
    USER_SOURCE,
    UserVehicleDatabase,
    normalize_vehicle_data_source,
    resolve_vehicle_data_source,
)


class _Settings:
    def __init__(self, value: str = "") -> None:
        self.saved = value
        self.writes: list[tuple[str, str]] = []

    def value(self, _key, default="", _type=str):
        return self.saved if self.saved else default

    def setValue(self, key, value) -> None:
        self.saved = str(value)
        self.writes.append((str(key), str(value)))


class V14VehicleDataSourceTests(unittest.TestCase):
    def _write_dataset(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        (path / "cars").mkdir()
        metadata = {"v": 1, "n": 2, "a": ["Autoshow", "Seasonal"], "d": []}
        rows = [[100, "Dataset Car A", 0, 0], [200, "Dataset Car B", 1, 0]]
        (path / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
        (path / "cars" / "cars_01.json").write_text(json.dumps({"rows": rows}), encoding="utf-8")

    def test_source_normalization(self):
        self.assertEqual(normalize_vehicle_data_source("HDR"), HDR_SOURCE)
        self.assertEqual(normalize_vehicle_data_source("user"), USER_SOURCE)
        self.assertEqual(normalize_vehicle_data_source("unknown"), "")

    def test_user_database_uses_dataset_name_and_keeps_override_priority(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data = root / "vehicle_data"
            app_data = root / "local"
            self._write_dataset(data)
            db = UserVehicleDatabase(data, app_data_dir=app_data)
            self.assertEqual(db.base_label(100), "Dataset Car A")
            self.assertEqual(db.get(100).label, "Dataset Car A")
            db.set_user_override(100, "My Override")
            self.assertEqual(db.base_label(100), "Dataset Car A")
            self.assertEqual(db.get(100).label, "My Override")
            self.assertEqual(db.status.cached_count, 0)

    def test_saved_hdr_source_is_reused_without_prompt(self):
        with tempfile.TemporaryDirectory() as td:
            data = Path(td) / "vehicle_data"
            self._write_dataset(data)
            settings = _Settings(HDR_SOURCE)
            self.assertEqual(resolve_vehicle_data_source(settings, data), HDR_SOURCE)
            self.assertEqual(settings.writes, [])

    def test_saved_user_source_is_reused(self):
        with tempfile.TemporaryDirectory() as td:
            data = Path(td) / "vehicle_data"
            self._write_dataset(data)
            settings = _Settings(USER_SOURCE)
            self.assertEqual(resolve_vehicle_data_source(settings, data), USER_SOURCE)
            self.assertEqual(settings.writes, [])

    def test_saved_user_source_falls_back_to_hdr_when_dataset_missing(self):
        with tempfile.TemporaryDirectory() as td:
            settings = _Settings(USER_SOURCE)
            missing = Path(td) / "missing"
            self.assertEqual(resolve_vehicle_data_source(settings, missing), HDR_SOURCE)
            self.assertEqual(settings.saved, USER_SOURCE)
            self.assertEqual(settings.writes, [])

    def test_smoke_test_defaults_to_hdr_without_persisting(self):
        with tempfile.TemporaryDirectory() as td:
            data = Path(td) / "vehicle_data"
            self._write_dataset(data)
            settings = _Settings()
            with patch.dict(os.environ, {"FH6_ASSISTANT_SMOKE_TEST_MS": "3000"}):
                self.assertEqual(resolve_vehicle_data_source(settings, data), HDR_SOURCE)
            self.assertEqual(settings.writes, [])

    def test_vehicle_source_reuses_acquisition_ui_index_when_present(self):
        text = Path("fh6garage/v1_4_vehicle_data_source_patch.py").read_text(encoding="utf-8")
        self.assertIn('if not isinstance(getattr(self, "acquisition_db", None), AcquisitionDatabase):', text)
        self.assertIn("self.acquisition_db = AcquisitionDatabase(user_data_path)", text)

    def test_patch_order_places_vehicle_source_after_acquisition_and_before_performance_probe(self):
        text = Path("fh6garage/v1_3_4_backup_action_wording_patch.py").read_text(encoding="utf-8")
        acquisition = text.rindex("apply_v1_4_acquisition_ui_patch(MainWindow)")
        vehicle = text.rindex("apply_v1_4_vehicle_data_source_patch(MainWindow)")
        profiler = text.rindex("apply_v1_3_4_performance_probe_patch(MainWindow)")
        self.assertLess(acquisition, vehicle)
        self.assertLess(vehicle, profiler)

        app = Path("app.py").read_text(encoding="utf-8")
        wording = app.rindex("apply_v1_3_4_backup_action_wording_patch(MainWindow)")
        final_affinity = app.rindex("apply_v1_3_2_thread_affinity_fix(MainWindow)")
        self.assertLess(wording, final_affinity)


if __name__ == "__main__":
    unittest.main()
