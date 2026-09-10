from __future__ import annotations

import unittest
from dataclasses import dataclass

from fh6garage.preview3d.manufacturer_materialbin_diagnostics import (
    trace_manufacturer_materialbin_payloads,
)


@dataclass
class _Payload:
    status: str
    resolution_mode: str
    cache_path: str | None = None
    texture_path: str | None = None

    def as_dict(self):
        return {
            "status": self.status,
            "resolution_mode": self.resolution_mode,
            "cache_path": self.cache_path,
            "texture_path": self.texture_path,
        }


def _p3d(path: str, *, uv4_status: str = "uv4_exact_kfps_accessor") -> dict:
    return {
        "status": "manufacturer_overlay_candidates_diagnosed",
        "candidates": [
            {
                "mesh_index": 2,
                "primitive_index": 0,
                "material_hash": "0xF7DBE8A7C839A675",
                "material_name": "carPaint",
                "selector": 0,
                "group_index": 0,
                "entry_index": 0,
                "entry_path": path,
                "uv4": {"status": uv4_status},
                "status": "manufacturer_entry_path_not_swatchbin",
            }
        ],
    }


def _helper(refs):
    return {
        "format": "fh6_materialbin_reference_diagnostic_v1",
        "revision": 1,
        "status": "materialbin_references_parsed",
        "gameDataModified": False,
        "references": [
            {
                "order": index,
                "sourceKind": source_kind,
                "sourceField": source_field,
                "parameterHash": parameter_hash,
                "pathHash": path_hash,
                "referencePath": path,
            }
            for index, (source_kind, source_field, parameter_hash, path_hash, path) in enumerate(refs)
        ],
    }


