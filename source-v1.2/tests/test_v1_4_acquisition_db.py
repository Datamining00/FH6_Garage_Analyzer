from __future__ import annotations

import gzip
import json
import tempfile
import unittest
from pathlib import Path

from fh6garage.acquisition_db import AcquisitionDatabase


class V14AcquisitionDatabaseTests(unittest.TestCase):
    def _payload(self) -> dict[str, object]:
        return {
            "v": 1,
            "n": 3,
            "a": ["Autoshow, Wheelspin", "Collection Journal", "Autoshow DLC"],
            "d": ["Car Pass"],
            "c": [
                [100, "Car A", 0, 0],
                [200, "Car B", 1, 0],
                [300, "Car C", 2, 1],
            ],
        }

    def _write_json(self, path: Path, payload: dict[str, object] | None = None) -> None:
        path.write_text(json.dumps(payload or self._payload()), encoding="utf-8")

    def _write_directory(self, path: Path, payload: dict[str, object] | None = None) -> None:
        data = dict(payload or self._payload())
        rows = data.pop("c")
        path.mkdir(parents=True, exist_ok=True)
        (path / "cars").mkdir()
        (path / "metadata.json").write_text(json.dumps(data), encoding="utf-8")
        (path / "cars" / "cars_01.json").write_text(json.dumps({"rows": rows[:2]}), encoding="utf-8")
        (path / "cars" / "cars_02.json").write_text(json.dumps({"rows": rows[2:]}), encoding="utf-8")

    def test_directory_schema_builds_o1_car_id_index(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bundled = root / "bundled"
            missing_cache = root / "missing" / "fh6_cars.json"
            self._write_directory(bundled)
            db = AcquisitionDatabase(bundled, cache_path=missing_cache)
            self.assertEqual(len(db), 3)
            self.assertEqual(db.get(100).acquisition, "Autoshow, Wheelspin")
            self.assertEqual(db.get(100).methods, ("Autoshow", "Wheelspin"))
            self.assertEqual(db.get(300).dlc_name, "Car Pass")
            self.assertIsNone(db.get(999))
            self.assertIsInstance(db._items, dict)

    def test_local_cache_takes_precedence_over_bundled_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bundled = root / "bundled"
            cache = root / "cache.json"
            self._write_directory(bundled)
            payload = {"v": 1, "n": 1, "a": ["Seasonal"], "d": [], "c": [[100, "Cache Car", 0, 0]]}
            self._write_json(cache, payload)
            db = AcquisitionDatabase(bundled, cache_path=cache)
            self.assertEqual(db.get(100).dataset_name, "Cache Car")
            self.assertEqual(db.get(100).acquisition, "Seasonal")
            self.assertEqual(db.loaded_path, cache)

    def test_legacy_gzip_cache_remains_readable(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bundled = root / "bundled"
            cache = root / "fh6_cars.json"
            legacy = root / "fh6_cars.json.gz"
            self._write_directory(bundled)
            payload = {"v": 1, "n": 1, "a": ["Seasonal"], "d": [], "c": [[100, "Legacy Car", 0, 0]]}
            with gzip.open(legacy, "wt", encoding="utf-8") as stream:
                json.dump(payload, stream)
            db = AcquisitionDatabase(bundled, cache_path=cache)
            self.assertEqual(db.get(100).dataset_name, "Legacy Car")
            self.assertEqual(db.loaded_path, legacy)


if __name__ == "__main__":
    unittest.main()
