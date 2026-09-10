from __future__ import annotations

import unittest

from fh6garage.preview3d.livery_recovery_diagnostic import classify_strict_recovery_candidate


class LiveryRecoveryDiagnosticTests(unittest.TestCase):
    def test_strict_missed_exterior_shell_with_mask_evidence_is_safe_candidate(self):
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
        self.assertEqual(result["recovery_class"], "exterior_shell")
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

    def test_primary_light_structure_is_never_safe_for_recovery_review(self):
        result = classify_strict_recovery_candidate({
            "final_allowed_sides": 0,
            "part_type": "CarBody",
            "source_entry": r"Scene\Exterior\PrimaryLights\glassLHL_a.modelbin",
            "mesh_name": "glassLHL_a",
            "declared_role": "trim",
            "selected_uv_evidence_sides": 5,
        })
        self.assertTrue(result["candidate"])
        self.assertFalse(result["safe_candidate_for_review"])
        self.assertEqual(result["recovery_class"], "non_livery_structure")
        self.assertIn("primarylights", result["hard_non_livery_path"])

    def test_door_handle_is_accessory_not_safe_shell(self):
        result = classify_strict_recovery_candidate({
            "final_allowed_sides": 0,
            "part_type": "CarBody",
            "source_entry": r"Scene\Exterior\Doors\doorHandleLF_a.modelbin",
            "mesh_name": "doorHandleLF_a :: doorHandleLF_a_LODS0",
            "declared_role": "trim",
            "selected_uv_evidence_sides": 8,
        })
        self.assertTrue(result["candidate"])
        self.assertFalse(result["safe_candidate_for_review"])
        self.assertEqual(result["recovery_class"], "accessory_or_non_livery")
        self.assertIn("doorhandle", result["risk_tokens"])

    def test_body_antenna_is_accessory_not_safe_shell(self):
        result = classify_strict_recovery_candidate({
            "final_allowed_sides": 0,
            "part_type": "CarBody",
            "source_entry": r"Scene\Exterior\Platform\bodyAntenna_a.modelbin",
            "mesh_name": "bodyAntenna_a :: bodyAntenna_a_LODS0",
            "declared_role": "trim",
            "selected_uv_evidence_sides": 4,
        })
        self.assertTrue(result["candidate"])
        self.assertFalse(result["safe_candidate_for_review"])
        self.assertEqual(result["recovery_class"], "accessory_or_non_livery")
        self.assertIn("antenna", result["risk_tokens"])

    def test_trunk_badge_is_accessory_not_safe_shell(self):
        result = classify_strict_recovery_candidate({
            "final_allowed_sides": 0,
            "part_type": "CarBody",
            "source_entry": r"Scene\Exterior\Trunk\trunk_a.modelbin",
            "mesh_name": "trunk_a :: trunkBadge_a_LODS0",
            "declared_role": "trim",
            "selected_uv_evidence_sides": 2,
        })
        self.assertTrue(result["candidate"])
        self.assertFalse(result["safe_candidate_for_review"])
        self.assertEqual(result["recovery_class"], "accessory_or_non_livery")
        self.assertIn("badge", result["risk_tokens"])

    def test_real_gtr_door_fender_and_body_shell_shapes_are_safe_review_candidates(self):
        cases = (
            (r"Scene\Exterior\Doors\doorLF_a.modelbin", "doorLF_a :: doorLF_a_LODS0", 8),
            (r"Scene\Exterior\Fenders\fenders_a.modelbin", "fenders_a :: fenders_a_LODS0", 24),
            (r"Scene\Exterior\Platform\body_a.modelbin", "body_a :: body_a_LODS0", 28),
        )
        for source_entry, mesh_name, evidence in cases:
            with self.subTest(mesh_name=mesh_name):
                result = classify_strict_recovery_candidate({
                    "final_allowed_sides": 0,
                    "part_type": "CarBody",
                    "source_entry": source_entry,
                    "mesh_name": mesh_name,
                    "declared_role": "trim",
                    "selected_uv_evidence_sides": evidence,
                })
                self.assertTrue(result["candidate"])
                self.assertTrue(result["safe_candidate_for_review"])
                self.assertEqual(result["recovery_class"], "exterior_shell")


if __name__ == "__main__":
    unittest.main()
