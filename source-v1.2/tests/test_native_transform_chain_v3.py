from __future__ import annotations

import unittest

from fh6garage.preview3d import native_transform_chain_v3 as ntc3


def _audit(identity: str, low, high, count: int = 100) -> dict:
    return {
        "instance_identity": identity,
        "part_type": "WheelStyle",
        "vertex_count": count,
        "local_aabb_min": list(low),
        "local_aabb_max": list(high),
    }


class NativeTransformChainV3Tests(unittest.TestCase):
    def test_wheel_rim_fit_uses_rendered_instance_local_geometry(self) -> None:
        diagnostics = {
            "transform_audit": [
                _audit("wheel_a", (-0.12, -0.25, -0.25), (0.12, 0.25, 0.25), 400),
                _audit("wheel_a", (-0.10, -0.24, -0.24), (0.10, 0.24, 0.24), 200),
            ]
        }
        fit = ntc3._wheel_rim_fit("wheel_a", diagnostics)
        self.assertEqual(fit["axial_axis"], 0)
        self.assertEqual(fit["radial_axes"], [1, 2])
        self.assertAlmostEqual(fit["rendered_rim_outer_diameter_m"], 0.5, places=12)
        self.assertEqual(fit["local_center"], [0.0, 0.0, 0.0])
        self.assertEqual(fit["mesh_count"], 2)
        self.assertEqual(fit["vertex_count"], 600)

    def test_dynamic_rim_fit_aggregates_axle_without_vehicle_constants(self) -> None:
        anchors = [
            {"instance_identity": "left", "dynamic_axle_index": 0},
            {"instance_identity": "right", "dynamic_axle_index": 0},
        ]
        diagnostics = {
            "transform_audit": [
                _audit("left", (-0.11, -0.25, -0.25), (0.13, 0.25, 0.25)),
                _audit("right", (-0.13, -0.25, -0.25), (0.11, 0.25, 0.25)),
            ]
        }
        fits = ntc3._dynamic_rim_fits(anchors, diagnostics)
        self.assertEqual(set(fits), {0})
        self.assertEqual(fits[0]["wheel_count"], 2)
        self.assertEqual(fits[0]["local_center"], [0.0, 0.0, 0.0])
        self.assertAlmostEqual(fits[0]["rendered_rim_outer_diameter_m"], 0.5, places=12)

    def test_missing_local_geometry_fails_closed(self) -> None:
        with self.assertRaisesRegex(ntc3.NativeTransformChainV3Error, "instance-local geometry"):
            ntc3._wheel_rim_fit(
                "wheel_a",
                {"transform_audit": [{"instance_identity": "wheel_a"}]},
            )

    def test_source_contains_no_vehicle_or_tire_family_hardcoding(self) -> None:
        source = __import__("pathlib").Path(ntc3.__file__).read_text(encoding="utf-8")
        self.assertNotIn("TOY_2000GT", source)
        self.assertNotIn("FER_FXX", source)
        self.assertNotIn("HYU_", source)
        self.assertNotIn("Vintage", source)
        self.assertNotIn("Sport", source)
        self.assertNotIn("Slick", source)


if __name__ == "__main__":
    unittest.main()
