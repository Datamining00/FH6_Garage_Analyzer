from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "tools" / "kfps_wheel_morph" / "MaterialbinReferenceDiagnostic.cs"
PATCHER = ROOT / "tools" / "patch_kfps_materialbin_diagnostic.py"


class MaterialbinReferenceHelperSourceTests(unittest.TestCase):
    def test_helper_preserves_pinned_fts_reference_order_without_path_heuristics(self):
        text = HELPER.read_text(encoding="utf-8")
        matl = text.index("foreach (var matl in bundle.Blobs.OfType<MatLBlob>())")
        path = text.index('AddMatlReference(references, ref order, "Path", matl.Path);', matl)
        path_v11 = text.index('AddMatlReference(references, ref order, "PathV1_1", matl.PathV1_1);', path)
        path_v12 = text.index('AddMatlReference(references, ref order, "PathV1_2", matl.PathV1_2);', path_v11)
        shader = text.index("foreach (var blob in bundle.Blobs)", path_v12)
        texture = text.index("parameter.Type != ShaderParameterType.Texture2D", shader)
        self.assertLess(matl, path)
        self.assertLess(path, path_v11)
        self.assertLess(path_v11, path_v12)
        self.assertLess(path_v12, shader)
        self.assertLess(shader, texture)
        self.assertIn('$"{parameter.NameHash:X8}"', text)
        self.assertIn('$"{texture.PathHash:X8}"', text)
        self.assertIn("bundle.Load(stream)", text)
        self.assertNotIn("Contains(\"paint\"", text)
        self.assertNotIn("GetFileName", text)
        self.assertNotIn("EndsWith(\"carpaint\"", text)

    def test_followup_patcher_is_modular_and_requires_established_decode_contract(self):
        text = PATCHER.read_text(encoding="utf-8")
        self.assertIn("6f53ca3c584d78659d06d4b4a39561db67d79345", text)
        self.assertIn("--decode-swatchbin", text)
        self.assertIn("--diagnose-materialbin", text)
        self.assertIn("MaterialbinReferenceRuntime.Diagnose", text)
        self.assertIn("Expected exactly one established --decode-swatchbin CLI contract", text)
        self.assertIn("shutil.copy2", text)


if __name__ == "__main__":
    unittest.main()
