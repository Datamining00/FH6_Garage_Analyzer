from __future__ import annotations

import unittest
from pathlib import Path


class V14PrivateDataReleaseContractTests(unittest.TestCase):
    def test_private_dataset_staging_path_is_gitignored(self):
        ignore = Path("../.gitignore").read_text(encoding="utf-8")
        self.assertIn("source-v1.2/data/fh6_cars.json.gz", ignore.splitlines())

    def test_build_fetcher_requires_authorized_private_repo_access(self):
        text = Path("tools/fetch_supplemental_car_data.py").read_text(encoding="utf-8")
        self.assertIn("Datamining00/FH6-Assistant-Data", text)
        self.assertIn("FH6_ASSISTANT_DATA_TOKEN", text)
        self.assertIn("AcquisitionDatabase._parse_payload(payload)", text)
        self.assertNotIn("github_pat_", text)
        self.assertNotIn("ghp_", text)

    def test_v14_specs_bundle_supplemental_data_only_when_staged(self):
        for name in ("FH6_Assistant_v1.4.spec", "FH6_Assistant_v1.4_portable.spec"):
            text = Path(name).read_text(encoding="utf-8")
            self.assertIn("fh6_cars.json.gz", text)
            self.assertIn("supplemental_data.is_file()", text)
            self.assertIn("datas.append((str(supplemental_data), 'data'))", text)

    def test_workflow_stages_private_data_without_hardcoded_credentials(self):
        workflow = Path("../.github/workflows/build-v1.3.3-beta.yml").read_text(encoding="utf-8")
        self.assertIn("FH6_ASSISTANT_DATA_TOKEN: ${{ secrets.FH6_ASSISTANT_DATA_TOKEN }}", workflow)
        self.assertIn("Stage private supplemental car data", workflow)
        self.assertIn("fetch_supplemental_car_data.py", workflow)
        self.assertIn("Supplemental acquisition data not staged", workflow)

    def test_runtime_uses_bundled_snapshot_without_replacing_hdr_names(self):
        ui = Path("fh6garage/v1_4_acquisition_ui_patch.py").read_text(encoding="utf-8")
        db = Path("fh6garage/acquisition_db.py").read_text(encoding="utf-8")
        self.assertIn('self.project_root / "data" / "fh6_cars.json.gz"', ui)
        self.assertIn("self.acquisition_db = AcquisitionDatabase(bundled)", ui)
        self.assertIn("HDR remains the authoritative vehicle-name database", db)


if __name__ == "__main__":
    unittest.main()