class ManufacturerMaterialbinDiagnosticsTests(unittest.TestCase):
    def test_matl_then_texture2d_order_selects_first_exact_resolved_swatch(self):
        assets = {
            "factory.materialbin": _Payload("resolved_payload", "game_loose_exact", "factory.cache"),
        }
        swatches = {
            "missing.swatchbin": _Payload("reference_unresolved", "none"),
            "body.swatchbin": _Payload("resolved_payload", "derived_zip_exact", "body.cache", "body.swatchbin"),
        }
        helper = _helper([
            ("matl", "Path", "", "", "missing.swatchbin"),
            ("texture2d", "TextureParameter.Path", "AABBCCDD", "11223344", "body.swatchbin"),
        ])

        report = trace_manufacturer_materialbin_payloads(
            _p3d("factory.materialbin"),
            "vehicle.zip",
            "cache",
            resolve_asset=lambda path, *_: assets[path],
            resolve_swatch=lambda path, *_: swatches[path],
            analyze_materialbin=lambda _path: helper,
        )
        self.assertEqual(report["exact_resolved_count"], 1)
        self.assertEqual(report["exact_shader_resolved_count"], 0)
        trace = report["traces"][0]
        self.assertEqual(trace["status"], "manufacturer_materialbin_swatch_resolved_exact")
        root = trace["root"]
        self.assertEqual(root["references"][0]["status"], "swatch_unresolved")
        self.assertEqual(root["references"][1]["status"], "swatch_resolved_exact")
        self.assertEqual(root["selected_swatch"]["reference_path"], "body.swatchbin")
        self.assertEqual(root["selected_swatch"]["parameter_hash"], "AABBCCDD")
        self.assertIsNone(root["selected_shader"])
        self.assertFalse(report["rendering_enabled"])
        self.assertFalse(report["game_data_modified"])

    def test_exact_shader_reference_is_material_chain_terminal_without_swatch_guess(self):
        assets = {
            "rossocorsa.materialbin": _Payload("resolved_payload", "derived_zip_exact", "rosso.cache"),
            "car_automotive_paint.shaderbin": _Payload("resolved_payload", "derived_zip_exact", "shader.cache"),
        }
        helper = _helper([
            ("matl", "Path", "", "", "car_automotive_paint.shaderbin"),
        ])
        swatch_called = {"value": False}

        def swatch_resolver(*_args):
            swatch_called["value"] = True
            raise AssertionError("shaderbin must not be sent to the swatch resolver")

        report = trace_manufacturer_materialbin_payloads(
            _p3d("rossocorsa.materialbin"),
            "vehicle.zip",
            "cache",
            resolve_asset=lambda path, *_: assets[path],
            resolve_swatch=swatch_resolver,
            analyze_materialbin=lambda _path: helper,
        )
        self.assertFalse(swatch_called["value"])
        self.assertEqual(report["exact_resolved_count"], 0)
        self.assertEqual(report["exact_shader_resolved_count"], 1)
        self.assertEqual(report["unresolved_count"], 0)
        trace = report["traces"][0]
        self.assertEqual(trace["status"], "manufacturer_materialbin_shader_resolved_exact")
        root = trace["root"]
        self.assertEqual(root["status"], "materialbin_selected_exact_shader")
        self.assertEqual(root["references"][0]["status"], "shader_resolved_exact")
        self.assertEqual(root["selected_shader"]["reference_path"], "car_automotive_paint.shaderbin")
        self.assertEqual(
            root["selected_lineage"],
            ["rossocorsa.materialbin", "car_automotive_paint.shaderbin"],
        )
        self.assertIsNone(root["selected_swatch"])

    def test_exact_shader_does_not_hide_later_exact_swatch(self):
        assets = {
            "factory.materialbin": _Payload("resolved_payload", "game_loose_exact", "factory.cache"),
            "paint.shaderbin": _Payload("resolved_payload", "game_loose_exact", "shader.cache"),
        }
        helper = _helper([
            ("matl", "Path", "", "", "paint.shaderbin"),
            ("texture2d", "TextureParameter.Path", "AABBCCDD", "11223344", "body.swatchbin"),
        ])
        report = trace_manufacturer_materialbin_payloads(
            _p3d("factory.materialbin"),
            "vehicle.zip",
            "cache",
            resolve_asset=lambda path, *_: assets[path],
            resolve_swatch=lambda path, *_: _Payload(
                "resolved_payload", "vehicle_archive_exact", "body.cache", path
            ),
            analyze_materialbin=lambda _path: helper,
        )
        self.assertEqual(report["exact_resolved_count"], 1)
        self.assertEqual(report["exact_shader_resolved_count"], 1)
        root = report["traces"][0]["root"]
        self.assertEqual(root["references"][0]["status"], "shader_resolved_exact")
        self.assertEqual(root["references"][1]["status"], "swatch_resolved_exact")
        self.assertEqual(root["selected_shader"]["reference_path"], "paint.shaderbin")
        self.assertEqual(root["selected_swatch"]["reference_path"], "body.swatchbin")

    def test_nested_materialbin_resolves_exact_swatch_and_preserves_lineage(self):
        assets = {
            "root.materialbin": _Payload("resolved_payload", "game_loose_exact", "root.cache"),
            "nested.materialbin": _Payload("resolved_payload", "derived_zip_exact", "nested.cache"),
        }
        reports = {
            "root.cache": _helper([("matl", "Path", "", "", "nested.materialbin")]),
            "nested.cache": _helper([("texture2d", "TextureParameter.Path", "12345678", "90ABCDEF", "flake.swatchbin")]),
        }

        report = trace_manufacturer_materialbin_payloads(
            _p3d("root.materialbin"),
            "vehicle.zip",
            "cache",
            resolve_asset=lambda path, *_: assets[path],
            resolve_swatch=lambda path, *_: _Payload("resolved_payload", "vehicle_archive_exact", "flake.cache", path),
            analyze_materialbin=lambda path: reports[path],
        )
        root = report["traces"][0]["root"]
        self.assertEqual(report["exact_resolved_count"], 1)
        self.assertEqual(root["selected_lineage"], ["root.materialbin", "nested.materialbin", "flake.swatchbin"])
        self.assertEqual(root["references"][0]["status"], "nested_materialbin_selected_exact_swatch")

    def test_nonexact_resolution_blocks_later_exact_reference_to_preserve_fts_order(self):
        helper = _helper([
            ("matl", "Path", "", "", "first.swatchbin"),
            ("texture2d", "TextureParameter.Path", "11111111", "22222222", "later.swatchbin"),
        ])
        swatches = {
            "first.swatchbin": _Payload("resolved_payload", "textures_zip_unique_filename", "first.cache"),
            "later.swatchbin": _Payload("resolved_payload", "game_loose_exact", "later.cache"),
        }
        report = trace_manufacturer_materialbin_payloads(
            _p3d("root.materialbin"),
            "vehicle.zip",
            "cache",
            resolve_asset=lambda *_: _Payload("resolved_payload", "game_loose_exact", "root.cache"),
            resolve_swatch=lambda path, *_: swatches[path],
            analyze_materialbin=lambda _path: helper,
        )
        self.assertEqual(report["exact_resolved_count"], 0)
        self.assertEqual(report["blocked_count"], 1)
        root = report["traces"][0]["root"]
        self.assertEqual(root["status"], "materialbin_blocked_by_nonexact_resolution")
        self.assertEqual(len(root["references"]), 1)
        self.assertEqual(root["references"][0]["reference_path"], "first.swatchbin")

    def test_cycle_is_treated_like_nested_null_and_parent_can_continue(self):
        helper = _helper([
            ("matl", "Path", "", "", "root.materialbin"),
            ("texture2d", "TextureParameter.Path", "ABCDEF01", "ABCDEF02", "body.swatchbin"),
        ])
        report = trace_manufacturer_materialbin_payloads(
            _p3d("root.materialbin"),
            "vehicle.zip",
            "cache",
            resolve_asset=lambda *_: _Payload("resolved_payload", "game_loose_exact", "root.cache"),
            resolve_swatch=lambda path, *_: _Payload("resolved_payload", "game_loose_exact", "body.cache", path),
            analyze_materialbin=lambda _path: helper,
        )
        root = report["traces"][0]["root"]
        self.assertEqual(report["exact_resolved_count"], 1)
        self.assertEqual(root["references"][0]["status"], "materialbin_cycle_deferred")
        self.assertEqual(root["selected_swatch"]["reference_path"], "body.swatchbin")

    def test_uv4_must_be_exact_before_materialbin_traversal(self):
        called = {"asset": False}
        def resolver(*_args):
            called["asset"] = True
            raise AssertionError("resolver must not run")

        report = trace_manufacturer_materialbin_payloads(
            _p3d("root.materialbin", uv4_status="uv4_missing"),
            "vehicle.zip",
            "cache",
            resolve_asset=resolver,
        )
        self.assertFalse(called["asset"])
        self.assertEqual(report["candidate_count"], 1)
        self.assertEqual(report["unresolved_count"], 1)
        self.assertEqual(report["traces"][0]["status"], "manufacturer_materialbin_uv4_contract_deferred")

    def test_malformed_helper_order_fails_closed(self):
        report = trace_manufacturer_materialbin_payloads(
            _p3d("root.materialbin"),
            "vehicle.zip",
            "cache",
            resolve_asset=lambda *_: _Payload("resolved_payload", "game_loose_exact", "root.cache"),
            analyze_materialbin=lambda _path: {
                "status": "materialbin_references_parsed",
                "references": [{"order": 7, "referencePath": "body.swatchbin"}],
            },
        )
        self.assertEqual(report["blocked_count"], 0)
        self.assertEqual(report["unresolved_count"], 1)
        self.assertEqual(report["traces"][0]["root"]["status"], "materialbin_reference_order_invalid")
        self.assertIsNone(report["traces"][0]["selected_swatch"])


if __name__ == "__main__":
    unittest.main()