from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fh6garage.v1_4_vehicle_source_database import SourceAwareCarDatabase


class V14VehicleSourceDatabaseTests(unittest.TestCase):
    def _write_user_data(self, root: Path) -> Path:
        data = root / "user_data"
        (data / "cars").mkdir(parents=True)
        (data / "metadata.json").write_text(
            json.dumps({"v": 1, "n": 2, "a": ["Autoshow"], "d": []}),
            encoding="utf-8",
        )
        (data / "cars" / "cars_01.json").write_text(
            json.dumps({"rows": [[1, "User One", 0, 0], [2, "User Two", 0, 0]]}),
            encoding="utf-8",
        )
        return data

    def _write_hdr_data(self, root: Path) -> Path:
        path = root / "car_names.json"
        path.write_text(json.dumps({"1": "HDR One", "3": "HDR Three"}), encoding="utf-8")
        return path

    def test_user_source_reads_committed_directory_names_directly(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = SourceAwareCarDatabase(
                self._write_hdr_data(root),
                source="user",
                user_data_path=self._write_user_data(root),
                app_data_dir=root / "appdata",
            )
            self.assertEqual(db.get(1).label, "User One")
            self.assertEqual(db.get(2).label, "User Two")
            self.assertFalse(db.is_known(3))

    def test_hdr_source_does_not_consume_newer_user_cache(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            appdata = root / "appdata"
            appdata.mkdir()
            (appdata / "fh6_car_ordinals.json").write_text(
                json.dumps({
                    "schema": 1,
                    "source_kind": "user",
                    "downloaded_at": "2099-01-01T00:00:00Z",
                    "count": 1,
                    "cars": {"1": "Cached User One"},
                }),
                encoding="utf-8",
            )
            db = SourceAwareCarDatabase(
                self._write_hdr_data(root),
                source="hdr",
                user_data_path=self._write_user_data(root),
                app_data_dir=appdata,
            )
            self.assertEqual(db.get(1).label, "HDR One")

    def test_user_source_ignores_hdr_cache_without_user_source_marker(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            appdata = root / "appdata"
            appdata.mkdir()
            (appdata / "fh6_car_ordinals.json").write_text(
                json.dumps({
                    "schema": 1,
                    "downloaded_at": "2099-01-01T00:00:00Z",
                    "count": 1,
                    "cars": {"1": "Cached HDR One"},
                }),
                encoding="utf-8",
            )
            db = SourceAwareCarDatabase(
                self._write_hdr_data(root),
                source="user",
                user_data_path=self._write_user_data(root),
                app_data_dir=appdata,
            )
            self.assertEqual(db.get(1).label, "User One")


if __name__ == "__main__":
    unittest.main()
