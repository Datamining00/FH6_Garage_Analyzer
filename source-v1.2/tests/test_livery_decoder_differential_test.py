from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from fh6garage.livery_decoder_differential_test import (
    CURRENT_KFPS_COMMIT,
    LEGACY_KFPS_COMMIT,
    _legacy_cgroup_dir,
    compare_decoded_sources,
)


ROOT = Path(__file__).resolve().parents[1]


class DecoderDifferentialTests(unittest.TestCase):
    def test_both_decoder_versions_are_pinned(self):
        self.assertEqual(LEGACY_KFPS_COMMIT, "8965780b8966e09d2f2a17e4d0684cdd44d7437c")
        self.assertEqual(CURRENT_KFPS_COMMIT, "004b3b61a57d901e65957b6099805835f91e32f6")
        cgroup = _legacy_cgroup_dir()
        self.assertTrue((cgroup / "forza_source_decoder.py").is_file())
        self.assertTrue((cgroup / "shape_identity.py").is_file())

    def test_compare_reports_count_order_and_semantic_differences(self):
        legacy = SimpleNamespace(
            layers=[
                {"source_section": "Left", "source_offset": 10, "type": 1048677, "data": [0, 0, 1, 1, 0, 0, 0], "color": [0, 0, 0, 255], "mask": False},
                {"source_section": "Left", "source_offset": 20, "type": 1048678, "data": [1, 0, 1, 1, 0, 0, 0], "color": [0, 0, 0, 255], "mask": False},
            ],
            report={"warnings": []},
        )
        current = SimpleNamespace(
            layers=[
                {"source_section": "Left", "source_offset": 20, "type": 1048678, "data": [2, 0, 1, 1, 0, 0, 0], "color": [0, 0, 0, 255], "mask": False},
                {"source_section": "Left", "source_offset": 30, "type": 1048679, "data": [0, 0, 1, 1, 0, 0, 0], "color": [0, 0, 0, 255], "mask": False},
            ],
            report={"warnings": []},
        )
        result = compare_decoded_sources(legacy, current)
        self.assertEqual(result["summary"]["only_legacy_count"], 1)
        self.assertEqual(result["summary"]["only_current_count"], 1)
        self.assertEqual(result["summary"]["semantic_difference_count"], 1)
        self.assertEqual(result["sections"]["Left"]["legacy_count"], 2)
        self.assertEqual(result["sections"]["Left"]["current_count"], 2)
        self.assertEqual(result["sections"]["Left"]["first_order_divergence"]["index"], 0)

    def test_app_installs_differential_after_clean_baseline(self):
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        clean = app.index("apply_kfps_3_1_31_clean_baseline()")
        diff = app.index("apply_livery_decoder_differential_test(MainWindow)")
        self.assertGreater(diff, clean)

    def test_spec_bundles_legacy_decoder_as_data_not_import_path(self):
        spec = (ROOT / "FH6_Assistant_v1.4.spec").read_text(encoding="utf-8")
        self.assertIn("vendor/kfps_legacy/tools/cgroup", spec)
        self.assertIn("forza_source_decoder.py", spec)
        self.assertNotIn("str(legacy_root), str(project_root)", spec)


if __name__ == "__main__":
    unittest.main()
