using System.Numerics;
using ForzaTechStudio.Services;

namespace Kfps.ChassisConverter;

internal sealed record WheelStyleAnchorDiagnostic(
    string InstanceIdentity,
    string SourceEntry,
    string ResourcePath,
    string BoneName,
    short BoneId,
    bool StockPart,
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

    public static IReadOnlyList<WheelStyleAnchorDiagnostic> WheelStyleAnchors => _wheelAnchors;
    public static IReadOnlyList<MeshTransformAuditDiagnostic> MeshTransformAudit => _meshAudit;

    public static void Configure(IReadOnlyList<ModelInstance> instances)
    {
        _wheelAnchors.Clear();
        _meshAudit.Clear();
        _wheelIdentities.Clear();
    }

    public static void RecordInstance(
        string sourceEntry,
        ModelInstance instance,
        Matrix4x4 effectiveTransform)
    {
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

        _meshAudit.Add(new MeshTransformAuditDiagnostic(
            instance.Identity,
            sourceEntry,
            instance.Path,
            instance.PartType.ToString(),
            instance.BoneName,
            instance.BoneId,
            instance.StockPart,
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
