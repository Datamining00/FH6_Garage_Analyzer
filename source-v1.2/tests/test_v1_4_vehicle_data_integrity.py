from __future__ import annotations

import json
import unittest
from pathlib import Path

from fh6garage.acquisition_db import AcquisitionDatabase, load_vehicle_data_payload


class V14VehicleDataIntegrityTests(unittest.TestCase):
    def test_committed_dataset_is_complete_and_indexable(self):
        root = Path("data/fh6_assistant_vehicle_data")
        self.assertTrue((root / "metadata.json").is_file())
        chunks = sorted((root / "cars").glob("*.json"))
        self.assertEqual(len(chunks), 9)

        payload = load_vehicle_data_payload(root)
        self.assertEqual(payload.get("v"), 1)
        self.assertEqual(payload.get("n"), 660)
        self.assertEqual(len(payload.get("c", [])), 660)
        self.assertEqual(len(payload.get("a", [])), 13)
        self.assertEqual(len(payload.get("d", [])), 7)

        rows = payload["c"]
        ids = [int(row[0]) for row in rows]
        self.assertEqual(len(set(ids)), 660)
        for row in rows:
            self.assertEqual(len(row), 4)
            self.assertTrue(str(row[1]).strip())
            self.assertGreaterEqual(int(row[2]), 0)
            self.assertLess(int(row[2]), len(payload["a"]))
            self.assertGreaterEqual(int(row[3]), 0)
            self.assertLessEqual(int(row[3]), len(payload["d"]))

        db = AcquisitionDatabase(root, cache_path=Path("__missing_v14_cache__.json"))
        self.assertEqual(len(db), 660)
        self.assertEqual(db.get(343).dataset_name, "1969 Nissan Fairlady Z 432")
        self.assertEqual(db.get(1283).dlc_name, "Car Pass")

    def test_dataset_files_are_plain_json_not_archives(self):
        root = Path("data/fh6_assistant_vehicle_data")
        for path in root.rglob("*"):
            if path.is_file():
                self.assertEqual(path.suffix.lower(), ".json")
                json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
