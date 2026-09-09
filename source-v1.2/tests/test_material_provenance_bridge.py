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

    def test_texture_provenance_preserves_parameter_and_path_hashes(self):
        text = MATERIAL_HELPER.read_text(encoding="utf-8")
        self.assertIn("MaterialTextureBindingDiagnostic", text)
        self.assertIn("ParameterHash", text)
        self.assertIn("PathHash", text)
        self.assertIn("texture.PathHash", text)
        self.assertIn("TextureBindings", text)
        self.assertIn("no diffuse/normal/roughness role is guessed", text)

    def test_material_uv_tiling_uses_exact_published_hashes_without_service_dependency(self):
        text = MATERIAL_HELPER.read_text(encoding="utf-8")
        self.assertNotIn("NameHashService.Instance", text)
        self.assertIn("0x19A7D8F1", text)  # U_Tiling
        self.assertIn("0xB01AEE8E", text)  # alternate U_Tiling hash
        self.assertIn("0x4A3D8375", text)  # V_Tiling
        self.assertIn("0x3E95E96D", text)  # alternate V_Tiling hash
        self.assertIn("0xB99646E7", text)  # BaseColorAlphaTilingOverride
        self.assertIn("0x1144D400", text)  # BaseColorTilingOverride
        self.assertIn("0x5EFF55B5", text)  # CH1DiffuseUVTiling
        self.assertIn("0x6DB70810", text)  # CH2DiffuseTextureUVTiling
        self.assertIn("UvTilingVectorHashes.Contains(hash)", text)
        self.assertIn("SanitizeTilingValue", text)
        self.assertIn("float.IsFinite(value) && MathF.Abs(value) > 1e-6f", text)
        self.assertIn("[uvTiling.X, uvTiling.Y]", text)

    def test_material_uv_tiling_matches_forzatechstudio_overwrite_scope(self):
        text = MATERIAL_HELPER.read_text(encoding="utf-8")
        # ForzaTechStudio resolves a material-wide viewport tiling by walking all
        # shader parameters in order. It does not narrow the vector candidates to
        # diffuse/base-color only, so later published UVTiling/TilingOverride
        # parameters are allowed to replace earlier values.
        self.assertIn("foreach (var blob in parameterBlobs)", text)
        self.assertIn("foreach (var parameter in blob.Parameters)", text)
        self.assertIn("0x8BAB96B3", text)  # RoughMetalAOTilingOverride
        self.assertIn("0xF383EB56", text)  # NormalTilingOverride
        self.assertIn("0x4CCD7F85", text)  # AlphaTilingOverride
        self.assertIn("0xADBA1134", text)  # UVTiling_9
        self.assertIn("uvTiling.X = SanitizeTilingValue(vector.X)", text)
        self.assertIn("uvTiling.Y = SanitizeTilingValue(vector.Y)", text)

    def test_material_uv_tiling_covers_late_forzatechstudio_namehash_entries(self):
        text = MATERIAL_HELPER.read_text(encoding="utf-8")
        # These hashes occur later in FTS NameHashService and previously fell
        # outside the converter's hand-maintained subset. Keep representative
        # diffuse/roughness/effect/generic generations locked to the published
        # identifiers rather than adding path/name heuristics.
        self.assertIn("0xD5E8D0C1", text)  # GlassRoughnessUVTiling
        self.assertIn("0x894A360A", text)  # GlossUVTiling
        self.assertIn("0xEA33F406", text)  # BaseColorRoughnessTiledDirtUVTiling
        self.assertIn("0xCD060FD0", text)  # CH1PatternMaskUVTiling
        self.assertIn("0x694E917B", text)  # ScrollingPixel1_UVTiling
        self.assertIn("0xF6C42060", text)  # MotionVector_Y_UVTiling
        self.assertIn("0x708065F7", text)  # UVTiling_10
        self.assertIn("0x9A7DB1FA", text)  # UVTiling_11
        self.assertIn("0xFD6BB566", text)  # UVTiling_12
        self.assertIn("0x32879008", text)  # UVTiling_13
        self.assertIn("0x52E3B8D7", text)  # UVTiling_14
        self.assertIn("0x0318C562", text)  # UVTiling_15

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