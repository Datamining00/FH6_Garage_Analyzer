from __future__ import annotations

import argparse
from pathlib import Path
import shutil


PINNED_KFPS_COMMIT = "6f53ca3c584d78659d06d4b4a39561db67d79345"


def _replace_exact(text: str, old: str, new: str, label: str, *, count: int = 1) -> str:
    found = text.count(old)
    if found != count:
        raise RuntimeError(f"{label}: expected {count} exact occurrence(s), found {found}")
    return text.replace(old, new, count)


def patch(kfps_root: Path, helper: Path, audit_helper: Path) -> None:
    converter = kfps_root / "tools" / "livery" / "chassis-converter"
    program = converter / "Program.cs"
    if not program.is_file():
        raise RuntimeError(f"Pinned KFPS Program.cs was not found: {program}")
    if not helper.is_file():
        raise RuntimeError(f"WheelMorphDiagnostic.cs was not found: {helper}")
    if not audit_helper.is_file():
        raise RuntimeError(f"TransformAudit.cs was not found: {audit_helper}")

    text = program.read_text(encoding="utf-8-sig")

    text = _replace_exact(
        text,
        """                scene_assembled = sceneAssembled,\n                requested_instance_count = extraction.RequestedInstances,""",
        """                scene_assembled = sceneAssembled,\n                wheel_morph_mode = WheelMorphRuntime.Mode,\n                wheel_morph_applied_meshes = WheelMorphRuntime.AppliedMeshes,\n                wheel_morph_applied_vertices = WheelMorphRuntime.AppliedVertices,\n                wheel_morph_axle_split_z = WheelMorphRuntime.AxleSplitZ,\n                wheel_style_anchor_count = TransformAuditRuntime.WheelStyleAnchors.Count,\n                wheel_style_anchors = TransformAuditRuntime.WheelStyleAnchors,\n                transform_audit_count = TransformAuditRuntime.MeshTransformAudit.Count,\n                transform_audit = TransformAuditRuntime.MeshTransformAudit,\n                requested_instance_count = extraction.RequestedInstances,""",
        "conversion JSON morph/transform diagnostics",
    )

    text = _replace_exact(
        text,
        """        var instances = SceneModelInstances(carbin.Scene, out var partOptions);\n        if (instances.Count == 0)""",
        """        var instances = SceneModelInstances(carbin.Scene, out var partOptions);\n        WheelMorphRuntime.Configure(instances);\n        TransformAuditRuntime.Configure(instances);\n        if (instances.Count == 0)""",
        "configure WheelStyle morph and transform audit",
    )

    text = _replace_exact(
        text,
        """            var instanceTransform = instance.Transform;\n            if (FindBoneWorld(model.Bundle, instance.BoneName, instance.BoneId) is Matrix4x4 boneWorld)\n                instanceTransform = instance.Transform * boneWorld;\n            var before = result.Count;""",
        """            var instanceTransform = instance.Transform;\n            if (FindBoneWorld(model.Bundle, instance.BoneName, instance.BoneId) is Matrix4x4 boneWorld)\n                instanceTransform = instance.Transform * boneWorld;\n            TransformAuditRuntime.RecordInstance(entryName, instance, instanceTransform);\n            var before = result.Count;""",
        "record exact KFPS effective instance transform",
    )

    text = _replace_exact(
        text,
        """            AppendMeshes(result, model.Imported, entryName, instance, instanceTransform, ref estimatedBinaryBytes);""",
        """            AppendMeshes(result, model.Bundle, model.Imported, entryName, instance, instanceTransform, ref estimatedBinaryBytes);""",
        "pass model bundle into scene AppendMeshes",
    )

    text = _replace_exact(
        text,
        """            AppendMeshes(\n                result,\n                model.Imported,""",
        """            AppendMeshes(\n                result,\n                model.Bundle,\n                model.Imported,""",
        "pass model bundle into loose AppendMeshes",
    )

    text = _replace_exact(
        text,
        """    private static void AppendMeshes(\n        List<ChassisMesh> result,\n        ImporterResult imported,""",
        """    private static void AppendMeshes(\n        List<ChassisMesh> result,\n        Bundle bundle,\n        ImporterResult imported,""",
        "AppendMeshes bundle parameter",
    )

    text = _replace_exact(
        text,
        """            var positions = TransformPositions(geometry, instanceTransform);""",
        """            var positions = TransformPositions(bundle, geometry, instance, instanceTransform);\n            TransformAuditRuntime.RecordGeometry(entryName: sourceEntry, geometry, instance, instanceTransform, positions);""",
        "weighted TransformPositions and transform-audit call",
    )

    text = _replace_exact(
        text,
        """    private static Vector3[] TransformPositions(ForzaGeometryData geometry, Matrix4x4 instanceTransform)\n    {\n        var mesh = geometry.SourceMesh;\n        var output = new Vector3[geometry.RawPositions.Length];\n        for (var index = 0; index < output.Length; index++)\n        {\n            var raw = geometry.RawPositions[index];\n            var local = new Vector3(\n                raw.X * mesh.PositionScale.X + mesh.PositionTranslate.X,\n                raw.Y * mesh.PositionScale.Y + mesh.PositionTranslate.Y,\n                raw.Z * mesh.PositionScale.Z + mesh.PositionTranslate.Z);\n            var transformed = geometry.BoneTransform == Matrix4x4.Identity\n                ? local\n                : Vector3.Transform(local, geometry.BoneTransform);\n            if (instanceTransform != Matrix4x4.Identity)\n                transformed = Vector3.Transform(transformed, instanceTransform);\n            output[index] = new Vector3(-transformed.X, transformed.Y, transformed.Z);\n        }\n        return output;\n    }""",
        """    private static Vector3[] TransformPositions(\n        Bundle bundle,\n        ForzaGeometryData geometry,\n        ModelInstance instance,\n        Matrix4x4 instanceTransform)\n    {\n        var mesh = geometry.SourceMesh;\n        var output = new Vector3[geometry.RawPositions.Length];\n        var morph = WheelMorphRuntime.CreateContext(bundle, geometry, instance);\n        for (var index = 0; index < output.Length; index++)\n        {\n            var raw = geometry.RawPositions[index];\n            var local = new Vector3(\n                raw.X * mesh.PositionScale.X + mesh.PositionTranslate.X,\n                raw.Y * mesh.PositionScale.Y + mesh.PositionTranslate.Y,\n                raw.Z * mesh.PositionScale.Z + mesh.PositionTranslate.Z);\n            if (morph is not null)\n                local += WheelMorphRuntime.DecodePositionDelta(morph, index);\n            var transformed = geometry.BoneTransform == Matrix4x4.Identity\n                ? local\n                : Vector3.Transform(local, geometry.BoneTransform);\n            if (instanceTransform != Matrix4x4.Identity)\n                transformed = Vector3.Transform(transformed, instanceTransform);\n            output[index] = new Vector3(-transformed.X, transformed.Y, transformed.Z);\n        }\n        if (morph is not null) WheelMorphRuntime.RecordVertices(output.Length);\n        return output;\n    }""",
        "apply weighted morph before KFPS transforms",
    )

    program.write_text(text, encoding="utf-8")
    shutil.copy2(helper, converter / "WheelMorphDiagnostic.cs")
    shutil.copy2(audit_helper, converter / "TransformAudit.cs")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Patch the pinned KFPS chassis converter with weighted wheel morph and exact transform-chain diagnostics."
    )
    parser.add_argument("--kfps-root", type=Path, required=True)
    parser.add_argument(
        "--helper",
        type=Path,
        default=Path(__file__).resolve().parent / "kfps_wheel_morph" / "WheelMorphDiagnostic.cs",
    )
    parser.add_argument(
        "--audit-helper",
        type=Path,
        default=Path(__file__).resolve().parent / "kfps_wheel_morph" / "TransformAudit.cs",
    )
    args = parser.parse_args()
    patch(args.kfps_root.resolve(), args.helper.resolve(), args.audit_helper.resolve())
    print(f"Patched pinned KFPS wheel morph/transform diagnostics: {args.kfps_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
