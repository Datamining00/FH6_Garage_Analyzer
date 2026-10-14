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

    def test_wheelstyle_aabb_groups_visible_structured_instances_only(self):
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
                    "extras": {
                        "kfps_part_type": "WheelStyle",
                        "kfps_instance_identity": "rear",
                        "kfps_role": "hidden",
                    },
                    "primitives": [{"attributes": {"POSITION": 3}}],
                },
                {
                    "extras": {"kfps_part_type": "CarBody", "kfps_instance_identity": "body"},
                    "primitives": [{"attributes": {"POSITION": 4}}],
                },
            ],
            "accessors": [
                {"min": [-1, 0, -2], "max": [0, 1, -1]},
                {"min": [0, -1, -2], "max": [2, 2, -1]},
                {"min": [-1, 0, 1], "max": [1, 2, 2]},
                {"min": [-50, -50, -50], "max": [50, 50, 50]},
                {"min": [-9, -9, -9], "max": [9, 9, 9]},
            ],
        }
        rows = self.module.wheelstyle_aabbs(document)
        self.assertEqual(len(rows), 2)
        by_identity = {row["instance_identity"]: row for row in rows}
        self.assertEqual(by_identity["rear"]["span"], [3.0, 3.0, 1.0])
        self.assertEqual(by_identity["rear"]["axle_from_world_z"], "rear")
        self.assertEqual(by_identity["front"]["axle_from_world_z"], "front")

        with_hidden = self.module.wheelstyle_aabbs(document, include_hidden=True)
        hidden_map = {row["instance_identity"]: row for row in with_hidden}
        self.assertEqual(hidden_map["rear"]["span"], [100.0, 100.0, 100.0])

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

    def test_converter_json_parses_pretty_printed_payload(self):
        stdout = """{
  "format": "kfps_local_chassis_conversion_v5",
  "wheel_morph_mode": "combined",
  "wheel_morph_applied_meshes": 33,
  "wheel_morph_applied_vertices": 6736
}
"""
        payload = self.module._converter_json(stdout)
        self.assertIsInstance(payload, dict)
        self.assertEqual(payload["wheel_morph_mode"], "combined")
        self.assertEqual(payload["wheel_morph_applied_meshes"], 33)

    def test_converter_diagnostics_fail_closed_for_unpatched_or_inactive_build(self):
        with self.assertRaises(RuntimeError):
            self.module.validate_converter_diagnostics("combined", {})
        with self.assertRaises(RuntimeError):
            self.module.validate_converter_diagnostics("combined", {
                "wheel_morph_mode": "width",
                "wheel_morph_applied_meshes": 1,
                "wheel_morph_applied_vertices": 1,
            })
        with self.assertRaises(RuntimeError):
            self.module.validate_converter_diagnostics("combined", {
                "wheel_morph_mode": "combined",
                "wheel_morph_applied_meshes": 0,
                "wheel_morph_applied_vertices": 100,
            })
        with self.assertRaises(RuntimeError):
            self.module.validate_converter_diagnostics("combined", {
                "wheel_morph_mode": "combined",
                "wheel_morph_applied_meshes": 10,
                "wheel_morph_applied_vertices": 0,
            })

    def test_converter_diagnostics_accept_verified_none_and_combined_modes(self):
        self.module.validate_converter_diagnostics("none", {
            "wheel_morph_mode": "none",
            "wheel_morph_applied_meshes": 0,
            "wheel_morph_applied_vertices": 0,
        })
        self.module.validate_converter_diagnostics("combined", {
            "wheel_morph_mode": "combined",
            "wheel_morph_applied_meshes": 33,
            "wheel_morph_applied_vertices": 6736,
        })

    def test_launcher_reuses_structural_neutral_wheel_visibility(self):
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("apply_neutral_wheel_visibility", script)
        self.assertIn('"neutral_wheel_visibility"', script)
        self.assertIn('"aabb_scope"', script)
        self.assertIn('kfps_role") or "").casefold() == "hidden"', script)

    def test_launcher_fails_closed_on_identical_outputs_and_records_v2_hashes(self):
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("wheel morph output remained byte-identical to baseline", script)
        self.assertIn('"output_sha256"', script)
        self.assertIn('"fh6_wheel_morph_four_way_diagnostic_v2"', script)
        self.assertIn("validate_converter_diagnostics(mode, converter_json)", script)

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
