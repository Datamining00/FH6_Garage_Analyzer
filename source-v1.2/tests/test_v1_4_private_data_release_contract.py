from __future__ import annotations

import unittest
from pathlib import Path


class V14PrivateDataReleaseContractTests(unittest.TestCase):
    def test_legacy_private_gzip_staging_path_remains_gitignored(self):
        ignore = Path("../.gitignore").read_text(encoding="utf-8")
        self.assertIn("source-v1.2/data/fh6_cars.json.gz", ignore.splitlines())

    def test_private_fetcher_is_maintenance_only_and_has_no_hardcoded_credentials(self):
        text = Path("tools/fetch_supplemental_car_data.py").read_text(encoding="utf-8")
        self.assertIn("Datamining00/FH6-Assistant-Data", text)
        self.assertIn("FH6_ASSISTANT_DATA_TOKEN", text)
        self.assertNotIn("github_pat_", text)
        self.assertNotIn("ghp_", text)

    def test_v14_specs_bundle_committed_uncompressed_vehicle_directory(self):
        for name in ("FH6_Assistant_v1.4.spec", "FH6_Assistant_v1.4_portable.spec"):
            text = Path(name).read_text(encoding="utf-8")
            self.assertIn("fh6_assistant_vehicle_data", text)
            self.assertIn("vehicle_data.is_dir()", text)
            self.assertIn("data/fh6_assistant_vehicle_data", text)
            self.assertNotIn("fh6_cars.json.gz", text)

    def test_workflow_does_not_depend_on_private_data_secret(self):
        workflow = Path("../.github/workflows/build-v1.3.3-beta.yml").read_text(encoding="utf-8")
        self.assertNotIn("FH6_ASSISTANT_DATA_TOKEN", workflow)
        self.assertNotIn("Stage private supplemental car data", workflow)
        self.assertIn("Verify committed vehicle data", workflow)
        self.assertIn("fh6_assistant_vehicle_data", workflow)

    def test_runtime_loader_supports_committed_directory_and_legacy_cache(self):
        db = Path("fh6garage/acquisition_db.py").read_text(encoding="utf-8")
        self.assertIn('DATA_DIR_NAME = "fh6_assistant_vehicle_data"', db)
        self.assertIn('LEGACY_DATA_FILE_NAME = "fh6_cars.json.gz"', db)
        self.assertIn('cars_dir.glob("*.json")', db)


if __name__ == "__main__":
    unittest.main()
