from __future__ import annotations

import unittest
from pathlib import Path

from fh6garage.preview3d.native_material_render_plan import (
    NativeMaterialRenderPlan,
    NativeMaterialTextureIssue,
    NativeMaterialTextureSelection,
)
from fh6garage.preview3d.native_normal_texture_diagnostics import (
    NATIVE_NORMAL_TEXTURE_DIAGNOSTICS_REVISION,
    build_native_normal_texture_diagnostics,
)


UV_MODE = "kfps_baked_texcoord_transform_vflip_plus_material_tiling"


def _selection(
    *,
    semantic: str = "normal",
    dxgi_format: int = 83,
    compression_family: str = "bc5",
    is_srgb: bool = False,
    uv_channel: int = 0,
    uv_tiling_u: float = 2.0,
    uv_tiling_v: float = 3.0,
    uv_transform_mode: str = UV_MODE,
) -> NativeMaterialTextureSelection:
    return NativeMaterialTextureSelection(
        mesh_index=7,
        mesh_name="mesh_7",
        mesh_role="trim",
        material_name="trim_material",
        semantic=semantic,
        parameter_hash="39731A8A" if semantic == "normal" else "85F59336",
        parameter_name="NormalMap" if semantic == "normal" else "DiffuseTexture",
        texture_path=r"Game:\media\textures\trim\normal.swatchbin",
        dds_path=r"C:\cache\normal.dds",
        dds_sha256="a" * 64,
        width=1024,
        height=1024,
        mip_levels=8,
        dxgi_format=dxgi_format,
        compression_family=compression_family,
        is_srgb=is_srgb,
        uv_channel=uv_channel,
        uv_tiling_u=uv_tiling_u,
        uv_tiling_v=uv_tiling_v,
        uv_transform_mode=uv_transform_mode,
    )


def _plan(
    *selections: NativeMaterialTextureSelection,
    issues: tuple[NativeMaterialTextureIssue, ...] = (),
) -> NativeMaterialRenderPlan:
    return NativeMaterialRenderPlan(
        revision=2,
        status="ready" if selections else "unavailable",
        manifest_path="manifest.json",
        binding_count=len(selections) + len(issues),
        recognized_binding_count=len(selections) + len(issues),
        unknown_binding_count=0,
        selection_count=len(selections),
        issue_count=len(issues),
        selections=tuple(selections),
        issues=issues,
        game_data_modified=False,
    )


class NativeNormalTextureDiagnosticsTests(unittest.TestCase):
    def test_unsigned_bc5_standard_uv_is_candidate_but_rendering_stays_disabled(self):
        report = build_native_normal_texture_diagnostics(_plan(_selection()))
        self.assertEqual(report.revision, NATIVE_NORMAL_TEXTURE_DIAGNOSTICS_REVISION)
        self.assertEqual(report.status, "normal_candidates_deferred")
        self.assertEqual(report.candidate_count, 1)
        self.assertEqual(report.unsigned_bc5_candidate_count, 1)
        self.assertFalse(report.rendering_enabled)
        self.assertFalse(report.game_data_modified)
        candidate = report.candidates[0]
        self.assertTrue(candidate.unsigned_bc5_contract)
        self.assertTrue(candidate.standard_uv_contract)
        self.assertFalse(candidate.rendering_enabled)
        self.assertEqual(candidate.dxgi_format, 83)
        self.assertEqual(candidate.parameter_hash, "39731A8A")
        self.assertEqual(
            candidate.status,
            "bc5_decode_orientation_validation_required",
        )
        self.assertIn("Z reconstruction", candidate.detail)
        self.assertIn("Y/handedness", candidate.detail)

    def test_signed_or_non_bc5_normal_formats_do_not_advance(self):
        for selection in (
            _selection(dxgi_format=84, compression_family="bc5_snorm"),
            _selection(dxgi_format=99, compression_family="bc7", is_srgb=True),
        ):
            report = build_native_normal_texture_diagnostics(_plan(selection))
            self.assertEqual(report.unsigned_bc5_candidate_count, 0)
            self.assertFalse(report.candidates[0].unsigned_bc5_contract)
            self.assertEqual(report.candidates[0].status, "normal_format_deferred")

    def test_invalid_or_nonstandard_uv_contract_stays_deferred(self):
        for selection in (
            _selection(uv_channel=1),
            _selection(uv_tiling_u=0.0),
            _selection(uv_transform_mode="legacy_identity_uv"),
        ):
            report = build_native_normal_texture_diagnostics(_plan(selection))
            self.assertEqual(report.unsigned_bc5_candidate_count, 0)
            self.assertTrue(report.candidates[0].unsigned_bc5_contract)
            self.assertFalse(report.candidates[0].standard_uv_contract)
            self.assertEqual(report.candidates[0].status, "normal_uv_contract_deferred")

    def test_non_normal_texture_selections_are_not_reclassified(self):
        report = build_native_normal_texture_diagnostics(
            _plan(_selection(semantic="base_color", dxgi_format=99, compression_family="bc7", is_srgb=True))
        )
        self.assertEqual(report.status, "no_primary_normal_bindings")
        self.assertEqual(report.candidate_count, 0)
        self.assertEqual(report.unsigned_bc5_candidate_count, 0)

    def test_unresolved_normal_plan_issue_is_preserved_without_guessing(self):
        issue = NativeMaterialTextureIssue(
            mesh_index=4,
            mesh_name="mesh_4",
            material_name="body_material",
            semantic="normal",
            status="ambiguous_semantic_bindings",
            detail="Multiple exact normal bindings exist.",
            texture_paths=("A.swatchbin", "B.swatchbin"),
        )
        report = build_native_normal_texture_diagnostics(_plan(issues=(issue,)))
        self.assertEqual(report.status, "normal_bindings_unresolved")
        self.assertEqual(report.candidate_count, 0)
        self.assertEqual(report.unresolved_issue_count, 1)
        self.assertEqual(report.issues[0].status, "ambiguous_semantic_bindings")
        self.assertEqual(report.issues[0].texture_paths, ("A.swatchbin", "B.swatchbin"))

    def test_production_widget_prepares_diagnostics_without_enabling_rendering(self):
        root = Path(__file__).resolve().parents[1]
        text = (root / "fh6garage" / "preview3d" / "native_material_texture_patch.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("build_native_normal_texture_diagnostics(plan)", text)
        self.assertIn("_fh6_native_normal_texture_diagnostics", text)
        self.assertNotIn("uNativeNormal", text)
        self.assertNotIn("_NORMAL_TEXTURE_UNIT", text)

    def test_converter_records_normal_candidates_without_making_them_geometry_validity(self):
        root = Path(__file__).resolve().parents[1]
        text = (root / "fh6garage" / "preview3d" / "chassis_converter.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("native_normal_texture_diagnostics_revision", text)
        self.assertIn("build_native_material_render_plan(output)", text)
        self.assertIn("build_native_normal_texture_diagnostics(native_render_plan)", text)
        self.assertIn("native_normal_texture_status", text)
        self.assertIn("rendering_enabled\": False", text)
        self.assertIn("game_data_modified\": False", text)
        self.assertNotIn("raise ChassisConverterError(\n            \"Native normal", text)


if __name__ == "__main__":
    unittest.main()
