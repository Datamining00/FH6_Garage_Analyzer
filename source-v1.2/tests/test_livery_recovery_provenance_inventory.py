from __future__ import annotations

import unittest
from dataclasses import dataclass

from fh6garage.preview3d.livery_recovery_diagnostic import (
    annotate_scene_recovery_diagnostics,
    mesh_provenance_from_document,
)


@dataclass(frozen=True)
class _Scene:
    primitive_diagnostics: tuple[dict, ...]
    livery_eligibility_policy: str = "strict"


class LiveryRecoveryProvenanceInventoryTests(unittest.TestCase):
    def test_converter_mesh_extras_are_preserved_as_diagnostic_provenance(self):
        document = {
            "meshes": [
                {
                    "extras": {
                        "kfps_material_binding_hash": "E00E033E6A20B977",
                        "kfps_instance_identity": "scene/exterior/test|0",
                        "kfps_stock_part": True,
                        "kfps_part_option_ids": [3, 7],
                        "kfps_draw_groups": 5,
                        "kfps_allowed_sides": 31,
                        "kfps_projection_sides": 4,
                    }
                }
            ]
        }
        result = mesh_provenance_from_document(document)
        self.assertEqual(result[0]["material_binding_hash"], "E00E033E6A20B977")
        self.assertEqual(result[0]["part_option_ids"], [3, 7])
        self.assertEqual(result[0]["converter_projection_sides"], 4)

    def test_unknown_exterior_part_is_inventoried_but_not_auto_recovered(self):
        scene = _Scene(({
            "mesh_index": 0,
            "mesh_name": "engineCover_a :: engineCover_a_LODS0",
            "primitive_index": 0,
            "material_name": "body_surface",
            "source_entry": r"Scene\Exterior\EngineCover\engineCover_a.modelbin",
            "part_type": "EngineCover",
            "declared_role": "trim",
            "final_allowed_sides": 0,
            "selected_uv_evidence_sides": 4,
        },))
        report = annotate_scene_recovery_diagnostics(
            scene,
            {0: {"material_binding_hash": "ABCDEF0123456789", "stock_part": True}},
        )
        self.assertEqual(report["candidate_count"], 0)
        self.assertEqual(report["missed_exterior_count"], 1)
        self.assertEqual(report["missed_exterior_by_part_type"], {"EngineCover": 1})
        row = report["missed_exterior_inventory"][0]
        self.assertEqual(row["reason"], "not_paintable_livery_part_type")
        self.assertEqual(row["material_binding_hash"], "ABCDEF0123456789")
        self.assertFalse(row["safe_candidate_for_review"])

    def test_known_light_remains_visible_in_inventory_as_non_livery_evidence(self):
        scene = _Scene(({
            "mesh_index": 1,
            "mesh_name": "glassLHL_a :: glassLHL_a_LODS0",
            "primitive_index": 0,
            "material_name": "glass_light",
            "source_entry": r"Scene\Exterior\PrimaryLights\glassLHL_a.modelbin",
            "part_type": "CarBody",
            "declared_role": "trim",
            "final_allowed_sides": 0,
            "selected_uv_evidence_sides": 5,
        },))
        report = annotate_scene_recovery_diagnostics(scene)
        self.assertEqual(report["missed_exterior_count"], 1)
        row = report["missed_exterior_inventory"][0]
        self.assertEqual(row["recovery_class"], "non_livery_structure")
        self.assertFalse(row["safe_candidate_for_review"])


if __name__ == "__main__":
    unittest.main()
