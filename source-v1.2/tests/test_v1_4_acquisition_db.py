from __future__ import annotations

import gzip
import json
import tempfile
import unittest
from pathlib import Path

from fh6garage.acquisition_db import AcquisitionDatabase


class V14AcquisitionDatabaseTests(unittest.TestCase):
    def _write(self, path: Path) -> None:
        payload = {
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
        with gzip.open(path, "wt", encoding="utf-8") as stream:
            json.dump(payload, stream, separators=(",", ":"))

    def test_compact_schema_builds_o1_car_id_index(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bundled = root / "bundled.json.gz"
            missing_cache = root / "missing" / "fh6_cars.json.gz"
            self._write(bundled)
            db = AcquisitionDatabase(bundled, cache_path=missing_cache)
            self.assertEqual(len(db), 3)
            self.assertEqual(db.get(100).acquisition, "Autoshow, Wheelspin")
            self.assertEqual(db.get(100).methods, ("Autoshow", "Wheelspin"))
            self.assertEqual(db.get(300).dlc_name, "Car Pass")
            self.assertIsNone(db.get(999))

    def test_local_cache_takes_precedence_over_bundled_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bundled = root / "bundled.json.gz"
            cache = root / "cache.json.gz"
            self._write(bundled)
            payload = {"v": 1, "n": 1, "a": ["Seasonal"], "d": [], "c": [[100, "Cache Car", 0, 0]]}
            with gzip.open(cache, "wt", encoding="utf-8") as stream:
                json.dump(payload, stream)
            db = AcquisitionDatabase(bundled, cache_path=cache)
            self.assertEqual(db.get(100).dataset_name, "Cache Car")
            self.assertEqual(db.get(100).acquisition, "Seasonal")
            self.assertEqual(db.loaded_path, cache)


if __name__ == "__main__":
    unittest.main()
