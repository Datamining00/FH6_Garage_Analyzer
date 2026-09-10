from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from fh6garage.preview3d.native_emissive_texture_patch import (
    build_native_emissive_draw_ranges,
    upgrade_native_emissive_fragment_shader,
)
from fh6garage.preview3d.native_material_render_plan import (
    NativeMaterialRenderPlan,
    NativeMaterialTextureSelection,
)


def _selection(
    mesh_index: int,
    path: str,
    *,
    dxgi_format: int = 99,
    is_srgb: bool = True,
    uv_channel: int = 0,
    uv_mode: str = "kfps_baked_texcoord_transform_vflip_plus_material_tiling",
) -> NativeMaterialTextureSelection:
    return NativeMaterialTextureSelection(
        mesh_index=mesh_index,
        mesh_name=f"mesh_{mesh_index}",
        mesh_role="trim",
        material_name="native_material",
        semantic="emissive",
        parameter_hash="020B22EB",
        parameter_name="EmissiveMap",
        texture_path=r"Game:\media\textures\emissive.swatchbin",
        dds_path=path,
        dds_sha256="c" * 64,
        width=8,
        height=8,
        mip_levels=1,
        dxgi_format=dxgi_format,
        compression_family="bc7_srgb" if dxgi_format == 99 else "rgba8_srgb",
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
        indices=[0] * indices,
        primitive_diagnostics=(
            {
                "mesh_index": mesh_index,
                "primitive_index": 0,
                "triangle_count": indices // 3,
            },
        ),
    )


class NativeEmissiveTexturePatchTests(unittest.TestCase):
    def test_shader_samples_srgb_emissive_after_albedo_and_before_pbr(self):
        fragment = """            in vec2 vMaterialUV;
            uniform int uNativeSurfaceRoughnessMode;
                vec3 albedo = vMaterialAux.y >= 0.0
                    ? clamp(vMaterialAux.yzw, 0.0, 1.0)
                    : pow(clamp(vColor, 0.0, 1.0), vec3(2.2));
                albedo = mix(albedo, decalLinear, decal.a);
                vec3 shaded = fh6ShadeMaterial(
                    albedo,
                    N,
                    V,
                    effectiveMaterialParams,
                    clamp(vMaterialAux.x, 0.0, 1.0),
                    vMaterialF0,
                    vMaterialCoatF0,
                    vMaterialEmission);
"""
        upgraded = upgrade_native_emissive_fragment_shader(fragment)
        self.assertIn("uniform bool uNativeEmissiveEnabled", upgraded)
        self.assertIn("sampler2D uNativeEmissive", upgraded)
        self.assertIn("vMaterialUV * uNativeEmissiveTiling", upgraded)
        self.assertIn("nativeEmissiveTexel", upgraded)
        self.assertIn("effectiveEmission.rgb *= nativeEmissiveTexel", upgraded)
        self.assertIn(
            "effectiveEmission.rgb = albedo * nativeEmissiveTexel", upgraded
        )
        self.assertIn("effectiveEmission);", upgraded)
        albedo_pos = upgraded.index("albedo = mix(albedo, decalLinear")
        emissive_pos = upgraded.index("nativeEmissiveTexel")
        pbr_pos = upgraded.index("vec3 shaded = fh6ShadeMaterial")
        self.assertLess(albedo_pos, emissive_pos)
        self.assertLess(emissive_pos, pbr_pos)

    def test_single_srgb_emissive_binding_is_enabled(self):
        ranges, issues = build_native_emissive_draw_ranges(
            _scene(), _plan(_selection(1, "emissive.dds"))
        )
        self.assertEqual(issues, ())
        self.assertEqual(len(ranges), 1)
        self.assertTrue(ranges[0].dds_path.endswith("emissive.dds"))
        self.assertEqual(
            (ranges[0].uv_tiling_u, ranges[0].uv_tiling_v),
            (2.0, 3.0),
        )

    def test_linear_or_nonstandard_uv_emissive_fails_closed(self):
        selections = (
            _selection(1, "linear.dds", dxgi_format=98, is_srgb=False),
            _selection(1, "uv1.dds", uv_channel=1),
            _selection(1, "unknown_uv.dds", uv_mode="unknown"),
        )
        for selection in selections:
            ranges, issues = build_native_emissive_draw_ranges(
                _scene(), _plan(selection)
            )
            self.assertEqual(len(issues), 1)
            self.assertIsNone(ranges[0].dds_path)

    def test_multiple_different_emissive_dds_fail_closed(self):
        ranges, issues = build_native_emissive_draw_ranges(
            _scene(),
            _plan(
                _selection(1, "emissive_a.dds"),
                _selection(1, "emissive_b.dds"),
            ),
        )
        self.assertEqual(len(issues), 1)
        self.assertIn("multiple emissive", issues[0])
        self.assertIsNone(ranges[0].dds_path)

    def test_invalid_sibling_disables_valid_emissive_for_same_mesh(self):
        ranges, issues = build_native_emissive_draw_ranges(
            _scene(),
            _plan(
                _selection(1, "emissive.dds"),
                _selection(1, "linear.dds", dxgi_format=98, is_srgb=False),
            ),
        )
        self.assertEqual(len(issues), 1)
        self.assertIsNone(ranges[0].dds_path)

    def test_draw_ranges_follow_flattened_primitive_order(self):
        scene = SimpleNamespace(
            indices=[0] * 15,
            primitive_diagnostics=(
                {"mesh_index": 2, "primitive_index": 0, "triangle_count": 2},
                {"mesh_index": 7, "primitive_index": 0, "triangle_count": 3},
            ),
        )
        ranges, issues = build_native_emissive_draw_ranges(
            scene, _plan(_selection(7, "emissive.dds"))
        )
        self.assertEqual(issues, ())
        self.assertEqual((ranges[0].first_index, ranges[0].index_count), (0, 6))
        self.assertIsNone(ranges[0].dds_path)
        self.assertEqual((ranges[1].first_index, ranges[1].index_count), (6, 9))
        self.assertTrue(ranges[1].dds_path.endswith("emissive.dds"))

    def test_draw_range_mismatch_is_rejected(self):
        scene = SimpleNamespace(
            indices=[0] * 6,
            primitive_diagnostics=(
                {"mesh_index": 1, "primitive_index": 0, "triangle_count": 1},
            ),
        )
        with self.assertRaisesRegex(ValueError, "cover 3 indices"):
            build_native_emissive_draw_ranges(scene, _plan())

    def test_lazy_installer_orders_emissive_after_normal_before_transform(self):
        root = Path(__file__).resolve().parents[1]
        text = (
            root / "fh6garage" / "preview3d" / "__init__.py"
        ).read_text(encoding="utf-8")
        texture = text.index("install_native_material_texture_patch()")
        normal = text.index("install_native_normal_texture_patch()")
        emissive = text.index("install_native_emissive_texture_patch()")
        transform = text.index("install_native_transform_chain_v3()")
        self.assertLess(texture, normal)
        self.assertLess(normal, emissive)
        self.assertLess(emissive, transform)


if __name__ == "__main__":
    unittest.main()
