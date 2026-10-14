from __future__ import annotations

import math
import unittest

from fh6garage.preview3d.wheel_morph_weights import (
    RIM_MORPH_MAPPING_REVISION,
    WheelMorphWeightError,
    axle_rim_morph_weights,
    rim_morph_weights,
    vehicle_rim_morph_weights,
)
from fh6garage.preview3d.wheel_spec import AxleWheelSpec, VehicleWheelSpec


class WheelMorphWeightTests(unittest.TestCase):
    def test_doliman_rim_formula_is_preserved_exactly(self):
        weights = rim_morph_weights(19.0, 265.0)
        self.assertAlmostEqual(weights[0], (19.0 - 10.0) / 14.0)
        self.assertAlmostEqual(weights[1], (1.0 - 265.0 / 1000.0) / 0.9)

    def test_mapping_does_not_clamp_extrapolated_values(self):
        diameter, width = rim_morph_weights(26.0, 1100.0)
        self.assertGreater(diameter, 1.0)
        self.assertLess(width, 0.0)

    def test_invalid_inputs_fail_closed(self):
        for rim, width in ((0.0, 265.0), (19.0, 0.0), (math.inf, 265.0), (19.0, math.nan)):
            with self.subTest(rim=rim, width=width):
                with self.assertRaises(WheelMorphWeightError):
                    rim_morph_weights(rim, width)

    def test_axle_mapping_keeps_scale_x_at_one(self):
        spec = AxleWheelSpec(
            axle="front",
            tire_width_mm=245.0,
            tire_aspect_ratio=35.0,
            rim_diameter_in=20.0,
        )
        mapped = axle_rim_morph_weights(spec)
        self.assertEqual(mapped.scale_x, 1.0)
        self.assertEqual(mapped.mapping_revision, RIM_MORPH_MAPPING_REVISION)
        self.assertEqual(mapped.weights, (mapped.diameter_weight, mapped.width_weight))

    def test_vehicle_mapping_uses_effective_front_and_rear_specs(self):
        spec = VehicleWheelSpec(
            car_id=1006,
            mode="effective",
            source_table="Drivable_Data_Car",
            car_body_id=123,
            tire_compound_id=None,
            tire_model_name=None,
            front=AxleWheelSpec(
                axle="front",
                tire_width_mm=255.0,
                tire_aspect_ratio=35.0,
                rim_diameter_in=20.0,
            ),
            rear=AxleWheelSpec(
                axle="rear",
                tire_width_mm=335.0,
                tire_aspect_ratio=30.0,
                rim_diameter_in=21.0,
            ),
            applied_upgrade_ids={"front_rim_size_id": 1},
        )
        mapped = vehicle_rim_morph_weights(spec)
        self.assertEqual(mapped.car_id, 1006)
        self.assertEqual(mapped.wheel_spec_mode, "effective")
        self.assertAlmostEqual(mapped.front.diameter_weight, 10.0 / 14.0)
        self.assertAlmostEqual(mapped.rear.diameter_weight, 11.0 / 14.0)
        self.assertAlmostEqual(mapped.front.width_weight, (1.0 - 0.255) / 0.9)
        self.assertAlmostEqual(mapped.rear.width_weight, (1.0 - 0.335) / 0.9)


if __name__ == "__main__":
    unittest.main()
