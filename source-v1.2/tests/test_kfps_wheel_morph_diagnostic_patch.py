from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATCHER = ROOT / "tools" / "patch_kfps_wheel_morph_diagnostic.py"
HELPER = ROOT / "tools" / "kfps_wheel_morph" / "WheelMorphDiagnostic.cs"
AUDIT = ROOT / "tools" / "kfps_wheel_morph" / "TransformAudit.cs"


class KfpsWheelMorphDiagnosticPatchTests(unittest.TestCase):
    def test_patcher_is_pinned_and_inserts_before_transforms(self):
        text = PATCHER.read_text(encoding="utf-8")
        self.assertIn("6f53ca3c584d78659d06d4b4a39561db67d79345", text)
        morph = text.index("local += WheelMorphRuntime.DecodePositionDelta(morph, index);")
        transform = text.index("Vector3.Transform(local, geometry.BoneTransform)", morph)
        self.assertLess(morph, transform)
        self.assertIn("model.Bundle", text)
        self.assertIn("WheelMorphRuntime.Configure(instances)", text)

    def test_attachment_resolution_prefers_local_named_bones_and_fail_closes_cross_namespace_ids(self):
        patcher = PATCHER.read_text(encoding="utf-8")
        audit = AUDIT.read_text(encoding="utf-8")
        self.assertIn("TransformAuditRuntime.ResolveAttachmentBone(model.Bundle, instance)", patcher)
        self.assertIn("attachmentResolution.World is Matrix4x4 boneWorld", patcher)
        self.assertIn(
            "TransformAuditRuntime.RecordInstance(entryName, instance, instanceTransform, attachmentResolution)",
            patcher,
        )
        self.assertIn("carbin.Scene.SkeletonPath", patcher)
        self.assertIn("TransformAuditRuntime.RegisterAuthoritativeSceneSkeleton", patcher)
        self.assertIn("TransformAuditRuntime.RegisterSceneSkeleton(rootEntry, rootModel.Bundle)", patcher)
        self.assertIn("instance.PartType == CCarParts.CarBody", patcher)
        self.assertIn("model.SnapToParent", patcher)
        self.assertIn("model.AssemblyName", patcher)
        # The C# replacement source lives inside Python string literals, so the
        # double quotes are escaped in the patcher source representation.
        self.assertIn('model.SnapToParent ? \\"snap:1\\" : \\"snap:0\\"', patcher)
        self.assertIn('\\"assembly:\\" + (model.AssemblyName ?? \\"\\").ToLowerInvariant()', patcher)

        self.assertIn('"child_name"', audit)
        self.assertIn('"scene_path_name_bone_only"', audit)
        self.assertIn('"bone_only_scene_name_not_found"', audit)
        self.assertIn('"named_child_miss_keep_carbin"', audit)
        self.assertIn('"id_only"', audit)
        self.assertIn("IsBoneOnlyPlacement(instance)", audit)
        self.assertIn("RequestedSceneSkeletonPath", audit)
        self.assertIn("AuthoritativeSceneSkeletonSource", audit)
        self.assertIn("SceneSkeletonResolutionMode", audit)
        self.assertIn("AttachmentResolutionMode", audit)
        self.assertIn("ResolvedAttachmentBoneIndex", audit)
        self.assertIn("SnapToParent", audit)
        self.assertIn("AssemblyName", audit)

        resolver_start = audit.index("public static AttachmentBoneResolution ResolveAttachmentBone")
        resolver_end = audit.index("private static Matrix4x4 ResolveBoneWorld", resolver_start)
        resolver = audit[resolver_start:resolver_end]
        named = resolver.index("if (!string.IsNullOrWhiteSpace(requestedName))")
        child = resolver.index("var childTarget", named)
        bone_only = resolver.index("if (IsBoneOnlyPlacement(instance))", child)
        scene = resolver.index('"scene_path_name_bone_only"', bone_only)
        no_name = resolver.index("// With no bone name", scene)

        # Named attachments resolve in their own model bundle first. If the name
        # is absent, the numeric BoneId must not be reinterpreted in that unrelated
        # local skeleton. A scene-skeleton name is allowed only for a zero-translation
        # bone-only placement; otherwise the Carbin matrix is preserved unchanged.
        self.assertLess(child, bone_only)
        self.assertLess(bone_only, scene)
        self.assertNotIn("if (instance.SnapToParent)", resolver)
        self.assertNotIn("instanceSkeleton.Bones[requestedId]", resolver[named:no_name])
        self.assertIn("instanceSkeleton.Bones[requestedId]", resolver[no_name:])

    def test_transform_audit_exposes_instance_local_wheel_geometry(self):
        audit = AUDIT.read_text(encoding="utf-8")
        self.assertIn("VertexCount", audit)
        self.assertIn("LocalAabbMin", audit)
        self.assertIn("LocalAabbMax", audit)
        self.assertIn("Matrix4x4.Invert(effectiveTransform", audit)
        self.assertIn("new Vector3(-point.X, point.Y, point.Z)", audit)

    def test_runtime_uses_signed_base_vertex_and_selector_indices(self):
        text = HELPER.read_text(encoding="utf-8")
        self.assertIn("geometry.MinVertexIndex + mesh.IndexedVertexOffset", text)
        self.assertIn("mesh.MorphTargetCount > 2", text)
        self.assertIn("mesh.IsMorphDamage", text)
        self.assertIn("selectorRaw", text)
        self.assertIn("context.Weights[selector]", text)
        self.assertIn("VerifiedFloat4Format = 10", text)
        self.assertNotIn("MathF.Abs(mesh.IndexedVertexOffset)", text)

    def test_runtime_prefers_front_wheel_semantics_and_keeps_coordinate_fallback(self):
        text = HELPER.read_text(encoding="utf-8")
        self.assertIn("WheelStylePartType = 44", text)
        self.assertIn("_namedFrontInstances", text)
        self.assertIn("IsNamedFrontWheel(instance.BoneName)", text)
        self.assertIn("_namedFrontInstances.Contains(instance.Identity)", text)
        self.assertIn("instance.Transform.M43", text)
        self.assertIn("_axleSplitZ", text)
        self.assertIn(": z > _axleSplitZ", text)
        # The helper must remain structural/semantic, not vehicle- or asset-specific.
        self.assertNotIn("wheelLF", text)
        self.assertNotIn("wheelLR", text)
        self.assertNotIn("spindleLF", text)
        self.assertNotIn("spindleLR", text)
        self.assertNotIn("FER_FXX", text)
        self.assertNotIn("TOY_2000GT", text)

    def test_runtime_has_no_arbitrary_wheel_scale_or_tire_morph(self):
        text = HELPER.read_text(encoding="utf-8")
        self.assertNotIn("scale_x", text.casefold())
        self.assertNotIn("tirecompound", text.casefold())
        self.assertNotIn("0.1f *", text)


if __name__ == "__main__":
    unittest.main()
