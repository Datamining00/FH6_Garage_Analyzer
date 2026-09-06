from __future__ import annotations

import unittest

from fh6garage.preview3d.wheel_morph_runtime import (
    WheelMorphRuntimeContractError,
    validate_wheel_morph_diagnostics,
    wheel_morph_environment,
)
from fh6garage.preview3d.wheel_morph_weights import (
    AxleRimMorphWeights,
    VehicleRimMorphWeights,
)


def _weights(car_id: int = 1006) -> VehicleRimMorphWeights:
    return VehicleRimMorphWeights(
        car_id=car_id,
        wheel_spec_mode="stock",
        front=AxleRimMorphWeights(
            axle="front",
            rim_diameter_in=19.0,
            tire_width_mm=245.0,
            diameter_weight=9.0 / 14.0,
            width_weight=0.755 / 0.9,
        ),
        rear=AxleRimMorphWeights(
            axle="rear",
            rim_diameter_in=19.0,
            tire_width_mm=345.0,
            diameter_weight=9.0 / 14.0,
            width_weight=0.655 / 0.9,
        ),
    )


class WheelMorphRuntimeTests(unittest.TestCase):
    def test_no_request_emits_no_environment(self):
        self.assertEqual(wheel_morph_environment(1006, None), {})
        self.assertIsNone(validate_wheel_morph_diagnostics(1006, None, {}))

    def test_combined_environment_uses_verified_front_rear_weights(self):
        env = wheel_morph_environment(1006, _weights())
        self.assertEqual(env["KFPS_WHEEL_MORPH_MODE"], "combined")
        self.assertEqual(float(env["KFPS_WHEEL_MORPH_FRONT_DIAMETER"]), 9.0 / 14.0)
        self.assertEqual(float(env["KFPS_WHEEL_MORPH_FRONT_WIDTH"]), 0.755 / 0.9)
        self.assertEqual(float(env["KFPS_WHEEL_MORPH_REAR_DIAMETER"]), 9.0 / 14.0)
        self.assertEqual(float(env["KFPS_WHEEL_MORPH_REAR_WIDTH"]), 0.655 / 0.9)
        self.assertEqual(len(env), 5)

    def test_car_id_mismatch_fails_before_converter_launch(self):
        with self.assertRaises(WheelMorphRuntimeContractError):
            wheel_morph_environment(1229, _weights(1006))

    def test_upstream_converter_shape_fails_closed(self):
        with self.assertRaises(WheelMorphRuntimeContractError):
            validate_wheel_morph_diagnostics(
                1006,
                _weights(),
                {
                    "format": "kfps_local_chassis_conversion_v5",
                    "mesh_count": 694,
                    "scene_assembled": True,
                },
            )

    def test_zero_applied_geometry_fails_closed(self):
        for key in ("wheel_morph_applied_meshes", "wheel_morph_applied_vertices"):
            payload = {
                "wheel_morph_mode": "combined",
                "wheel_morph_applied_meshes": 48,
                "wheel_morph_applied_vertices": 37066,
                "wheel_morph_axle_split_z": -0.001,
            }
            payload[key] = 0
            with self.subTest(key=key):
                with self.assertRaises(WheelMorphRuntimeContractError):
                    validate_wheel_morph_diagnostics(1006, _weights(), payload)

    def test_verified_combined_diagnostics_are_recorded(self):
        result = validate_wheel_morph_diagnostics(
            1006,
            _weights(),
            {
                "wheel_morph_mode": "combined",
                "wheel_morph_applied_meshes": 48,
                "wheel_morph_applied_vertices": 37066,
                "wheel_morph_axle_split_z": -0.0010060072,
            },
        )
        assert result is not None
        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["applied_meshes"], 48)
        self.assertEqual(result["applied_vertices"], 37066)
        self.assertAlmostEqual(result["axle_split_z"], -0.0010060072)
        self.assertEqual(result["weights"]["car_id"], 1006)
        self.assertEqual(result["weights"]["front"]["scale_x"], 1.0)
        self.assertEqual(result["weights"]["rear"]["scale_x"], 1.0)


if __name__ == "__main__":
    unittest.main()
