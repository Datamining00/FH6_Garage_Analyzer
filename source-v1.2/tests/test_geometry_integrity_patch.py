from __future__ import annotations

import unittest

from fh6garage.preview3d.geometry_integrity_patch import GEOMETRY_INTEGRITY_PATCH_REVISION
from fh6garage.preview3d import neutral_geometry
from fh6garage.preview3d import tire_production_trial_geometry
from fh6garage.preview3d.wheel_spec import AxleWheelSpec


class GeometryIntegrityPatchTests(unittest.TestCase):
    def test_native_tire_normalization_recenters_off_origin_geometry(self) -> None:
        positions = (
            (10.0, 20.0, 30.0),
            (12.0, 20.0, 30.0),
            (10.0, 24.0, 30.0),
            (10.0, 20.0, 36.0),
            (12.0, 24.0, 36.0),
        )
        axle = AxleWheelSpec("front", 165.0, 75.0, 15.0)
        normalized, _scales, _before, after = (
            tire_production_trial_geometry._normalize_positions_to_stock_dimensions(
                positions,
                axle,
            )
        )
        self.assertTrue(normalized)
        center = tuple(float(value) for value in after["center"])
        for value in center:
            self.assertAlmostEqual(value, 0.0, places=6)
        target_outer = (15.0 * 25.4 + 2.0 * 165.0 * 0.75) / 1000.0
        span = tuple(float(value) for value in after["span"])
        self.assertAlmostEqual(span[0], 0.165, places=6)
        self.assertAlmostEqual(span[1], target_outer, places=6)
        self.assertAlmostEqual(span[2], target_outer, places=6)

    def test_neutral_policy_reports_mechanical_geometry_preservation(self) -> None:
        result = neutral_geometry.NeutralGeometryResult(
            status="annotated",
            revision=3,
            mesh_count=1,
            ab_hidden_meshes=0,
            a_presentation_hidden_meshes=0,
            b_support_hidden_meshes=0,
            c_candidate_meshes=0,
            wheelstyle_hidden_meshes=0,
            extreme_thin_hidden_meshes=0,
            mapped_render_meshes=1,
            unmapped_render_meshes=0,
            carbin_instances_matched=1,
            carbin_instances_unmatched=0,
        )
        payload = result.as_dict()
        policy = payload["policy"]
        self.assertIn("preserve suspension", policy["B"])
        self.assertIn("preserve thin physical geometry", policy["thin_geometry"])
        self.assertEqual(
            policy["geometry_integrity_patch_revision"],
            GEOMETRY_INTEGRITY_PATCH_REVISION,
        )

    def test_patch_is_installed_process_wide(self) -> None:
        marker = "_fh6_geometry_integrity_patch_installed"
        self.assertTrue(getattr(neutral_geometry, marker, False))
        self.assertTrue(
            getattr(
                tire_production_trial_geometry._normalize_positions_to_stock_dimensions,
                marker,
                False,
            )
        )
        self.assertTrue(
            getattr(neutral_geometry.annotate_neutral_geometry, marker, False)
        )


if __name__ == "__main__":
    unittest.main()
