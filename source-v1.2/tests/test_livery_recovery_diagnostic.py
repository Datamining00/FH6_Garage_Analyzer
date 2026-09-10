from __future__ import annotations

import unittest

from fh6garage.preview3d.livery_recovery_diagnostic import classify_strict_recovery_candidate


class LiveryRecoveryDiagnosticTests(unittest.TestCase):
    def test_strict_missed_exterior_carbody_with_mask_evidence_is_candidate(self):
        result = classify_strict_recovery_candidate({
            "final_allowed_sides": 0,
            "structural_livery_exclusion": "",
            "declared_role": "trim",
            "part_type": "CarBody",
            "source_entry": r"Scene\Exterior\Hood\hood_a.modelbin",
            "mesh_name": "hood_outer",
            "material_name": "body_surface",
            "selected_uv_evidence_sides": 4,
        })
        self.assertTrue(result["candidate"])
        self.assertTrue(result["safe_candidate_for_review"])
        self.assertEqual(result["evidence_mask"], 4)

    def test_already_strict_eligible_is_not_candidate(self):
        result = classify_strict_recovery_candidate({
            "final_allowed_sides": 3,
            "part_type": "CarBody",
            "source_entry": r"Scene\Exterior\Doors\doorLF_a.modelbin",
            "selected_uv_evidence_sides": 3,
        })
        self.assertFalse(result["candidate"])
        self.assertEqual(result["reason"], "already_eligible")

    def test_structurally_excluded_geometry_is_not_candidate(self):
        result = classify_strict_recovery_candidate({
            "final_allowed_sides": 0,
            "structural_livery_exclusion": "part_type_brakes",
            "part_type": "Brakes",
            "source_entry": r"Scene\Exterior\Brakes\disc.modelbin",
            "selected_uv_evidence_sides": 1,
        })
        self.assertFalse(result["candidate"])
        self.assertTrue(result["reason"].startswith("structural_exclusion:"))

    def test_non_carbody_exterior_is_not_candidate(self):
        result = classify_strict_recovery_candidate({
            "final_allowed_sides": 0,
            "part_type": "WheelStyle",
            "source_entry": r"Scene\Exterior\Wheels\rim.modelbin",
            "selected_uv_evidence_sides": 1,
        })
        self.assertFalse(result["candidate"])
        self.assertEqual(result["reason"], "not_carbody")

    def test_carbody_without_mask_evidence_is_not_candidate(self):
        result = classify_strict_recovery_candidate({
            "final_allowed_sides": 0,
            "part_type": "CarBody",
            "source_entry": r"Scene\Exterior\Roof\roof_a.modelbin",
            "selected_uv_evidence_sides": 0,
            "uv3_evidence_sides": 0,
        })
        self.assertFalse(result["candidate"])
        self.assertEqual(result["reason"], "no_livery_mask_evidence")

    def test_light_like_names_are_flagged_for_manual_review_not_auto_rejected(self):
        result = classify_strict_recovery_candidate({
            "final_allowed_sides": 0,
            "part_type": "CarBody",
            "source_entry": r"Scene\Exterior\Lights\headlightLF.modelbin",
            "mesh_name": "headlight_lens",
            "material_name": "bulb_glass",
            "selected_uv_evidence_sides": 1,
        })
        self.assertTrue(result["candidate"])
        self.assertFalse(result["safe_candidate_for_review"])
        self.assertIn("headlight", result["risk_tokens"])
        self.assertIn("bulb", result["risk_tokens"])


if __name__ == "__main__":
    unittest.main()
