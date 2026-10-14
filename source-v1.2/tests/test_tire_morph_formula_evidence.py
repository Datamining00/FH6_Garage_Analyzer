from __future__ import annotations

import unittest

from fh6garage.preview3d.tire_morph_formula_evidence import (
    TireMorphFormulaEvidenceError,
    build_tire_morph_formula_evidence,
)
from fh6garage.preview3d.wheel_spec import AxleWheelSpec, VehicleWheelSpec


def _selector(selector, max_abs, min_signed, max_signed):
    return {
        "selector": selector,
        "record_count": 10,
        "nonzero_record_count": 10,
        "sum_abs_delta": [0.0, 0.0, 0.0],
        "mean_abs_delta": [0.0, 0.0, 0.0],
        "max_abs_delta": list(max_abs),
        "min_signed_delta": list(min_signed),
        "max_signed_delta": list(max_signed),
    }


def _morph_profile(selector0=(0.01, 0.275, 0.274)):
    selectors = [
        _selector(0, selector0, (-0.01, -0.275, -0.274), (0.01, 0.275, 0.274)),
        _selector(1, (0.005, 0.184, 0.180), (-0.005, -0.184, -0.180), (0.005, 0.184, 0.180)),
        _selector(2, (0.100, 0.080, 0.050), (-0.080, -0.050, -0.040), (0.100, 0.080, 0.050)),
        _selector(3, (0.378, 0.005, 0.004), (0.0, -0.005, -0.004), (0.378, 0.005, 0.004)),
        _selector(4, (0.377, 0.005, 0.004), (-0.377, -0.005, -0.004), (0.0, 0.005, 0.004)),
    ]
    profile = {
        "morph_target_count": 5,
        "selectors": selectors,
    }
    group = {"profile": profile}
    modelbin = {"profiles": [group]}
    return {
        "modelbins": [modelbin, modelbin],
        "left_right_morph_buffers_identical": True,
    }


def _geometry_report(x_span=1.0):
    model = {"states": {"baseline": {"aabb": {"span": [x_span, 0.8, 0.8]}}}}
    return {"modelbins": [model, model]}


def _spec(mode="stock"):
    return VehicleWheelSpec(
        car_id=1006,
        mode=mode,
        source_table="Data_Car",
        car_body_id=None,
        tire_compound_id=13,
        tire_model_name="Slick",
        front=AxleWheelSpec("front", 245.0, 35.0, 19.0),
        rear=AxleWheelSpec("rear", 345.0, 35.0, 19.0),
    )


class TireMorphFormulaEvidenceTests(unittest.TestCase):
    def test_fxx_stock_mapping_is_decomposed_into_physical_quantities(self):
        report = build_tire_morph_formula_evidence(
            _spec(), _morph_profile(), _geometry_report()
        )
        self.assertFalse(report.production_mapping_enabled)
        self.assertEqual(report.complete_mapping_status, "diagnostic_only_partial_corroboration")
        self.assertAlmostEqual(report.front.outer_radius_mm, 327.05)
        self.assertAlmostEqual(report.rear.outer_radius_mm, 362.05)
        self.assertAlmostEqual(report.front.selector0_outer_radius_weight, 0.3710909090909091)
        self.assertAlmostEqual(report.rear.selector0_outer_radius_weight, 0.49836363636363636)
        self.assertAlmostEqual(report.front.selector1_rim_diameter_weight, 0.6428571428571429)
        self.assertAlmostEqual(report.front.scale_x_width_m, 0.245)
        self.assertAlmostEqual(report.rear.scale_x_width_m, 0.345)

    def test_selector_roles_and_radial_scales_are_corroborated_individually(self):
        report = build_tire_morph_formula_evidence(
            _spec(), _morph_profile(), _geometry_report()
        )
        by_selector = {item.selector: item for item in report.selector_evidence}
        self.assertEqual(by_selector[0].geometry_role_hint, "radial_dominant")
        self.assertEqual(by_selector[0].expected_physical_role, "outer_radius_control")
        self.assertEqual(by_selector[0].corroboration, "geometry_corroborated")
        self.assertAlmostEqual(by_selector[0].expected_radial_scale_m_per_weight, 0.275)
        self.assertAlmostEqual(by_selector[0].radial_scale_relative_error, 0.0)

        self.assertEqual(by_selector[1].geometry_role_hint, "radial_dominant")
        self.assertEqual(by_selector[1].expected_physical_role, "rim_diameter_control")
        self.assertEqual(by_selector[1].corroboration, "geometry_corroborated")
        self.assertLess(by_selector[1].radial_scale_relative_error, 0.04)

        self.assertEqual(by_selector[2].geometry_role_hint, "mixed")
        self.assertEqual(by_selector[2].corroboration, "not_applicable")
        self.assertEqual(by_selector[3].geometry_role_hint, "positive_x_dominant")
        self.assertEqual(by_selector[4].geometry_role_hint, "negative_x_dominant")

    def test_width_scale_requires_independent_base_x_normalization(self):
        consistent = build_tire_morph_formula_evidence(
            _spec(), _morph_profile(), _geometry_report(1.0)
        )
        self.assertEqual(
            consistent.width_scale_normalization_status,
            "base_x_normalization_consistent",
        )
        inconsistent = build_tire_morph_formula_evidence(
            _spec(), _morph_profile(), _geometry_report(0.8)
        )
        self.assertEqual(
            inconsistent.width_scale_normalization_status,
            "base_x_normalization_not_corroborated",
        )
        missing = build_tire_morph_formula_evidence(_spec(), _morph_profile())
        self.assertEqual(missing.width_scale_normalization_status, "not_evaluated")

    def test_wrong_selector0_axis_fails_corroboration(self):
        report = build_tire_morph_formula_evidence(
            _spec(),
            _morph_profile(selector0=(0.300, 0.010, 0.010)),
            _geometry_report(),
        )
        selector0 = {item.selector: item for item in report.selector_evidence}[0]
        self.assertEqual(selector0.geometry_role_hint, "x_dominant")
        self.assertEqual(selector0.corroboration, "not_corroborated")
        self.assertEqual(report.complete_mapping_status, "diagnostic_only_not_corroborated")

    def test_effective_upgrade_mode_fails_closed(self):
        with self.assertRaisesRegex(TireMorphFormulaEvidenceError, "requires a stock"):
            build_tire_morph_formula_evidence(
                _spec(mode="effective"), _morph_profile(), _geometry_report()
            )


if __name__ == "__main__":
    unittest.main()
