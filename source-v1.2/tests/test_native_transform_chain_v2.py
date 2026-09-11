from __future__ import annotations

import math
from types import SimpleNamespace
import unittest

from fh6garage.preview3d import native_transform_chain_v2 as ntc2


def _matrix(x: float = 0.0, y: float = 0.0, z: float = 0.0) -> list[float]:
    return [
        1.0, 0.0, 0.0, 0.0,
        0.0, 1.0, 0.0, 0.0,
        0.0, 0.0, 1.0, 0.0,
        float(x), float(y), float(z), 1.0,
    ]


def _anchor(identity: str, x: float, z: float, *, bone: str = "") -> dict:
    return {
        "instance_identity": identity,
        "source_entry": f"wheel/{identity}.modelbin",
        "resource_path": f"scene/wheel/{identity}.modelbin",
        "bone_name": bone,
        "bone_id": 0,
        "stock_part": True,
        "carbin_transform_row_major": _matrix(x, 0.0, z),
        "effective_transform_row_major": _matrix(x, 0.0, z),
    }


class NativeTransformChainV2Tests(unittest.TestCase):
    def test_annular_mapping_infers_axis_and_matches_width_bead_outer(self) -> None:
        # Structural centre is deliberately offset from the model origin.  X is
        # axial and Y/Z form the rotational plane; no axis is supplied to code.
        points = []
        for x in (0.0, 2.0):
            for radius in (2.0, 3.0):
                for angle in (0.0, math.pi / 2.0, math.pi, 3.0 * math.pi / 2.0):
                    points.append(
                        (
                            x,
                            4.0 + radius * math.cos(angle),
                            -3.0 + radius * math.sin(angle),
                        )
                    )
        spec = SimpleNamespace(
            tire_width_mm=200.0,
            rim_diameter_mm=400.0,
            tire_outer_diameter_mm=600.0,
        )
        mapped, report = ntc2._map_annular_tire_to_stock(points, spec)
        self.assertEqual(report["axial_axis"], 0)
        self.assertEqual(report["radial_axes"], [1, 2])
        self.assertEqual(report["geometry_mapping_mode"], "structure_inferred_annular_stock_mapping")
        xs = [point[0] for point in mapped]
        self.assertAlmostEqual(min(xs), -0.1, places=9)
        self.assertAlmostEqual(max(xs), 0.1, places=9)
        radii = [math.hypot(point[1], point[2]) for point in mapped]
        self.assertAlmostEqual(min(radii), 0.2, places=9)
        self.assertAlmostEqual(max(radii), 0.3, places=9)
        self.assertAlmostEqual(report["mapped_axial_center"], 0.0, places=12)
        self.assertFalse(report["vehicle_specific_offset_applied"])
        self.assertFalse(report["family_specific_scale_applied"])

    def test_ambiguous_rotational_axes_fail_closed(self) -> None:
        cube = [
            (-1.0, -1.0, -1.0),
            (-1.0, -1.0, 1.0),
            (-1.0, 1.0, -1.0),
            (-1.0, 1.0, 1.0),
            (1.0, -1.0, -1.0),
            (1.0, -1.0, 1.0),
            (1.0, 1.0, -1.0),
            (1.0, 1.0, 1.0),
        ]
        with self.assertRaisesRegex(ntc2.NativeTransformChainV2Error, "ambiguous"):
            ntc2._structural_tire_axes(cube)

    def test_six_wheels_form_three_dynamic_axles(self) -> None:
        raw = [
            _anchor("front_left", -1.0, 3.0),
            _anchor("front_right", 1.0, 3.0),
            _anchor("middle_left", -1.0, 0.5),
            _anchor("middle_right", 1.0, 0.5),
            _anchor("rear_left", -1.0, -2.0),
            _anchor("rear_right", 1.0, -2.0),
        ]
        classified = ntc2._classify_dynamic_wheel_anchors_v2(raw)
        self.assertEqual(len(classified), 6)
        self.assertEqual({item["dynamic_axle_count"] for item in classified}, {3})
        counts = {
            index: sum(item["dynamic_axle_index"] == index for item in classified)
            for index in range(3)
        }
        self.assertEqual(counts, {0: 2, 1: 2, 2: 2})
        self.assertEqual(
            {item["stock_spec_axle"] for item in classified if item["dynamic_axle_index"] == 0},
            {"front"},
        )
        self.assertEqual(
            {item["stock_spec_axle"] for item in classified if item["dynamic_axle_index"] > 0},
            {"rear"},
        )

    def test_three_wheels_keep_center_wheel_as_own_axle(self) -> None:
        raw = [
            _anchor("front_left", -1.0, 2.0),
            _anchor("front_right", 1.0, 2.0),
            _anchor("rear_center", 0.0, -1.0),
        ]
        classified = ntc2._classify_dynamic_wheel_anchors_v2(raw)
        center = next(item for item in classified if item["instance_identity"] == "rear_center")
        self.assertEqual(center["side"], "center")
        self.assertEqual(center["dynamic_axle_index"], 1)
        self.assertEqual(center["dynamic_axle_count"], 2)


if __name__ == "__main__":
    unittest.main()
