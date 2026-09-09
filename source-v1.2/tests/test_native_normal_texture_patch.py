from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from fh6garage.preview3d.native_material_render_plan import (
    NativeMaterialRenderPlan,
    NativeMaterialTextureSelection,
)
from fh6garage.preview3d.native_normal_texture_patch import (
    NATIVE_NORMAL_Y_SIGN,
    build_native_normal_draw_ranges,
    upgrade_native_normal_fragment_shader,
)


def _normal_selection(
    mesh_index: int,
    path: str,
    *,
    dxgi_format: int = 83,
    compression_family: str = "bc5",
    is_srgb: bool = False,
    uv_channel: int = 0,
    uv_mode: str = "kfps_baked_texcoord_transform_vflip_plus_material_tiling",
) -> NativeMaterialTextureSelection:
    return NativeMaterialTextureSelection(
        mesh_index=mesh_index,
        mesh_name=f"mesh_{mesh_index}",
        mesh_role="trim",
        material_name="native_material",
        semantic="normal",
        parameter_hash="39731A8A",
        parameter_name="NormalMap",
        texture_path=r"Game:\media\textures\normal.swatchbin",
        dds_path=path,
        dds_sha256="b" * 64,
        width=8,
        height=8,
        mip_levels=1,
        dxgi_format=dxgi_format,
        compression_family=compression_family,
        is_srgb=is_srgb,
        uv_channel=uv_channel,
        uv_tiling_u=2.0,
        uv_tiling_v=3.0,
        uv_transform_mode=uv_mode,
    )


def _plan(*selections: NativeMaterialTextureSelection) -> NativeMaterialRenderPlan:
    return NativeMaterialRenderPlan(
        revision=2,
        status="ready",
        manifest_path="manifest.json",
        binding_count=len(selections),
        recognized_binding_count=len(selections),
        unknown_binding_count=0,
        selection_count=len(selections),
        issue_count=0,
        selections=tuple(selections),
        issues=(),
        game_data_modified=False,
    )


def _scene(indices: int = 6, mesh_index: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        indices=np.zeros(indices, dtype=np.uint32),
        primitive_diagnostics=(
            {"mesh_index": mesh_index, "primitive_index": 0, "triangle_count": indices // 3},
        ),
    )


class NativeNormalTexturePatchTests(unittest.TestCase):
    def test_reference_shader_uses_bc5_xy_positive_z_no_green_flip_and_derivative_tbn(self):
        fragment = """            in vec2 vMaterialUV;
            uniform int uNativeSurfaceRoughnessMode;
                vec3 N = normalize(vNormal);
                vec3 V = normalize(uEye - vWorld);
"""
        upgraded = upgrade_native_normal_fragment_shader(fragment)
        self.assertIn("uniform bool uNativeNormalEnabled", upgraded)
        self.assertIn("sampler2D uNativeNormal", upgraded)
        self.assertIn("texture(uNativeNormal, nativeNormalUV).rg * 2.0 - 1.0", upgraded)
        self.assertIn("nativeXY.y *= uNativeNormalYSign", upgraded)
        self.assertIn("sqrt(max(0.0, 1.0 - dot(nativeXY, nativeXY)))", upgraded)
        self.assertIn("dFdx(vWorld)", upgraded)
        self.assertIn("dFdy(nativeNormalUV)", upgraded)
        self.assertIn("mat3 TBN", upgraded)
        self.assertEqual(NATIVE_NORMAL_Y_SIGN, 1.0)

    def test_single_linear_bc5_normal_is_enabled_for_mesh(self):
        ranges, issues = build_native_normal_draw_ranges(
            _scene(), _plan(_normal_selection(1, "normal.dds"))
        )
        self.assertEqual(issues, ())
        self.assertEqual(len(ranges), 1)
        self.assertTrue(ranges[0].dds_path.endswith("normal.dds"))
        self.assertEqual((ranges[0].uv_tiling_u, ranges[0].uv_tiling_v), (2.0, 3.0))

    def test_non_bc5_srgb_or_nonstandard_uv_fail_closed(self):
        selections = (
            _normal_selection(1, "bc7.dds", dxgi_format=98, compression_family="bc7"),
            _normal_selection(1, "srgb.dds", is_srgb=True),
            _normal_selection(1, "uv1.dds", uv_channel=1),
            _normal_selection(1, "unknown_uv.dds", uv_mode="unknown"),
        )
        for selection in selections:
            ranges, issues = build_native_normal_draw_ranges(_scene(), _plan(selection))
            self.assertEqual(len(issues), 1)
            self.assertIsNone(ranges[0].dds_path)

    def test_multiple_different_normal_dds_fail_closed(self):
        ranges, issues = build_native_normal_draw_ranges(
            _scene(),
            _plan(
                _normal_selection(1, "normal_a.dds"),
                _normal_selection(1, "normal_b.dds"),
            ),
        )
        self.assertEqual(len(issues), 1)
        self.assertIn("multiple primary normal", issues[0])
        self.assertIsNone(ranges[0].dds_path)

    def test_invalid_sibling_disables_valid_normal_for_same_mesh(self):
        ranges, issues = build_native_normal_draw_ranges(
            _scene(),
            _plan(
                _normal_selection(1, "normal.dds"),
                _normal_selection(1, "invalid.dds", dxgi_format=98, compression_family="bc7"),
            ),
        )
        self.assertEqual(len(issues), 1)
        self.assertIsNone(ranges[0].dds_path)

    def test_draw_ranges_follow_flattened_primitive_order(self):
        scene = SimpleNamespace(
            indices=np.zeros(15, dtype=np.uint32),
            primitive_diagnostics=(
                {"mesh_index": 2, "primitive_index": 0, "triangle_count": 2},
                {"mesh_index": 7, "primitive_index": 0, "triangle_count": 3},
            ),
        )
        ranges, issues = build_native_normal_draw_ranges(
            scene, _plan(_normal_selection(7, "normal.dds"))
        )
        self.assertEqual(issues, ())
        self.assertEqual((ranges[0].first_index, ranges[0].index_count), (0, 6))
        self.assertIsNone(ranges[0].dds_path)
        self.assertEqual((ranges[1].first_index, ranges[1].index_count), (6, 9))
        self.assertTrue(ranges[1].dds_path.endswith("normal.dds"))

    def test_draw_range_mismatch_is_rejected(self):
        scene = SimpleNamespace(
            indices=np.zeros(6, dtype=np.uint32),
            primitive_diagnostics=({"mesh_index": 1, "primitive_index": 0, "triangle_count": 1},),
        )
        with self.assertRaisesRegex(ValueError, "cover 3 indices"):
            build_native_normal_draw_ranges(scene, _plan())


if __name__ == "__main__":
    unittest.main()
