from __future__ import annotations

import unittest

from fh6garage.preview3d.tire_morph_semantic_evidence import (
    TireMorphSemanticEvidenceError,
    build_tire_selector_semantic_evidence,
)


class TireMorphSemanticEvidenceTests(unittest.TestCase):
    def test_reference_mapping_keeps_selectors_2_4_literal_zero(self) -> None:
        report = build_tire_selector_semantic_evidence()
        by_selector = {item.selector: item for item in report.selectors}

        self.assertEqual(by_selector[0].reference_stock_weight_kind, "computed")
        self.assertEqual(by_selector[1].reference_stock_weight_kind, "computed")
        for selector in (2, 3, 4):
            self.assertEqual(by_selector[selector].reference_stock_weight_kind, "literal_zero")
            self.assertEqual(by_selector[selector].reference_expression, "0")
            self.assertFalse(by_selector[selector].production_semantics_assigned)

        self.assertIn(
            "primary_stock_tire_width_control",
            by_selector[2].excluded_candidate_semantics,
        )
        self.assertIn("track_spacing_control", by_selector[3].excluded_candidate_semantics)
        self.assertIn("track_spacing_control", by_selector[4].excluded_candidate_semantics)
        self.assertFalse(report.production_mapping_enabled)
        self.assertEqual(
            report.complete_mapping_status,
            "diagnostic_selector_2_4_semantics_unresolved",
        )

    def test_expected_slick_like_geometry_remains_unresolved_for_2_4(self) -> None:
        observed = {
            0: ["radial_expansion_dominant"],
            1: ["radial_expansion_dominant"],
            2: ["mixed_x_expansion_radial_contraction"],
            3: ["positive_x_boundary_expansion"],
            4: ["negative_x_boundary_expansion"],
        }
        report = build_tire_selector_semantic_evidence(observed)
        by_selector = {item.selector: item for item in report.selectors}

        self.assertEqual(
            by_selector[0].semantic_status,
            "reference_mapped_geometry_consistent",
        )
        self.assertEqual(
            by_selector[1].semantic_status,
            "reference_mapped_geometry_consistent",
        )
        for selector in (2, 3, 4):
            self.assertEqual(
                by_selector[selector].semantic_status,
                "reference_stock_weight_zero_geometry_role_observed_semantics_unresolved",
            )
        self.assertEqual(
            report.separate_controls["track_spacing"]["reference_behavior"],
            "wheel-instance translation, not tire morph",
        )
        self.assertFalse(report.production_mapping_enabled)

    def test_role_mismatch_fails_closed(self) -> None:
        report = build_tire_selector_semantic_evidence(
            {
                0: ["positive_x_boundary_expansion"],
                1: ["radial_expansion_dominant"],
                2: ["radial_expansion_dominant"],
            }
        )
        self.assertEqual(
            report.complete_mapping_status,
            "diagnostic_selector_semantics_conflict_or_mismatch",
        )
        self.assertFalse(report.production_mapping_enabled)

    def test_unknown_selector_is_rejected(self) -> None:
        with self.assertRaisesRegex(TireMorphSemanticEvidenceError, "0..4"):
            build_tire_selector_semantic_evidence({5: ["unknown"]})


if __name__ == "__main__":
    unittest.main()
