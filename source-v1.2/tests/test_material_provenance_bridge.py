from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATCHER = ROOT / "tools" / "patch_kfps_wheel_morph_diagnostic.py"
MATERIAL_HELPER = ROOT / "tools" / "kfps_wheel_morph" / "MaterialAppearanceDiagnostic.cs"


class MaterialProvenanceBridgeTests(unittest.TestCase):
    def test_kfps_patch_exports_embedded_material_appearance(self):
        patcher = PATCHER.read_text(encoding="utf-8")
        self.assertIn("MaterialAppearanceDiagnostic MaterialAppearance", patcher)
        self.assertIn("MaterialAppearanceRuntime.Resolve", patcher)
        # This C# writer fragment lives inside a Python replacement string, so
        # its quotes are escaped in the patcher's source representation.
        self.assertIn('\\"kfps_material_appearance\\"', patcher)
        self.assertIn("MaterialAppearanceDiagnostic.cs", patcher)
        self.assertIn("glb_writer.write_text", patcher)

    def test_resolver_uses_embedded_material_blob_and_shader_parameters(self):
        text = MATERIAL_HELPER.read_text(encoding="utf-8")
        self.assertIn("OfType<MaterialBlob>()", text)
        self.assertIn("OfType<NameMetadata>()", text)
        self.assertIn("OfType<MaterialShaderParameterBlob>()", text)
        self.assertIn("Bundle.TAG_BLOB_MaterialShaderParameter", text)
        self.assertIn("Bundle.TAG_BLOB_DefaultShaderParameter", text)
        self.assertIn("ShaderParameterType.Texture2D", text)
        self.assertIn("TextureParameter", text)

    def test_shader_semantics_are_global_not_vehicle_specific(self):
        text = MATERIAL_HELPER.read_text(encoding="utf-8")
        self.assertIn("0xA05F6E3F", text)  # Roughness
        self.assertIn("0x649F46D0", text)  # F_Roughness
        self.assertIn("0x1B51AB81", text)  # F_Metalness
        self.assertIn("0x7E88DE7D", text)  # ClearCoatGloss
        self.assertIn("0x23C8B47A", text)  # ClearCoatF0
        self.assertNotIn("Car ID", text)
        self.assertNotIn("FER_FXX", text)
        self.assertNotIn("TOY_2000GT", text)
        self.assertNotIn("HYU_", text)

    def test_resolution_is_fail_closed_for_missing_or_ambiguous_materials(self):
        text = MATERIAL_HELPER.read_text(encoding="utf-8")
        self.assertIn('"embedded_material_not_found"', text)
        self.assertIn('"embedded_material_name_ambiguous"', text)
        self.assertIn('"embedded_material_bundle_unparsed"', text)
        self.assertIn('"embedded_material_has_no_shader_parameters"', text)
        self.assertNotIn("FirstOrDefault() ??", text)


if __name__ == "__main__":
    unittest.main()
