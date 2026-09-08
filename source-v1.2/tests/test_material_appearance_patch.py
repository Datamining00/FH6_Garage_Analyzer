from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "fh6garage" / "preview3d" / "material_appearance_patch.py"
SPEC = importlib.util.spec_from_file_location("fh6_material_appearance_patch_test", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
appearance = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(appearance)


class MaterialAppearancePatchTests(unittest.TestCase):
    def _flat_shader(self) -> str:
        return (
            "#version 330 core\n"
            "flat in int vDirectUv;\n"
            "out vec4 fragColor;\n"
            "            void main() {\n"
            + appearance._FLAT_LIGHTING
            + "                vec4 decal = vec4(0.0);\n"
            + appearance._FLAT_OUTPUT
            + "            }\n"
        )

    def _vertex_shader(self) -> str:
        return (
            "#version 330 core\n"
            "            layout(location=6) in float inDirectUv;\n"
            "            flat out int vDirectUv;\n"
            "            void main() {\n"
            "                vDirectUv = int(floor(inDirectUv + 0.5));\n"
            "            }\n"
        )

    def test_upgrades_livery_to_pre_lighting_pbr_composite(self):
        upgraded = appearance.upgrade_fragment_shader(self._flat_shader())
        self.assertIn("fh6DistributionGGX", upgraded)
        self.assertIn("fh6GeometrySmith", upgraded)
        self.assertIn("fh6FresnelSchlick", upgraded)
        self.assertIn("fh6ShadeMaterial", upgraded)
        self.assertIn("vMaterialParams", upgraded)
        self.assertIn("vMaterialAux", upgraded)
        self.assertIn("decalLinear", upgraded)
        self.assertIn("albedo = mix(albedo, decalLinear, decal.a)", upgraded)
        self.assertIn("clearcoat", upgraded)
        self.assertIn("roughness", upgraded)
        self.assertIn("fh6Environment", upgraded)
        self.assertNotIn("mix(base, decal.rgb, decal.a)", upgraded)
        self.assertNotIn("vColor * (0.34 + 0.66 * d)", upgraded)

    def test_vertex_shader_carries_native_material_streams(self):
        upgraded = appearance.upgrade_vertex_shader(self._vertex_shader())
        self.assertIn("layout(location=7) in vec4 inMaterialParams", upgraded)
        self.assertIn("layout(location=8) in vec4 inMaterialAux", upgraded)
        self.assertIn("vMaterialParams = inMaterialParams", upgraded)
        self.assertIn("vMaterialAux = inMaterialAux", upgraded)

    def test_upgrade_is_idempotent(self):
        once = appearance.upgrade_fragment_shader(self._flat_shader())
        twice = appearance.upgrade_fragment_shader(once)
        self.assertEqual(once, twice)
        vertex_once = appearance.upgrade_vertex_shader(self._vertex_shader())
        self.assertEqual(vertex_once, appearance.upgrade_vertex_shader(vertex_once))

    def test_unknown_shader_is_left_unchanged(self):
        source = "#version 330 core\nvoid main() {}\n"
        self.assertEqual(appearance.upgrade_fragment_shader(source), source)
        self.assertEqual(appearance.upgrade_vertex_shader(source), source)

    def test_native_roughness_metalness_and_clearcoat_override_role_defaults(self):
        params, aux, used = appearance.material_values_for_primitive(
            "trim",
            {
                "resolutionMode": "embedded_material_shader_parameters",
                "roughness": 0.18,
                "metalness": 0.76,
                "clearCoatGloss": 0.90,
                "baseColor": [0.12, 0.25, 0.50, 1.0],
            },
        )
        self.assertTrue(used)
        np.testing.assert_allclose(params, [0.76, 0.18, 1.0, 0.10], atol=1e-6)
        np.testing.assert_allclose(aux, [0.0, 0.12, 0.25, 0.50], atol=1e-6)

    def test_gloss_converts_to_microfacet_roughness(self):
        params, _aux, used = appearance.material_values_for_primitive(
            "dark",
            {
                "resolutionMode": "embedded_material_shader_parameters",
                "gloss": 0.72,
            },
        )
        self.assertTrue(used)
        self.assertAlmostEqual(float(params[1]), 0.28, places=6)

    def test_carpaint_keeps_dynamic_base_color_but_uses_native_surface_response(self):
        params, aux, used = appearance.material_values_for_primitive(
            "paint",
            {
                "resolutionMode": "embedded_material_shader_parameters",
                "roughness": 0.20,
                "baseColor": [1.0, 0.0, 0.0, 1.0],
            },
        )
        self.assertTrue(used)
        self.assertAlmostEqual(float(params[1]), 0.20, places=6)
        self.assertLess(float(aux[1]), 0.0)

    def test_unresolved_material_keeps_role_defaults(self):
        params, aux, used = appearance.material_values_for_primitive(
            "glass",
            {"resolutionMode": "embedded_material_not_found"},
        )
        self.assertFalse(used)
        np.testing.assert_allclose(params, [0.0, 0.08, 0.35, 0.05], atol=1e-6)
        self.assertAlmostEqual(float(aux[0]), 0.72, places=6)

    def test_no_vehicle_specific_material_tuning(self):
        text = MODULE_PATH.read_text(encoding="utf-8")
        for token in (
            "FER_FXX",
            "TOY_2000GT",
            "HYU_",
            "Car ID",
            "car_id",
            "model_code",
        ):
            with self.subTest(token=token):
                self.assertNotIn(token, text)

    def test_existing_livery_mapping_contract_is_not_reimplemented(self):
        text = MODULE_PATH.read_text(encoding="utf-8")
        for token in (
            "uSourceRegions",
            "uPaintRegions",
            "uProjectionAxes",
            "uProjectionMaskRegions",
            "coverageForSlot",
            "geometrySide",
        ):
            with self.subTest(token=token):
                self.assertNotIn(token, text)


if __name__ == "__main__":
    unittest.main()
