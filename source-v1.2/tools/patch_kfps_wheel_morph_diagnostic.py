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
    glb_writer = converter / "GlbWriter.cs"
    material_helper = audit_helper.with_name("MaterialAppearanceDiagnostic.cs")
    if not program.is_file():
        raise RuntimeError(f"Pinned KFPS Program.cs was not found: {program}")
    if not glb_writer.is_file():
        raise RuntimeError(f"Pinned KFPS GlbWriter.cs was not found: {glb_writer}")
    if not helper.is_file():
        raise RuntimeError(f"WheelMorphDiagnostic.cs was not found: {helper}")
    if not audit_helper.is_file():
        raise RuntimeError(f"TransformAudit.cs was not found: {audit_helper}")
    if not material_helper.is_file():
        raise RuntimeError(f"MaterialAppearanceDiagnostic.cs was not found: {material_helper}")

    text = program.read_text(encoding="utf-8-sig")

    text = _replace_exact(
        text,
        """    int ProjectionSides,\n    ulong MaterialBindingHash,\n    Vector3[] Positions,""",
        """    int ProjectionSides,\n    ulong MaterialBindingHash,\n    MaterialAppearanceDiagnostic MaterialAppearance,\n    Vector3[] Positions,""",
        "preserve material appearance provenance in ChassisMesh",
    )

    text = _replace_exact(
        text,
        """internal sealed record ModelInstance(\n    string Path,\n    Matrix4x4 Transform,\n    string BoneName,\n    short BoneId,\n    CCarParts PartType,""",
        """internal sealed record ModelInstance(\n    string Path,\n    Matrix4x4 Transform,\n    string BoneName,\n    short BoneId,\n    bool SnapToParent,\n    string AssemblyName,\n    CCarParts PartType,""",
        "preserve CarRenderModel parent-attachment semantics",
    )

    text = _replace_exact(
        text,
        """                scene_assembled = sceneAssembled,\n                requested_instance_count = extraction.RequestedInstances,""",
        """                scene_assembled = sceneAssembled,\n                wheel_morph_mode = WheelMorphRuntime.Mode,\n                wheel_morph_applied_meshes = WheelMorphRuntime.AppliedMeshes,\n                wheel_morph_applied_vertices = WheelMorphRuntime.AppliedVertices,\n                wheel_morph_axle_split_z = WheelMorphRuntime.AxleSplitZ,\n                wheel_style_anchor_count = TransformAuditRuntime.WheelStyleAnchors.Count,\n                wheel_style_anchors = TransformAuditRuntime.WheelStyleAnchors,\n                transform_audit_count = TransformAuditRuntime.MeshTransformAudit.Count,\n                transform_audit = TransformAuditRuntime.MeshTransformAudit,\n                scene_attachment_skeleton_count = TransformAuditRuntime.SceneSkeletonCount,\n                scene_skeleton_path = TransformAuditRuntime.RequestedSceneSkeletonPath,\n                scene_skeleton_resolution_mode = TransformAuditRuntime.SceneSkeletonResolutionMode,\n                authoritative_scene_skeleton_source = TransformAuditRuntime.AuthoritativeSceneSkeletonSource,\n                requested_instance_count = extraction.RequestedInstances,""",
        "conversion JSON morph/transform diagnostics",
    )

    text = _replace_exact(
        text,
        """        var instances = SceneModelInstances(carbin.Scene, out var partOptions);\n        if (instances.Count == 0)""",
        """        var instances = SceneModelInstances(carbin.Scene, out var partOptions);\n        WheelMorphRuntime.Configure(instances);\n        TransformAuditRuntime.Configure(instances, carbin.Scene.SkeletonPath);\n        if (instances.Count == 0)""",
        "configure WheelStyle morph and transform audit",
    )

    text = _replace_exact(
        text,
        """        var cache = new Dictionary<string, ImportedModel>(StringComparer.OrdinalIgnoreCase);\n        var result = new List<ChassisMesh>();""",
        """        var cache = new Dictionary<string, ImportedModel>(StringComparer.OrdinalIgnoreCase);\n\n        // Scene.SkeletonPath is the Carbin-declared parent/chassis skeleton.  It\n        // is authoritative for SnapToParent attachments when it resolves.  This\n        // is structural scene metadata, not a vehicle/model-specific exception.\n        if (!string.IsNullOrWhiteSpace(carbin.Scene.SkeletonPath))\n        {\n            var sceneSkeletonEntry = ResolveModelEntry(carbin.Scene.SkeletonPath, mediaName, available);\n            if (sceneSkeletonEntry is null)\n            {\n                TransformAuditRuntime.RecordSceneSkeletonResolutionFailure(\"scene_skeleton_path_unresolved\");\n            }\n            else\n            {\n                try\n                {\n                    if (!cache.TryGetValue(sceneSkeletonEntry, out var sceneSkeletonModel))\n                    {\n                        sceneSkeletonModel = LoadModel(available[sceneSkeletonEntry], sceneSkeletonEntry);\n                        cache[sceneSkeletonEntry] = sceneSkeletonModel;\n                    }\n                    if (!TransformAuditRuntime.RegisterAuthoritativeSceneSkeleton(\n                            sceneSkeletonEntry, sceneSkeletonModel.Bundle))\n                    {\n                        TransformAuditRuntime.RecordSceneSkeletonResolutionFailure(\n                            \"scene_skeleton_path_has_no_skeleton\");\n                    }\n                }\n                catch (Exception error)\n                {\n                    TransformAuditRuntime.RecordSceneSkeletonResolutionFailure(\n                        $\"scene_skeleton_path_load_failed:{error.GetType().Name}\");\n                }\n            }\n        }\n\n        // Keep resolvable stock CarBody skeletons only as exact-name fallback\n        // namespaces when the authoritative Scene.SkeletonPath cannot satisfy a\n        // named attachment.  Ambiguous fallback names remain fail-closed.\n        foreach (var rootInstance in instances.Where(instance => instance.StockPart && instance.PartType == CCarParts.CarBody))\n        {\n            var rootEntry = ResolveModelEntry(rootInstance.Path, mediaName, available);\n            if (rootEntry is null || rootEntry.Contains(\"__slod\", StringComparison.OrdinalIgnoreCase))\n                continue;\n            if (!cache.TryGetValue(rootEntry, out var rootModel))\n            {\n                rootModel = LoadModel(available[rootEntry], rootEntry);\n                cache[rootEntry] = rootModel;\n            }\n            TransformAuditRuntime.RegisterSceneSkeleton(rootEntry, rootModel.Bundle);\n        }\n\n        var result = new List<ChassisMesh>();""",
        "register authoritative scene skeleton and stock CarBody fallbacks before part transforms",
    )

    text = _replace_exact(
        text,
        """            var instanceTransform = instance.Transform;\n            if (FindBoneWorld(model.Bundle, instance.BoneName, instance.BoneId) is Matrix4x4 boneWorld)\n                instanceTransform = instance.Transform * boneWorld;\n            var before = result.Count;""",
        """            var instanceTransform = instance.Transform;\n            var attachmentResolution = TransformAuditRuntime.ResolveAttachmentBone(model.Bundle, instance);\n            if (attachmentResolution.World is Matrix4x4 boneWorld)\n                instanceTransform = instance.Transform * boneWorld;\n            TransformAuditRuntime.RecordInstance(entryName, instance, instanceTransform, attachmentResolution);\n            var before = result.Count;""",
        "resolve attachment bone without cross-skeleton numeric fallback and record provenance",
    )

    text = _replace_exact(
        text,
        """            AppendMeshes(result, model.Imported, entryName, instance, instanceTransform, ref estimatedBinaryBytes);""",
        """            AppendMeshes(result, model.Bundle, model.Imported, entryName, instance, instanceTransform, ref estimatedBinaryBytes);""",
        "pass model bundle into scene AppendMeshes",
    )

    text = _replace_exact(
        text,
        """            var instance = new ModelInstance(\n                requestedName,\n                Matrix4x4.Identity,\n                \"\",\n                -1,\n                CCarParts.CarBody,""",
        """            var instance = new ModelInstance(\n                requestedName,\n                Matrix4x4.Identity,\n                \"\",\n                -1,\n                false,\n                \"\",\n                CCarParts.CarBody,""",
        "loose ModelInstance parent-attachment defaults",
    )

    text = _replace_exact(
        text,
        """            AppendMeshes(\n                result,\n                model.Imported,""",
        """            AppendMeshes(\n                result,\n                model.Bundle,\n                model.Imported,""",
        "pass model bundle into loose AppendMeshes",
    )

    text = _replace_exact(
        text,
        """            output.Add(new ModelInstance(\n                model.Path,\n                model.Transform,\n                model.BoneName ?? \"\",\n                model.BoneId,\n                partType,""",
        """            output.Add(new ModelInstance(\n                model.Path,\n                model.Transform,\n                model.BoneName ?? \"\",\n                model.BoneId,\n                model.SnapToParent,\n                model.AssemblyName ?? \"\",\n                partType,""",
        "preserve scene ModelInstance SnapToParent and AssemblyName",
    )

    text = _replace_exact(
        text,
        """            (model.BoneName ?? \"\").ToLowerInvariant(),\n            model.BoneId.ToString(),\n            ((uint)partType).ToString(),""",
        """            (model.BoneName ?? \"\").ToLowerInvariant(),\n            model.BoneId.ToString(),\n            model.SnapToParent ? \"snap:1\" : \"snap:0\",\n            \"assembly:\" + (model.AssemblyName ?? \"\").ToLowerInvariant(),\n            ((uint)partType).ToString(),""",
        "include parent/assembly semantics in ModelInstance identity",
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
        """            var positions = TransformPositions(bundle, geometry, instance, instanceTransform);\n            TransformAuditRuntime.RecordGeometry(sourceEntry, geometry, instance, instanceTransform, positions);""",
        "weighted TransformPositions and transform-audit call",
    )

    text = _replace_exact(
        text,
        """            var role = ClassifyRole(\n                identity,\n                hasUv3,\n                instance.WindowHint,\n                geometry.Name,\n                geometry.MaterialName ?? \"\",\n                materialBindingHash);\n            var actualBytes = checked(""",
        """            var role = ClassifyRole(\n                identity,\n                hasUv3,\n                instance.WindowHint,\n                geometry.Name,\n                geometry.MaterialName ?? \"\",\n                materialBindingHash);\n            var materialAppearance = MaterialAppearanceRuntime.Resolve(\n                bundle, geometry.MaterialName ?? \"\");\n            var actualBytes = checked(""",
        "resolve embedded MaterialBlob shader parameters per mesh",
    )

    text = _replace_exact(
        text,
        """                ProjectionLiverySides(role, geometry.Name, instance.PartType),\n                materialBindingHash,\n                positions,""",
        """                ProjectionLiverySides(role, geometry.Name, instance.PartType),\n                materialBindingHash,\n                materialAppearance,\n                positions,""",
        "attach material appearance provenance to ChassisMesh",
    )

    text = _replace_exact(
        text,
        """    private static Vector3[] TransformPositions(ForzaGeometryData geometry, Matrix4x4 instanceTransform)\n    {\n        var mesh = geometry.SourceMesh;\n        var output = new Vector3[geometry.RawPositions.Length];\n        for (var index = 0; index < output.Length; index++)\n        {\n            var raw = geometry.RawPositions[index];\n            var local = new Vector3(\n                raw.X * mesh.PositionScale.X + mesh.PositionTranslate.X,\n                raw.Y * mesh.PositionScale.Y + mesh.PositionTranslate.Y,\n                raw.Z * mesh.PositionScale.Z + mesh.PositionTranslate.Z);\n            var transformed = geometry.BoneTransform == Matrix4x4.Identity\n                ? local\n                : Vector3.Transform(local, geometry.BoneTransform);\n            if (instanceTransform != Matrix4x4.Identity)\n                transformed = Vector3.Transform(transformed, instanceTransform);\n            output[index] = new Vector3(-transformed.X, transformed.Y, transformed.Z);\n        }\n        return output;\n    }""",
        """    private static Vector3[] TransformPositions(\n        Bundle bundle,\n        ForzaGeometryData geometry,\n        ModelInstance instance,\n        Matrix4x4 instanceTransform)\n    {\n        var mesh = geometry.SourceMesh;\n        var output = new Vector3[geometry.RawPositions.Length];\n        var morph = WheelMorphRuntime.CreateContext(bundle, geometry, instance);\n        for (var index = 0; index < output.Length; index++)\n        {\n            var raw = geometry.RawPositions[index];\n            var local = new Vector3(\n                raw.X * mesh.PositionScale.X + mesh.PositionTranslate.X,\n                raw.Y * mesh.PositionScale.Y + mesh.PositionTranslate.Y,\n                raw.Z * mesh.PositionScale.Z + mesh.PositionTranslate.Z);\n            if (morph is not null)\n                local += WheelMorphRuntime.DecodePositionDelta(morph, index);\n            var transformed = geometry.BoneTransform == Matrix4x4.Identity\n                ? local\n                : Vector3.Transform(local, geometry.BoneTransform);\n            if (instanceTransform != Matrix4x4.Identity)\n                transformed = Vector3.Transform(transformed, instanceTransform);\n            output[index] = new Vector3(-transformed.X, transformed.Y, transformed.Z);\n        }\n        if (morph is not null) WheelMorphRuntime.RecordVertices(output.Length);\n        return output;\n    }""",
        "apply weighted morph before KFPS transforms",
    )

    writer_text = glb_writer.read_text(encoding="utf-8-sig")
    writer_text = _replace_exact(
        writer_text,
        """                    [\"kfps_material_binding_hash\"] = mesh.MaterialBindingHash.ToString(\"X16\"),\n                };""",
        """                    [\"kfps_material_binding_hash\"] = mesh.MaterialBindingHash.ToString(\"X16\"),\n                    [\"kfps_material_appearance\"] = mesh.MaterialAppearance,\n                };""",
        "write material appearance provenance into GLB extras",
    )

    program.write_text(text, encoding="utf-8")
    glb_writer.write_text(writer_text, encoding="utf-8")
    shutil.copy2(helper, converter / "WheelMorphDiagnostic.cs")
    shutil.copy2(audit_helper, converter / "TransformAudit.cs")
    shutil.copy2(material_helper, converter / "MaterialAppearanceDiagnostic.cs")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Patch the pinned KFPS chassis converter with weighted wheel morph, "
            "exact transform-chain diagnostics, and embedded material provenance."
        )
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
    print(f"Patched pinned KFPS wheel morph/transform/material diagnostics: {args.kfps_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())