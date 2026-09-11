from __future__ import annotations

import unittest

from fh6garage.preview3d.native_texture_semantics import (
    classify_native_texture_parameter,
    known_native_texture_parameter_count,
    normalize_parameter_hash,
)


class NativeTextureSemanticTests(unittest.TestCase):
    def test_exact_forzatechstudio_hashes_map_without_filename_guessing(self):
        cases = {
            "85F59336": ("DiffuseTexture", "base_color"),
            "10350BBC": ("CH1DiffuseTextureTexture", "base_color"),
            "39731A8A": ("NormalMap", "normal"),
            "8C658791": ("NormalTexture", "normal"),
            "7E4A41E1": ("GlossTexture", "gloss"),
            "7FDA2F1B": ("LocalAOTexture", "ambient_occlusion"),
            "57D9D49E": ("AlphaTexture", "alpha"),
            "020B22EB": ("EmissiveMap", "emissive"),
            "ECE98535": ("GlassRoughnessTexture", "roughness"),
        }
        for parameter_hash, (name, semantic) in cases.items():
            with self.subTest(parameter_hash=parameter_hash):
                result = classify_native_texture_parameter(parameter_hash)
                self.assertEqual(result.parameter_hash, parameter_hash)
                self.assertEqual(result.parameter_name, name)
                self.assertEqual(result.semantic, semantic)
                self.assertEqual(result.resolution_mode, "forzatechstudio_namehash_exact")

    def test_special_normal_layers_are_not_collapsed_into_primary_normal(self):
        clearcoat = classify_native_texture_parameter("3C929217")
        flake = classify_native_texture_parameter("B59BE3AB")
        self.assertEqual(clearcoat.semantic, "clearcoat_normal")
        self.assertEqual(flake.semantic, "flake_normal")
        self.assertNotEqual(clearcoat.semantic, "normal")
        self.assertNotEqual(flake.semantic, "normal")

    def test_unknown_hash_fails_closed_without_path_or_name_heuristics(self):
        result = classify_native_texture_parameter("DEADBEEF")
        self.assertEqual(result.parameter_hash, "DEADBEEF")
        self.assertIsNone(result.parameter_name)
        self.assertEqual(result.semantic, "unknown")
        self.assertEqual(result.resolution_mode, "unmapped_parameter_hash")

    def test_hash_parser_accepts_hex_forms_and_rejects_invalid_values(self):
        self.assertEqual(normalize_parameter_hash("0x85F59336"), 0x85F59336)
        self.assertEqual(normalize_parameter_hash(0x39731A8A), 0x39731A8A)
        self.assertIsNone(normalize_parameter_hash("not-a-hash"))
        self.assertIsNone(normalize_parameter_hash(-1))
        self.assertIsNone(normalize_parameter_hash(0x1_0000_0000))

    def test_mapping_has_broad_non_vehicle_specific_coverage(self):
        self.assertGreaterEqual(known_native_texture_parameter_count(), 25)


if __name__ == "__main__":
    unittest.main()
