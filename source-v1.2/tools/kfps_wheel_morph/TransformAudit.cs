using System.Numerics;
using ForzaTechStudio.Services;
using ForzaTools.Bundles;
using ForzaTools.Bundles.Blobs;

namespace Kfps.ChassisConverter;

internal sealed record AttachmentBoneResolution(
    string Mode,
    string RequestedName,
    short RequestedId,
    string ResolvedName,
    int ResolvedIndex,
    string SkeletonSource,
    Matrix4x4? World);

internal sealed record WheelStyleAnchorDiagnostic(
    string InstanceIdentity,
    string SourceEntry,
    string ResourcePath,
    string BoneName,
    short BoneId,
    bool StockPart,
    string AttachmentResolutionMode,
    string ResolvedAttachmentBoneName,
    int ResolvedAttachmentBoneIndex,
    string AttachmentSkeletonSource,
    float[] CarbinTransformRowMajor,
    float[] EffectiveTransformRowMajor,
    float CarbinX,
    float CarbinY,
    float CarbinZ,
    float EffectiveX,
    float EffectiveY,
    float EffectiveZ);

internal sealed record MeshTransformAuditDiagnostic(
    string InstanceIdentity,
    string SourceEntry,
    string ResourcePath,
    string PartType,
    string AttachmentBoneName,
    short AttachmentBoneId,
    bool StockPart,
    string AttachmentResolutionMode,
    string ResolvedAttachmentBoneName,
    int ResolvedAttachmentBoneIndex,
    string AttachmentSkeletonSource,
    string MeshName,
    short RigidBoneIndex,
    string RigidBoneName,
    float[] CarbinTransformRowMajor,
    float[] EffectiveInstanceTransformRowMajor,
    float[] RigidBoneTransformRowMajor,
    float[] RenderAabbMin,
    float[] RenderAabbMax);

internal static class TransformAuditRuntime
{
    private const uint WheelStylePartType = 44;
    private static readonly List<WheelStyleAnchorDiagnostic> _wheelAnchors = [];
    private static readonly List<MeshTransformAuditDiagnostic> _meshAudit = [];
    private static readonly HashSet<string> _wheelIdentities = new(StringComparer.Ordinal);
    private static readonly Dictionary<string, AttachmentBoneResolution> _attachmentResolutions =
        new(StringComparer.Ordinal);

    public static IReadOnlyList<WheelStyleAnchorDiagnostic> WheelStyleAnchors => _wheelAnchors;
    public static IReadOnlyList<MeshTransformAuditDiagnostic> MeshTransformAudit => _meshAudit;

    public static void Configure(IReadOnlyList<ModelInstance> instances)
    {
        _wheelAnchors.Clear();
        _meshAudit.Clear();
        _wheelIdentities.Clear();
        _attachmentResolutions.Clear();
    }

    public static AttachmentBoneResolution ResolveAttachmentBone(Bundle bundle, ModelInstance instance)
    {
        const string skeletonSource = "instance_model_bundle";
        var requestedName = instance.BoneName ?? "";
        var requestedId = instance.BoneId;
        var skeleton = bundle.Blobs.OfType<SkeletonBlob>().FirstOrDefault();
        if (skeleton is null || skeleton.Bones.Count == 0)
        {
            return new AttachmentBoneResolution(
                "no_skeleton", requestedName, requestedId, "", -1, skeletonSource, null);
        }

        var target = -1;
        var mode = "none";
        if (!string.IsNullOrWhiteSpace(requestedName))
        {
            target = skeleton.Bones.FindIndex(
                bone => string.Equals(bone.Name, requestedName, StringComparison.OrdinalIgnoreCase));
            if (target < 0)
            {
                // A BoneId belongs to a specific skeleton namespace.  Never silently
                // reinterpret a named Carbin attachment as the same numeric index in
                // a different/child model skeleton when its name did not resolve.
                return new AttachmentBoneResolution(
                    "name_not_found", requestedName, requestedId, "", -1, skeletonSource, null);
            }
            mode = "name";
        }
        else if (requestedId >= 0 && requestedId < skeleton.Bones.Count)
        {
            target = requestedId;
            mode = "id_only";
        }
        else
        {
            return new AttachmentBoneResolution(
                "none", requestedName, requestedId, "", -1, skeletonSource, null);
        }

        var cache = new Matrix4x4?[skeleton.Bones.Count];
        var visiting = new bool[skeleton.Bones.Count];
        Matrix4x4 Resolve(int index)
        {
            if (cache[index] is Matrix4x4 ready) return ready;
            if (visiting[index])
                throw new InvalidDataException("A model skeleton contains a parent cycle.");
            visiting[index] = true;
            var bone = skeleton.Bones[index];
            var world = bone.Matrix;
            if (bone.ParentId >= 0 && bone.ParentId < skeleton.Bones.Count)
                world *= Resolve(bone.ParentId);
            visiting[index] = false;
            cache[index] = world;
            return world;
        }

        return new AttachmentBoneResolution(
            mode,
            requestedName,
            requestedId,
            skeleton.Bones[target].Name ?? "",
            target,
            skeletonSource,
            Resolve(target));
    }

