from __future__ import annotations

import unittest

from fh6garage.preview3d.tire_morph_weights import (
    TireMorphWeightError,
    stock_vehicle_tire_morph_weights,
    tire_morph_weights,
)
from fh6garage.preview3d.wheel_spec import AxleWheelSpec, VehicleWheelSpec


class TireMorphWeightTests(unittest.TestCase):
    def test_fxx_stock_front_weights_match_forzatech_mapping(self) -> None:
        weights, scale_x = tire_morph_weights(245.0, 35.0, 19.0, 19.0)
        self.assertAlmostEqual(weights[0], 0.3710909090909091)
        self.assertAlmostEqual(weights[1], 0.6428571428571429)
        self.assertEqual(weights[2:], (0.0, 0.0, 0.0))
        self.assertAlmostEqual(scale_x, 0.245)

    def test_fxx_stock_rear_weights_match_forzatech_mapping(self) -> None:
        weights, scale_x = tire_morph_weights(345.0, 35.0, 19.0, 19.0)
        self.assertAlmostEqual(weights[0], 0.49836363636363636)
        self.assertAlmostEqual(weights[1], 0.6428571428571429)
        self.assertEqual(weights[2:], (0.0, 0.0, 0.0))
        self.assertAlmostEqual(scale_x, 0.345)

    def test_stock_vehicle_mapping_preserves_exact_tire_model_name(self) -> None:
        spec = VehicleWheelSpec(
            car_id=1006,
            mode="stock",
            source_table="Data_Car",
            car_body_id=None,
            tire_compound_id=13,
            tire_model_name="Slick",
            front=AxleWheelSpec(
                axle="front",
                tire_width_mm=245.0,
                tire_aspect_ratio=35.0,
                rim_diameter_in=19.0,
            ),
            rear=AxleWheelSpec(
                axle="rear",
                tire_width_mm=345.0,
                tire_aspect_ratio=35.0,
                rim_diameter_in=19.0,
            ),
        )
        mapped = stock_vehicle_tire_morph_weights(spec)
        self.assertEqual(mapped.car_id, 1006)
        self.assertEqual(mapped.tire_model_name, "Slick")
        self.assertAlmostEqual(mapped.front.scale_x, 0.245)
        self.assertAlmostEqual(mapped.rear.scale_x, 0.345)
        self.assertEqual(mapped.front.selector_weights[2:], (0.0, 0.0, 0.0))
        self.assertEqual(mapped.rear.selector_weights[2:], (0.0, 0.0, 0.0))

    def test_effective_upgrade_mode_fails_closed(self) -> None:
        spec = VehicleWheelSpec(
            car_id=1006,
            mode="effective",
            source_table="Data_Car",
            car_body_id=None,
            tire_compound_id=13,
            tire_model_name="Slick",
            front=AxleWheelSpec("front", 245.0, 35.0, 19.0),
            rear=AxleWheelSpec("rear", 345.0, 35.0, 19.0),
        )
        with self.assertRaisesRegex(TireMorphWeightError, "requires a stock"):
            stock_vehicle_tire_morph_weights(spec)

    def test_invalid_dimensions_fail_closed(self) -> None:
        for bad in (0.0, -1.0, float("inf"), float("nan")):
            with self.subTest(bad=bad):
                with self.assertRaises(TireMorphWeightError):
                    tire_morph_weights(bad, 35.0, 19.0, 19.0)


if __name__ == "__main__":
    unittest.main()
