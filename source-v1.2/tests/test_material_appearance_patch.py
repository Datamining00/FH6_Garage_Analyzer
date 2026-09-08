from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

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
            "out vec4 fragColor;\n"
            "            void main() {\n"
            + appearance._FLAT_LIGHTING
            + "                vec4 decal = vec4(0.0);\n"
            + appearance._FLAT_OUTPUT
            + "            }\n"
        )

    def test_upgrades_livery_to_pre_lighting_pbr_composite(self):
        upgraded = appearance.upgrade_fragment_shader(self._flat_shader())
        self.assertIn("fh6DistributionGGX", upgraded)
        self.assertIn("fh6GeometrySmith", upgraded)
        self.assertIn("fh6FresnelSchlick", upgraded)
        self.assertIn("fh6ShadeMaterial", upgraded)
        self.assertIn("decalLinear", upgraded)
        self.assertIn("albedo = mix(albedo, decalLinear, decal.a)", upgraded)
        self.assertIn("clearcoat", upgraded)
        self.assertIn("roughness", upgraded)
        self.assertIn("fh6Environment", upgraded)
        self.assertNotIn("mix(base, decal.rgb, decal.a)", upgraded)
        self.assertNotIn("vColor * (0.34 + 0.66 * d)", upgraded)

    def test_upgrade_is_idempotent(self):
        once = appearance.upgrade_fragment_shader(self._flat_shader())
        twice = appearance.upgrade_fragment_shader(once)
        self.assertEqual(once, twice)

    def test_unknown_shader_is_left_unchanged(self):
        source = "#version 330 core\nvoid main() {}\n"
        self.assertEqual(appearance.upgrade_fragment_shader(source), source)

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
