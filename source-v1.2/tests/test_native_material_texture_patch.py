from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from fh6garage.preview3d.native_material_render_plan import (
    NativeMaterialRenderPlan,
    NativeMaterialTextureSelection,
)
from fh6garage.preview3d.native_material_texture_patch import (
    _copy_native_texture_sidecar,
    build_native_base_color_draw_ranges,
    upgrade_native_texture_fragment_shader,
    upgrade_native_texture_vertex_shader,
)


def _selection(mesh_index: int, path: str, semantic: str = "base_color") -> NativeMaterialTextureSelection:
    return NativeMaterialTextureSelection(
        mesh_index=mesh_index,
        mesh_name=f"mesh_{mesh_index}",
        mesh_role="trim",
        material_name="trim_material",
        semantic=semantic,
        parameter_hash="85F59336",
        parameter_name="DiffuseTexture",
        texture_path=r"Game:\media\textures\trim\body.swatchbin",
        dds_path=path,
        dds_sha256="a" * 64,
        width=4,
        height=4,
        mip_levels=1,
        dxgi_format=99,
        compression_family="bc7",
        is_srgb=True,
        uv_channel=0,
        uv_tiling_u=2.0,
        uv_tiling_v=3.0,
        uv_transform_mode="kfps_baked_texcoord_transform_vflip_plus_material_tiling",
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


class NativeMaterialTexturePatchTests(unittest.TestCase):
    def test_shader_layers_native_base_texture_before_livery_and_pbr(self):
        vertex = """            layout(location=11) in vec4 inMaterialEmission;
            out vec4 vMaterialEmission;
                vMaterialEmission = inMaterialEmission;
"""
        upgraded_vertex = upgrade_native_texture_vertex_shader(vertex)
        self.assertIn("layout(location=12) in vec2 inMaterialUV", upgraded_vertex)
        self.assertIn("out vec2 vMaterialUV", upgraded_vertex)
        self.assertIn("vMaterialUV = inMaterialUV", upgraded_vertex)

        fragment = """            in vec4 vMaterialEmission;
            uniform vec3 uEye;
                vec3 albedo = vMaterialAux.y >= 0.0
                    ? clamp(vMaterialAux.yzw, 0.0, 1.0)
                    : pow(clamp(vColor, 0.0, 1.0), vec3(2.2));
                albedo = mix(albedo, decalLinear, decal.a);
"""
        upgraded = upgrade_native_texture_fragment_shader(fragment)
        self.assertIn("uNativeBaseColorEnabled", upgraded)
        self.assertIn("sampler2D uNativeBaseColor", upgraded)
        self.assertIn("vMaterialUV * uNativeBaseColorTiling", upgraded)
        texture_pos = upgraded.index("texture(uNativeBaseColor")
        livery_pos = upgraded.index("albedo = mix(albedo, decalLinear")
        self.assertLess(texture_pos, livery_pos)

    def test_draw_ranges_follow_flattened_primitive_index_order(self):
        scene = SimpleNamespace(
            indices=np.zeros(15, dtype=np.uint32),
            primitive_diagnostics=(
                {"mesh_index": 2, "primitive_index": 0, "triangle_count": 2},
                {"mesh_index": 7, "primitive_index": 0, "triangle_count": 3},
            ),
        )
        ranges, issues = build_native_base_color_draw_ranges(scene, _plan(_selection(7, "B.dds")))
        self.assertEqual(issues, ())
        self.assertEqual(len(ranges), 2)
        self.assertEqual((ranges[0].first_index, ranges[0].index_count), (0, 6))
        self.assertIsNone(ranges[0].dds_path)
        self.assertEqual((ranges[1].first_index, ranges[1].index_count), (6, 9))
        self.assertTrue(ranges[1].dds_path.endswith("B.dds"))
        self.assertEqual((ranges[1].uv_tiling_u, ranges[1].uv_tiling_v), (2.0, 3.0))

    def test_two_base_semantics_with_different_dds_fail_closed_per_mesh(self):
        scene = SimpleNamespace(
            indices=np.zeros(3, dtype=np.uint32),
            primitive_diagnostics=({"mesh_index": 1, "primitive_index": 0, "triangle_count": 1},),
        )
        plan = _plan(
            _selection(1, "base.dds", "base_color"),
            _selection(1, "alpha.dds", "base_color_alpha"),
        )
        ranges, issues = build_native_base_color_draw_ranges(scene, plan)
        self.assertEqual(len(issues), 1)
        self.assertIsNone(ranges[0].dds_path)

    def test_draw_range_mismatch_is_rejected(self):
        scene = SimpleNamespace(
            indices=np.zeros(6, dtype=np.uint32),
            primitive_diagnostics=({"mesh_index": 1, "primitive_index": 0, "triangle_count": 1},),
        )
        with self.assertRaisesRegex(ValueError, "cover 3 indices"):
            build_native_base_color_draw_ranges(scene, _plan())

    def test_read_only_texture_manifest_propagates_to_native_tire_derivative(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "car.glb"
            selected = root / "trial" / "car__native_tires.glb"
            source.write_bytes(b"glTF")
            selected.parent.mkdir()
            selected.write_bytes(b"glTF")
            source_manifest = source.with_suffix(source.suffix + ".native_textures.json")
            payload = {
                "format": "fh6_native_material_texture_resolution_v3",
                "game_data_modified": False,
                "textures": [],
            }
            source_manifest.write_text(json.dumps(payload), encoding="utf-8")
            self.assertTrue(_copy_native_texture_sidecar(source, selected))
            copied = selected.with_suffix(selected.suffix + ".native_textures.json")
            self.assertEqual(json.loads(copied.read_text(encoding="utf-8")), payload)

            payload["game_data_modified"] = True
            source_manifest.write_text(json.dumps(payload), encoding="utf-8")
            copied.unlink()
            self.assertFalse(_copy_native_texture_sidecar(source, selected))
            self.assertFalse(copied.exists())

    def test_lazy_installer_orders_texture_after_material_stream_wiring(self):
        root = Path(__file__).resolve().parents[1]
        text = (root / "fh6garage" / "preview3d" / "__init__.py").read_text(encoding="utf-8")
        pbr = text.index("install_game_like_material_patch()")
        wiring = text.index("install_material_runtime_wiring_patch()")
        texture = text.index("install_native_material_texture_patch()")
        transform = text.index("install_native_transform_chain_v3()")
        self.assertLess(pbr, wiring)
        self.assertLess(wiring, texture)
        self.assertLess(texture, transform)


if __name__ == "__main__":
    unittest.main()
