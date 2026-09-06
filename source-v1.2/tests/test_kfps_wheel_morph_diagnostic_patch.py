from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATCHER = ROOT / "tools" / "patch_kfps_wheel_morph_diagnostic.py"
HELPER = ROOT / "tools" / "kfps_wheel_morph" / "WheelMorphDiagnostic.cs"


class KfpsWheelMorphDiagnosticPatchTests(unittest.TestCase):
    def test_patcher_is_pinned_and_inserts_before_transforms(self):
        text = PATCHER.read_text(encoding="utf-8")
        self.assertIn("6f53ca3c584d78659d06d4b4a39561db67d79345", text)
        morph = text.index("local += WheelMorphRuntime.DecodePositionDelta(morph, index);")
        transform = text.index("Vector3.Transform(local, geometry.BoneTransform)", morph)
        self.assertLess(morph, transform)
        self.assertIn("model.Bundle", text)
        self.assertIn("WheelMorphRuntime.Configure(instances)", text)

    def test_runtime_uses_signed_base_vertex_and_selector_indices(self):
        text = HELPER.read_text(encoding="utf-8")
        self.assertIn("geometry.MinVertexIndex + mesh.IndexedVertexOffset", text)
        self.assertIn("mesh.MorphTargetCount > 2", text)
        self.assertIn("mesh.IsMorphDamage", text)
        self.assertIn("selectorRaw", text)
        self.assertIn("context.Weights[selector]", text)
        self.assertIn("VerifiedFloat4Format = 10", text)
        self.assertNotIn("MathF.Abs(mesh.IndexedVertexOffset)", text)

    def test_runtime_classifies_axle_from_wheelstyle_carbin_z_not_asset_name(self):
        text = HELPER.read_text(encoding="utf-8")
        self.assertIn("WheelStylePartType = 44", text)
        self.assertIn("instance.Transform.M43", text)
        self.assertIn("_axleSplitZ", text)
        self.assertNotIn("wheelLF", text)
        self.assertNotIn("wheelLR", text)
        self.assertNotIn("spindleLF", text)
        self.assertNotIn("spindleLR", text)

    def test_runtime_has_no_arbitrary_wheel_scale_or_tire_morph(self):
        text = HELPER.read_text(encoding="utf-8")
        self.assertNotIn("scale_x", text.casefold())
        self.assertNotIn("tirecompound", text.casefold())
        self.assertNotIn("0.1f *", text)


if __name__ == "__main__":
    unittest.main()
