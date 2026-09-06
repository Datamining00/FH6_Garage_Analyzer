from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "run_wheel_morph_bake_diagnostic.py"
LAUNCHER = ROOT / "tools" / "Run_FER_FXX_05_Wheel_Morph_Bake_Diagnostic.cmd"


def _load_script():
    spec = importlib.util.spec_from_file_location("wheel_morph_bake_diagnostic", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WheelMorphBakeDiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = _load_script()

    def test_fxx_candidate_weights_use_published_rim_formula(self):
        front = self.module.rim_morph_weights(19, 245)
        rear = self.module.rim_morph_weights(19, 345)
        self.assertAlmostEqual(front[0], 9.0 / 14.0)
        self.assertAlmostEqual(front[1], 0.755 / 0.9)
        self.assertAlmostEqual(rear[0], 9.0 / 14.0)
        self.assertAlmostEqual(rear[1], 0.655 / 0.9)

    def test_carbin_resolution_reads_zip_without_rewriting_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "FER_FXX_05.zip"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("FER_FXX_05.carbin", b"scene")
                output.writestr("Scene/test.modelbin", b"model")
            before = self.module.sha256_file(archive)
            self.assertEqual(self.module.resolve_carbin_entry(archive), "FER_FXX_05.carbin")
            self.assertEqual(before, self.module.sha256_file(archive))

    def test_wheelstyle_aabb_groups_by_structured_instance_identity(self):
        document = {
            "meshes": [
                {
                    "extras": {"kfps_part_type": "WheelStyle", "kfps_instance_identity": "rear"},
                    "primitives": [{"attributes": {"POSITION": 0}}],
                },
                {
                    "extras": {"kfps_part_type": "WheelStyle", "kfps_instance_identity": "rear"},
                    "primitives": [{"attributes": {"POSITION": 1}}],
                },
                {
                    "extras": {"kfps_part_type": "WheelStyle", "kfps_instance_identity": "front"},
                    "primitives": [{"attributes": {"POSITION": 2}}],
                },
                {
                    "extras": {"kfps_part_type": "CarBody", "kfps_instance_identity": "body"},
                    "primitives": [{"attributes": {"POSITION": 3}}],
                },
            ],
            "accessors": [
                {"min": [-1, 0, -2], "max": [0, 1, -1]},
                {"min": [0, -1, -2], "max": [2, 2, -1]},
                {"min": [-1, 0, 1], "max": [1, 2, 2]},
                {"min": [-9, -9, -9], "max": [9, 9, 9]},
            ],
        }
        rows = self.module.wheelstyle_aabbs(document)
        self.assertEqual(len(rows), 2)
        by_identity = {row["instance_identity"]: row for row in rows}
        self.assertEqual(by_identity["rear"]["span"], [3.0, 3.0, 1.0])
        self.assertEqual(by_identity["rear"]["axle_from_world_z"], "rear")
        self.assertEqual(by_identity["front"]["axle_from_world_z"], "front")

    def test_aabb_comparison_reports_span_and_center_deltas(self):
        baseline = [{
            "instance_identity": "wheel",
            "span": [1.0, 2.0, 3.0],
            "center": [4.0, 5.0, 6.0],
            "axle_from_world_z": "front",
        }]
        candidate = [{
            "instance_identity": "wheel",
            "span": [1.5, 2.0, 4.0],
            "center": [4.1, 5.0, 6.2],
        }]
        row = self.module.compare_aabbs(baseline, candidate)[0]
        self.assertEqual(row["span_delta"], [0.5, 0.0, 1.0])
        self.assertAlmostEqual(row["center_delta"][0], 0.1)
        self.assertAlmostEqual(row["center_delta"][2], 0.2)

    def test_launcher_is_fxx_candidate_only_and_has_no_geometry_scale_patch(self):
        launcher = LAUNCHER.read_text(encoding="utf-8")
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("--front-width-mm 245", launcher)
        self.assertIn("--rear-width-mm 345", launcher)
        self.assertIn("--front-wheel-diameter-in 19", launcher)
        self.assertIn("--rear-wheel-diameter-in 19", launcher)
        self.assertIn('"scale_x": 1.0', script)
        self.assertNotIn("tirecompound", script.casefold())
        self.assertNotIn("scale_x =", script.casefold())
        self.assertNotIn("0.1 *", script)


if __name__ == "__main__":
    unittest.main()
