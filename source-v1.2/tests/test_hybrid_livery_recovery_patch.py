from __future__ import annotations

import unittest
from dataclasses import dataclass

import numpy as np

from fh6garage.preview3d.hybrid_livery_recovery_patch import apply_hybrid_recovery_to_scene


@dataclass(frozen=True)
class _Scene:
    allowed_sides: np.ndarray
    projection_sides: np.ndarray
    direct_uv: np.ndarray
    indices: np.ndarray
    primitive_diagnostics: tuple[dict, ...]
    livery_uv_channel: int = 3
    livery_eligibility_policy: str = "strict"
    uv3_meshes: int = 0
    promoted_livery_meshes: int = 0
    selected_uv_channel_counts: dict[int, int] | None = None


class HybridLiveryRecoveryPatchTests(unittest.TestCase):
    def _scene(self, rows):
        vertex_count = 0
        all_indices = []
        for row in rows:
            local = np.asarray(row.pop("_indices"), dtype=np.uint32)
            all_indices.append(local + vertex_count)
            vertex_count += int(local.max(initial=0)) + 1
        return _Scene(
            allowed_sides=np.zeros((vertex_count, 1), dtype=np.float32),
            projection_sides=np.zeros((vertex_count, 1), dtype=np.float32),
            direct_uv=np.zeros((vertex_count, 1), dtype=np.float32),
            indices=np.concatenate(all_indices),
            primitive_diagnostics=tuple(rows),
            selected_uv_channel_counts={},
        )

    def test_verified_exterior_shell_is_recovered(self):
        scene = self._scene([{
            "_indices": [0, 1, 2],
            "triangle_count": 1,
            "final_allowed_sides": 0,
            "structural_livery_exclusion": "",
            "declared_role": "trim",
            "part_type": "CarBody",
            "source_entry": r"Scene\Exterior\Fenders\fenders_a.modelbin",
            "mesh_name": "fenders_a :: fenders_a_LODS0",
            "material_name": "",
            "selected_uv_evidence_sides": 24,
            "has_selected_uv": True,
        }])
        result = apply_hybrid_recovery_to_scene(scene)
        self.assertEqual(result.livery_eligibility_policy, "hybrid")
        self.assertTrue(np.all(result.allowed_sides[:, 0] == 24.0))
        self.assertTrue(np.all(result.direct_uv[:, 0] == 1.0))
        self.assertEqual(result.promoted_livery_meshes, 1)
        self.assertEqual(result.primitive_diagnostics[0]["inference_action"], "hybrid_recovered_exterior_shell")

    def test_kfps_hood_part_with_top_mask_evidence_is_recovered(self):
        scene = self._scene([{
            "_indices": [0, 1, 2],
            "triangle_count": 1,
            "final_allowed_sides": 0,
            "structural_livery_exclusion": "",
            "declared_role": "trim",
            "part_type": "Hood",
            "source_entry": r"Scene\Exterior\Hood\hood_a.modelbin",
            "mesh_name": "hood_a :: hood_a_LODS0",
            "material_name": "",
            "selected_uv_evidence_sides": 4,
            "has_selected_uv": True,
        }])
        result = apply_hybrid_recovery_to_scene(scene)
        self.assertTrue(np.all(result.allowed_sides[:, 0] == 4.0))
        self.assertTrue(np.all(result.direct_uv[:, 0] == 1.0))
        self.assertEqual(result.promoted_livery_meshes, 1)
        self.assertTrue(result.primitive_diagnostics[0]["livery_recovery_applied"])

    def test_primary_light_is_not_recovered(self):
        scene = self._scene([{
            "_indices": [0, 1, 2],
            "triangle_count": 1,
            "final_allowed_sides": 0,
            "structural_livery_exclusion": "",
            "declared_role": "trim",
            "part_type": "CarBody",
            "source_entry": r"Scene\Exterior\PrimaryLights\glassLHL_a.modelbin",
            "mesh_name": "glassLHL_a :: glassLHL_a_LODS0",
            "material_name": "",
            "selected_uv_evidence_sides": 5,
            "has_selected_uv": True,
        }])
        result = apply_hybrid_recovery_to_scene(scene)
        self.assertTrue(np.all(result.allowed_sides == 0.0))
        self.assertTrue(np.all(result.direct_uv == 0.0))
        self.assertEqual(result.promoted_livery_meshes, 0)
        self.assertFalse(result.primitive_diagnostics[0]["livery_recovery_applied"])

    def test_accessory_inside_shell_family_is_not_recovered(self):
        scene = self._scene([{
            "_indices": [0, 1, 2],
            "triangle_count": 1,
            "final_allowed_sides": 0,
            "structural_livery_exclusion": "",
            "declared_role": "trim",
            "part_type": "CarBody",
            "source_entry": r"Scene\Exterior\Doors\doorHandleLF_a.modelbin",
            "mesh_name": "doorHandleLF_a :: doorHandleLF_a_LODS0",
            "material_name": "",
            "selected_uv_evidence_sides": 8,
            "has_selected_uv": True,
        }])
        result = apply_hybrid_recovery_to_scene(scene)
        self.assertTrue(np.all(result.allowed_sides == 0.0))
        self.assertEqual(result.promoted_livery_meshes, 0)

    def test_missing_selected_uv_fails_closed(self):
        scene = self._scene([{
            "_indices": [0, 1, 2],
            "triangle_count": 1,
            "final_allowed_sides": 0,
            "structural_livery_exclusion": "",
            "declared_role": "trim",
            "part_type": "Hood",
            "source_entry": r"Scene\Exterior\Hood\hood_a.modelbin",
            "mesh_name": "hood_a :: hood_a_LODS0",
            "material_name": "",
            "selected_uv_evidence_sides": 4,
            "has_selected_uv": False,
        }])
        result = apply_hybrid_recovery_to_scene(scene)
        self.assertTrue(np.all(result.allowed_sides == 0.0))
        self.assertEqual(result.promoted_livery_meshes, 0)


if __name__ == "__main__":
    unittest.main()
