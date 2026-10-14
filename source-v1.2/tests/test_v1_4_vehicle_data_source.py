from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fh6garage.acquisition_db import AcquisitionDatabase
from fh6garage.car_db import CarDatabase
from fh6garage.v1_4_vehicle_data_source_patch import (
    HDR_SOURCE,
    USER_SOURCE,
    USER_DATA_ACQUISITION_URL,
    USER_DATA_DLC_URL,
    USER_DATA_MANIFEST_URL,
    USER_DATA_NAMES_URL,
    _fetch_user_vehicle_update,
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
    def test_source_normalization(self):
        self.assertEqual(normalize_vehicle_data_source("HDR"), HDR_SOURCE)
        self.assertEqual(normalize_vehicle_data_source("user"), USER_SOURCE)
        self.assertEqual(normalize_vehicle_data_source("unknown"), "")

    def test_fresh_start_defaults_to_hdr_without_persisting_or_prompting(self):
        with tempfile.TemporaryDirectory() as td:
            settings = _Settings()
            self.assertEqual(
                resolve_vehicle_data_source(
                    settings,
                    Path(td) / "missing",
                    parent=object(),
                ),
                HDR_SOURCE,
            )
            self.assertEqual(settings.writes, [])

    def test_saved_hdr_source_is_reused_without_prompt(self):
        settings = _Settings(HDR_SOURCE)
        self.assertEqual(
            resolve_vehicle_data_source(settings, Path("unused")),
            HDR_SOURCE,
        )
        self.assertEqual(settings.writes, [])

    def test_saved_user_source_is_reused_even_when_bundled_dataset_missing(self):
        settings = _Settings(USER_SOURCE)
        self.assertEqual(
            resolve_vehicle_data_source(settings, Path("missing")),
            USER_SOURCE,
        )
        self.assertEqual(settings.writes, [])

    def test_public_user_data_urls_target_readable_main_snapshot(self):
        for url in (
            USER_DATA_MANIFEST_URL,
            USER_DATA_NAMES_URL,
            USER_DATA_ACQUISITION_URL,
            USER_DATA_DLC_URL,
        ):
            self.assertIn("Datamining00/FH6-Assistant-Data/main/vehicle_data/", url)

    def test_user_update_writes_common_car_cache_and_supplemental_cache(self):
        manifest = {
            "version": 1,
            "vehicle_count": 500,
            "format": "fh6-assistant-readable-v1",
        }
        names = {f"Car {car_id}": str(car_id) for car_id in range(1, 501)}
        acquisition = {str(car_id): "Autoshow" for car_id in range(1, 501)}
        dlc = {"500": "Car Pass"}
        responses = [
            (manifest, "manifest-date"),
            (names, "names-date"),
            (acquisition, ""),
            (dlc, ""),
        ]

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            car_cache = root / "fh6_car_ordinals.json"
            supplemental_cache = root / "fh6_cars.json"
            with patch(
                "fh6garage.v1_4_vehicle_data_source_patch._download_json",
                side_effect=responses,
            ):
                result = _fetch_user_vehicle_update(
                    car_cache,
                    supplemental_cache,
                )

            self.assertEqual(result.source, USER_SOURCE)
            self.assertEqual(result.count, 500)
            car_payload = json.loads(car_cache.read_text(encoding="utf-8"))
            self.assertEqual(car_payload["source_kind"], USER_SOURCE)
            self.assertEqual(car_payload["count"], 500)
            self.assertEqual(car_payload["cars"]["1"], "Car 1")

            supplemental = json.loads(
                supplemental_cache.read_text(encoding="utf-8")
            )
            self.assertEqual(supplemental["n"], 500)
            self.assertEqual(len(supplemental["c"]), 500)
            self.assertEqual(
                AcquisitionDatabase(supplemental_cache).get(500).dlc_name,
                "Car Pass",
            )

    def test_update_source_patch_does_not_replace_car_database_at_startup(self):
        text = Path("fh6garage/v1_4_vehicle_data_source_patch.py").read_text(
            encoding="utf-8"
        )
        patched_init = text.split("def patched_init", 1)[1].split(
            "@Slot()\n    def start_car_db_update", 1
        )[0]
        self.assertNotIn("UserVehicleDatabase", patched_init)
        self.assertNotIn("self.car_db =", patched_init)
        self.assertIn("resolve_vehicle_data_source", patched_init)

    def test_source_choice_occurs_only_in_explicit_update_action(self):
        text = Path("fh6garage/v1_4_vehicle_data_source_patch.py").read_text(
            encoding="utf-8"
        )
        resolver = text.split("def resolve_vehicle_data_source", 1)[1].split(
            "def _utc_now", 1
        )[0]
        update_action = text.split("def start_car_db_update", 1)[1].split(
            "@Slot(object)", 1
        )[0]
        self.assertNotIn("QMessageBox", resolver)
        self.assertNotIn("_choose_update_source", resolver)
        self.assertIn("_choose_update_source(self)", update_action)

    def test_vehicle_source_reuses_acquisition_ui_index_when_present(self):
        text = Path("fh6garage/v1_4_vehicle_data_source_patch.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("AcquisitionDatabase", text)
        self.assertIn("self.acquisition_db.reload()", text)

    def test_patch_order_places_vehicle_source_after_acquisition_and_before_performance_probe(self):
        text = Path("fh6garage/v1_3_4_backup_action_wording_patch.py").read_text(
            encoding="utf-8"
        )
        acquisition = text.rindex("apply_v1_4_acquisition_ui_patch(MainWindow)")
        vehicle = text.rindex("apply_v1_4_vehicle_data_source_patch(MainWindow)")
        profiler = text.rindex("apply_v1_3_4_performance_probe_patch(MainWindow)")
        self.assertLess(acquisition, vehicle)
        self.assertLess(vehicle, profiler)

        app = Path("app.py").read_text(encoding="utf-8")
        wording = app.rindex(
            "apply_v1_3_4_backup_action_wording_patch(MainWindow)"
        )
        final_affinity = app.rindex(
            "apply_v1_3_2_thread_affinity_fix(MainWindow)"
        )
        self.assertLess(wording, final_affinity)


if __name__ == "__main__":
    unittest.main()