    public static void RecordInstance(
        string sourceEntry,
        ModelInstance instance,
        Matrix4x4 effectiveTransform,
        AttachmentBoneResolution attachment)
    {
        _attachmentResolutions[instance.Identity] = attachment;
        if ((uint)instance.PartType != WheelStylePartType)
            return;
        if (!_wheelIdentities.Add(instance.Identity))
            return;
        ValidateFinite(instance.Transform, $"WheelStyle {instance.Identity} carbin transform");
        ValidateFinite(effectiveTransform, $"WheelStyle {instance.Identity} effective transform");
        _wheelAnchors.Add(new WheelStyleAnchorDiagnostic(
            instance.Identity,
            sourceEntry,
            instance.Path,
            instance.BoneName,
            instance.BoneId,
            instance.StockPart,
            attachment.Mode,
            attachment.ResolvedName,
            attachment.ResolvedIndex,
            attachment.SkeletonSource,
            MatrixValues(instance.Transform),
            MatrixValues(effectiveTransform),
            instance.Transform.M41,
            instance.Transform.M42,
            instance.Transform.M43,
            effectiveTransform.M41,
            effectiveTransform.M42,
            effectiveTransform.M43));
    }

    public static void RecordGeometry(
        string sourceEntry,
        ForzaGeometryData geometry,
        ModelInstance instance,
        Matrix4x4 effectiveTransform,
        IReadOnlyList<Vector3> renderPositions)
    {
        if (renderPositions.Count == 0)
            return;
        ValidateFinite(instance.Transform, $"{instance.Identity} carbin transform");
        ValidateFinite(effectiveTransform, $"{instance.Identity} effective transform");
        ValidateFinite(geometry.BoneTransform, $"{instance.Identity}/{geometry.Name} rigid-bone transform");

        var minimum = new Vector3(float.PositiveInfinity, float.PositiveInfinity, float.PositiveInfinity);
        var maximum = new Vector3(float.NegativeInfinity, float.NegativeInfinity, float.NegativeInfinity);
        foreach (var point in renderPositions)
        {
            if (!float.IsFinite(point.X) || !float.IsFinite(point.Y) || !float.IsFinite(point.Z))
                throw new InvalidDataException($"{instance.Identity}/{geometry.Name} render AABB contains a non-finite point.");
            minimum = Vector3.Min(minimum, point);
            maximum = Vector3.Max(maximum, point);
        }

        if (!_attachmentResolutions.TryGetValue(instance.Identity, out var attachment))
        {
            attachment = new AttachmentBoneResolution(
                "not_recorded", instance.BoneName, instance.BoneId, "", -1,
                "instance_model_bundle", null);
        }
        _meshAudit.Add(new MeshTransformAuditDiagnostic(
            instance.Identity,
            sourceEntry,
            instance.Path,
            instance.PartType.ToString(),
            instance.BoneName,
            instance.BoneId,
            instance.StockPart,
            attachment.Mode,
            attachment.ResolvedName,
            attachment.ResolvedIndex,
            attachment.SkeletonSource,
            geometry.Name,
            geometry.BoneIndex,
            geometry.BoneName,
            MatrixValues(instance.Transform),
            MatrixValues(effectiveTransform),
            MatrixValues(geometry.BoneTransform),
            [minimum.X, minimum.Y, minimum.Z],
            [maximum.X, maximum.Y, maximum.Z]));
    }

    private static float[] MatrixValues(Matrix4x4 value) =>
    [
        value.M11, value.M12, value.M13, value.M14,
        value.M21, value.M22, value.M23, value.M24,
        value.M31, value.M32, value.M33, value.M34,
        value.M41, value.M42, value.M43, value.M44,
    ];

    private static void ValidateFinite(Matrix4x4 value, string label)
    {
        foreach (var component in MatrixValues(value))
        {
            if (!float.IsFinite(component))
                throw new InvalidDataException($"{label} contains a non-finite component.");
        }
    }
}
