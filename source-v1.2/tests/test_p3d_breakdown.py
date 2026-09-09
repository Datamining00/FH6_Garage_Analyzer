from __future__ import annotations

import unittest

from fh6garage.preview3d.manufacturer_materialbin_diagnostics import (
    _p3d_breakdown,
    trace_manufacturer_materialbin_payloads,
)


class P3dBreakdownTests(unittest.TestCase):
    def test_breakdown_identifies_dominant_pre_p3f_rejection(self):
        report = {
            "status": "manufacturer_overlay_candidates_diagnosed",
            "paint_primitive_count": 3,
            "evaluated_binding_count": 1,
            "exact_candidate_count": 0,
            "candidates": [
                {
                    "mesh_index": 1,
                    "primitive_index": 0,
                    "mesh_name": "PaintA",
                    "material_hash": "0x1111111111111111",
                    "material_name": "carpaint",
                    "selector": None,
                    "group_index": None,
                    "entry_index": None,
                    "entry_path": None,
                    "uv4": {"status": "uv4_exact_kfps_accessor", "count": 3, "position_count": 3},
                    "status": "binding_record_unmatched",
                },
                {
                    "mesh_index": 2,
                    "primitive_index": 0,
                    "mesh_name": "PaintB",
                    "material_hash": "0x2222222222222222",
                    "material_name": "carpaint",
                    "selector": None,
                    "group_index": None,
                    "entry_index": None,
                    "entry_path": None,
                    "uv4": {"status": "uv4_exact_kfps_accessor", "count": 3, "position_count": 3},
                    "status": "binding_record_unmatched",
                },
                {
                    "mesh_index": 3,
                    "primitive_index": 0,
                    "mesh_name": "PaintC",
                    "material_hash": None,
                    "material_name": None,
                    "selector": None,
                    "group_index": None,
                    "entry_index": None,
                    "entry_path": None,
                    "uv4": {"status": "uv4_missing", "count": None, "position_count": None},
                    "status": "binding_hash_invalid",
                },
            ],
        }

        breakdown = _p3d_breakdown(report)
        self.assertEqual(breakdown["status"], "p3d_breakdown_diagnosed")
        self.assertEqual(breakdown["paint_primitive_count"], 3)
        self.assertEqual(breakdown["with_material_name_count"], 2)
        self.assertEqual(breakdown["with_binding_hash_count"], 2)
        self.assertEqual(breakdown["row_status_counts"]["binding_record_unmatched"], 2)
        self.assertEqual(breakdown["entry_path_kind_counts"]["missing"], 3)
        self.assertEqual(breakdown["p3f_materialbin_deferred_count"], 0)
        self.assertEqual(
            breakdown["diagnostic_focus"],
            "no_materialbin_candidate_dominant_status:binding_record_unmatched:2",
        )
        statuses = {sample["status"] for sample in breakdown["rejection_samples"]}
        self.assertEqual(statuses, {"binding_record_unmatched", "binding_hash_invalid"})

    def test_breakdown_marks_materialbin_handoff_and_uv4_readiness(self):
        report = {
            "status": "manufacturer_overlay_candidates_diagnosed",
            "paint_primitive_count": 2,
            "evaluated_binding_count": 2,
            "exact_candidate_count": 0,
            "candidates": [
                {
                    "mesh_index": 1,
                    "primitive_index": 0,
                    "mesh_name": "PaintA",
                    "material_hash": "0x1111111111111111",
                    "material_name": "carpaint",
                    "selector": 0,
                    "group_index": 0,
                    "entry_index": 0,
                    "entry_path": "factory.materialbin",
                    "uv4": {"status": "uv4_exact_kfps_accessor", "count": 3, "position_count": 3},
                    "status": "manufacturer_entry_path_not_swatchbin",
                },
                {
                    "mesh_index": 2,
                    "primitive_index": 0,
                    "mesh_name": "PaintB",
                    "material_hash": "0x2222222222222222",
                    "material_name": "carpaint2",
                    "selector": 0,
                    "group_index": 0,
                    "entry_index": 1,
                    "entry_path": "secondary.materialbin",
                    "uv4": {"status": "uv4_missing", "count": None, "position_count": 3},
                    "status": "manufacturer_entry_path_not_swatchbin",
                },
            ],
        }

        breakdown = _p3d_breakdown(report)
        self.assertEqual(breakdown["entry_path_kind_counts"]["materialbin"], 2)
        self.assertEqual(breakdown["p3f_materialbin_deferred_count"], 2)
        self.assertEqual(breakdown["p3f_materialbin_uv4_ready_count"], 1)
        self.assertEqual(breakdown["diagnostic_focus"], "materialbin_candidates_present_uv4_ready")

    def test_p3f_report_always_carries_p3d_breakdown(self):
        p3d = {
            "status": "manufacturer_overlay_candidates_diagnosed",
            "paint_primitive_count": 0,
            "evaluated_binding_count": 0,
            "exact_candidate_count": 0,
            "candidates": [],
        }
        report = trace_manufacturer_materialbin_payloads(
            p3d,
            "vehicle.zip",
            "cache",
        )
        self.assertEqual(report["revision"], 2)
        self.assertEqual(report["candidate_count"], 0)
        self.assertEqual(report["p3d_breakdown"]["diagnostic_focus"], "no_paint_primitives_exported")


if __name__ == "__main__":
    unittest.main()
