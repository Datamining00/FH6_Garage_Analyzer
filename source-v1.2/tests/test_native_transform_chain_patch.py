from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from fh6garage.preview3d import native_transform_chain_patch as ntc


def _matrix(x: float = 0.0, y: float = 0.0, z: float = 0.0) -> list[float]:
    return [
        1.0, 0.0, 0.0, 0.0,
        0.0, 1.0, 0.0, 0.0,
        0.0, 0.0, 1.0, 0.0,
        float(x), float(y), float(z), 1.0,
    ]


def _anchor(identity: str, x: float, z: float, *, bone: str = "") -> dict:
    carbin = _matrix(x, 0.0, z)
    # Deliberately make the exact KFPS effective transform different from the
    # raw carbin transform so the contract can prove which matrix it selects.
    effective = _matrix(x + 0.125, 0.25, z - 0.375)
    return {
        "instance_identity": identity,
        "source_entry": f"wheel/{identity}.modelbin",
        "resource_path": f"scene/wheel/{identity}.modelbin",
        "bone_name": bone,
        "bone_id": 0,
        "stock_part": True,
        "carbin_transform_row_major": carbin,
        "effective_transform_row_major": effective,
    }


class NativeTransformChainTests(unittest.TestCase):
    def test_row_major_bone_world_matches_system_numerics_order(self) -> None:
        parent = tuple(_matrix(10.0, 0.0, 0.0))
        child = tuple(_matrix(0.0, 2.0, 0.0))
        bones = (
            ("root", -1, parent),
            ("child", 0, child),
        )
        worlds = ntc._bone_world_matrices(bones)
        self.assertEqual(len(worlds), 2)
        self.assertEqual(ntc._transform_point_row((0.0, 0.0, 0.0), worlds[1]), (10.0, 2.0, 0.0))

    def test_six_wheel_inventory_is_not_reduced_to_four(self) -> None:
        raw = [
            _anchor("front_left", -1.0, 3.0),
            _anchor("front_right", 1.0, 3.0),
            _anchor("mid_left", -1.0, 0.5),
            _anchor("mid_right", 1.0, 0.5),
            _anchor("rear_left", -1.0, -2.0),
            _anchor("rear_right", 1.0, -2.0),
        ]
        classified = ntc._classify_dynamic_wheel_anchors(raw)
        self.assertEqual(len(classified), 6)
        self.assertEqual(sum(item["axle"] == "front" for item in classified), 2)
        self.assertEqual(sum(item["axle"] == "rear" for item in classified), 4)
        self.assertEqual(sum(item["side"] == "left" for item in classified), 3)
        self.assertEqual(sum(item["side"] == "right" for item in classified), 3)

    def test_three_wheel_inventory_preserves_center_wheel(self) -> None:
        raw = [
            _anchor("front_left", -1.0, 2.0),
            _anchor("front_right", 1.0, 2.0),
            _anchor("rear_center", 0.0, -1.0),
        ]
        classified = ntc._classify_dynamic_wheel_anchors(raw)
        self.assertEqual(len(classified), 3)
        center = next(item for item in classified if item["instance_identity"] == "rear_center")
        self.assertEqual(center["axle"], "rear")
        self.assertEqual(center["side"], "center")
        self.assertEqual(center["side_inference"], "carbin_lateral_center")

    def test_attachment_contract_uses_exact_kfps_effective_transform(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            left_front = root / "front_left.glb"
            right_front = root / "front_right.glb"
            left_rear = root / "rear_left.glb"
            right_rear = root / "rear_right.glb"
            for path in (left_front, right_front, left_rear, right_rear):
                path.write_bytes(b"fixture")

            geometry = {
                "front": {
                    "modelbins": [
                        {"entry": "tireL_Test.modelbin", "glb_path": str(left_front)},
                        {"entry": "tireR_Test.modelbin", "glb_path": str(right_front)},
                    ]
                },
                "rear": {
                    "modelbins": [
                        {"entry": "tireL_Test.modelbin", "glb_path": str(left_rear)},
                        {"entry": "tireR_Test.modelbin", "glb_path": str(right_rear)},
                    ]
                },
            }
            anchors = [
                _anchor("wheel_fl", -1.0, 2.0, bone="spindleLF"),
                _anchor("wheel_fr", 1.0, 2.0, bone="spindleRF"),
                _anchor("wheel_ml", -1.0, 0.0),
                _anchor("wheel_mr", 1.0, 0.0),
                _anchor("wheel_rl", -1.0, -2.0, bone="spindleLR"),
                _anchor("wheel_rr", 1.0, -2.0, bone="spindleRR"),
            ]
            contract = ntc._build_dynamic_attachment_contract(
                247,
                geometry,
                {"wheel_style_anchors": anchors},
            )

            self.assertEqual(contract["attachment_count"], 6)
            self.assertFalse(contract["four_wheel_assumption"])
            self.assertTrue(contract["native_tire_rigid_bone_applied"])
            self.assertTrue(contract["exact_kfps_effective_instance_transform_used"])
            by_id = {item["attachment_id"]: item for item in contract["attachments"]}
            for source in anchors:
                attached = by_id[source["instance_identity"]]
                self.assertEqual(
                    attached["placement_transform_matrix_row_major"],
                    source["effective_transform_row_major"],
                )
                self.assertNotEqual(
                    attached["placement_transform_matrix_row_major"],
                    source["carbin_transform_row_major"],
                )

    def test_no_wheelstyle_inventory_fails_closed_instead_of_assuming_four(self) -> None:
        with self.assertRaisesRegex(ntc.NativeTransformChainError, "no resolved WheelStyle anchors"):
            ntc._classify_dynamic_wheel_anchors([])


if __name__ == "__main__":
    unittest.main()
