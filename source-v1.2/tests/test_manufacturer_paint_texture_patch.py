from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fh6garage.preview3d.manufacturer_paint_texture_patch import (
    _material_tiling,
    upgrade_manufacturer_paint_fragment_shader,
    upgrade_manufacturer_paint_vertex_shader,
)


class ManufacturerPaintTexturePatchTests(unittest.TestCase):
    def test_uv4_vertex_attribute_layers_after_standard_material_uv(self):
        source = (
            "            layout(location=12) in vec2 inMaterialUV;\n"
            "            out vec2 vMaterialUV;\n"
            "                vMaterialUV = inMaterialUV;\n"
        )
        upgraded = upgrade_manufacturer_paint_vertex_shader(source)
        self.assertIn("layout(location=13) in vec2 inManufacturerUV4;", upgraded)
        self.assertIn("out vec2 vManufacturerUV4;", upgraded)
        self.assertIn("vManufacturerUV4 = inManufacturerUV4;", upgraded)
        self.assertEqual(upgrade_manufacturer_paint_vertex_shader(upgraded), upgraded)

    def test_swatch_tints_base_before_existing_livery_composite(self):
        source = (
            "            in vec2 vMaterialUV;\n"
            "            uniform vec2 uNativeEmissiveTiling;\n"
            "                albedo = mix(albedo, decalLinear, decal.a);\n"
        )
        upgraded = upgrade_manufacturer_paint_fragment_shader(source)
        self.assertIn("uniform bool uManufacturerPaintEnabled;", upgraded)
        self.assertIn("texture(\n                        uManufacturerPaint,", upgraded)
        self.assertIn("albedo *= manufacturerSwatch;", upgraded)
        self.assertIn("albedo = mix(albedo, decalLinear, decal.a);", upgraded)
        self.assertLess(
            upgraded.index("albedo *= manufacturerSwatch;"),
            upgraded.index("albedo = mix(albedo, decalLinear, decal.a);"),
        )
        self.assertEqual(upgrade_manufacturer_paint_fragment_shader(upgraded), upgraded)

    def test_material_tiling_requires_exact_finite_nonzero_provenance(self):
        mesh = {
            "extras": {
                "kfps_material_appearance": {
                    "uvTiling": [2.0, 3.0],
                }
            }
        }
        self.assertEqual(_material_tiling(mesh), (2.0, 3.0))
        with self.assertRaises(ValueError):
            _material_tiling({"extras": {"kfps_material_appearance": {}}})
        with self.assertRaises(ValueError):
            _material_tiling({"extras": {"kfps_material_appearance": {"uvTiling": [0.0, 1.0]}}})

    def test_source_is_exact_primary_only_and_durango_fail_closed(self):
        text = (ROOT / "fh6garage" / "preview3d" / "manufacturer_paint_texture_patch.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('_PRIMARY_MATERIAL = "carpaint"', text)
        self.assertIn('row.get("status") != "manufacturer_overlay_payload_resolved_exact"', text)
        self.assertIn('row.get("exact_resolution_approved") is not True', text)
        self.assertIn('row.get("uv4_status") != "uv4_exact_kfps_accessor"', text)
        self.assertIn("carpaint_secondary UV4 swatch deferred", text)
        self.assertIn("_SRGB_ALBEDO_DXGI", text)
        self.assertNotIn("opacity multiplier", text.casefold())


if __name__ == "__main__":
    unittest.main()
