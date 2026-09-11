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
    bool SnapToParent,
    string AssemblyName,
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
    bool SnapToParent,
    string AssemblyName,
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
    int VertexCount,
    float[] LocalAabbMin,
    float[] LocalAabbMax,
    float[] RenderAabbMin,
    float[] RenderAabbMax);

internal sealed record SceneSkeletonCandidate(string SourceEntry, SkeletonBlob Skeleton, bool Authoritative);

internal static class TransformAuditRuntime
{
    private const uint WheelStylePartType = 44;
    private static readonly List<WheelStyleAnchorDiagnostic> _wheelAnchors = [];
    private static readonly List<MeshTransformAuditDiagnostic> _meshAudit = [];
    private static readonly List<SceneSkeletonCandidate> _sceneSkeletons = [];
    private static readonly HashSet<string> _sceneSkeletonSources = new(StringComparer.OrdinalIgnoreCase);
    private static readonly HashSet<string> _wheelIdentities = new(StringComparer.Ordinal);
    private static readonly Dictionary<string, AttachmentBoneResolution> _attachmentResolutions =
        new(StringComparer.Ordinal);
    private static SceneSkeletonCandidate? _authoritativeSceneSkeleton;
    private static string _requestedSceneSkeletonPath = "";
    private static string _sceneSkeletonResolutionMode = "not_configured";

    public static IReadOnlyList<WheelStyleAnchorDiagnostic> WheelStyleAnchors => _wheelAnchors;
    public static IReadOnlyList<MeshTransformAuditDiagnostic> MeshTransformAudit => _meshAudit;
    public static int SceneSkeletonCount => _sceneSkeletons.Count + (_authoritativeSceneSkeleton is null ? 0 : 1);
    public static string RequestedSceneSkeletonPath => _requestedSceneSkeletonPath;
    public static string AuthoritativeSceneSkeletonSource => _authoritativeSceneSkeleton?.SourceEntry ?? "";
    public static string SceneSkeletonResolutionMode => _sceneSkeletonResolutionMode;

    public static void Configure(IReadOnlyList<ModelInstance> instances, string? sceneSkeletonPath)
    {
        _wheelAnchors.Clear();
        _meshAudit.Clear();
        _sceneSkeletons.Clear();
        _sceneSkeletonSources.Clear();
        _wheelIdentities.Clear();
        _attachmentResolutions.Clear();
        _authoritativeSceneSkeleton = null;
        _requestedSceneSkeletonPath = sceneSkeletonPath ?? "";
        _sceneSkeletonResolutionMode = string.IsNullOrWhiteSpace(_requestedSceneSkeletonPath)
            ? "not_declared"
            : "unresolved";
    }

    public static bool RegisterAuthoritativeSceneSkeleton(string sourceEntry, Bundle bundle)
    {
        var skeleton = bundle.Blobs.OfType<SkeletonBlob>().FirstOrDefault();
        if (skeleton is null || skeleton.Bones.Count == 0)
        {
            _sceneSkeletonResolutionMode = "resolved_entry_without_skeleton";
            return false;
        }
        _authoritativeSceneSkeleton = new SceneSkeletonCandidate(sourceEntry, skeleton, true);
        _sceneSkeletonSources.Add(sourceEntry);
        _sceneSkeletonResolutionMode = "scene_skeleton_path";
        return true;
    }

    public static void RecordSceneSkeletonResolutionFailure(string mode)
    {
        if (_authoritativeSceneSkeleton is not null)
            return;
        _sceneSkeletonResolutionMode = string.IsNullOrWhiteSpace(mode) ? "unresolved" : mode;
    }

    public static void RegisterSceneSkeleton(string sourceEntry, Bundle bundle)
    {
        var skeleton = bundle.Blobs.OfType<SkeletonBlob>().FirstOrDefault();
        if (skeleton is null || skeleton.Bones.Count == 0)
            return;
        if (!_sceneSkeletonSources.Add(sourceEntry))
            return;
        _sceneSkeletons.Add(new SceneSkeletonCandidate(sourceEntry, skeleton, false));
    }

    private static AttachmentBoneResolution? ResolveNamed(
        SceneSkeletonCandidate candidate,
        string requestedName,
        short requestedId,
        string mode,
        string sourcePrefix)
    {
        var target = candidate.Skeleton.Bones.FindIndex(
            bone => string.Equals(bone.Name, requestedName, StringComparison.OrdinalIgnoreCase));
        if (target < 0)
            return null;
        return new AttachmentBoneResolution(
            mode,
            requestedName,
            requestedId,
            candidate.Skeleton.Bones[target].Name ?? "",
            target,
            $"{sourcePrefix}:{candidate.SourceEntry}",
            ResolveBoneWorld(candidate.Skeleton, target));
    }

    private static AttachmentBoneResolution ResolveNamedSceneFallback(
        string requestedName,
        short requestedId,
        string successMode,
        string missingMode)
    {
        var sceneMatches = new List<(SceneSkeletonCandidate Candidate, int Index)>();
        foreach (var candidate in _sceneSkeletons)
        {
            var index = candidate.Skeleton.Bones.FindIndex(
                bone => string.Equals(bone.Name, requestedName, StringComparison.OrdinalIgnoreCase));
            if (index >= 0)
                sceneMatches.Add((candidate, index));
        }
        if (sceneMatches.Count == 1)
        {
            var match = sceneMatches[0];
            return new AttachmentBoneResolution(
                successMode,
                requestedName,
                requestedId,
                match.Candidate.Skeleton.Bones[match.Index].Name ?? "",
                match.Index,
                $"scene_stock_carbody:{match.Candidate.SourceEntry}",
                ResolveBoneWorld(match.Candidate.Skeleton, match.Index));
        }
        if (sceneMatches.Count > 1)
        {
            return new AttachmentBoneResolution(
                "scene_name_ambiguous",
                requestedName,
                requestedId,
                "",
                -1,
                "scene_stock_carbody",
                null);
        }
        return new AttachmentBoneResolution(
            missingMode,
            requestedName,
            requestedId,
            "",
            -1,
            "scene_skeleton",
            null);
    }

    private static bool IsBoneOnlyPlacement(ModelInstance instance)
    {
        var requestedName = instance.BoneName ?? "";
        if (string.IsNullOrWhiteSpace(requestedName)
            || string.Equals(requestedName, "<root>", StringComparison.OrdinalIgnoreCase))
            return false;

        const float zeroTranslationTolerance = 0.000001f;
        return MathF.Abs(instance.Transform.M41) < zeroTranslationTolerance
            && MathF.Abs(instance.Transform.M42) < zeroTranslationTolerance
            && MathF.Abs(instance.Transform.M43) < zeroTranslationTolerance;
    }

    public static AttachmentBoneResolution ResolveAttachmentBone(Bundle bundle, ModelInstance instance)
    {
        const string instanceSkeletonSource = "instance_model_bundle";
        var requestedName = instance.BoneName ?? "";
        var requestedId = instance.BoneId;
        var instanceSkeleton = bundle.Blobs.OfType<SkeletonBlob>().FirstOrDefault();

        if (!string.IsNullOrWhiteSpace(requestedName))
        {
            // A named attachment belongs to the model bundle first.  This is the
            // original KFPS placement namespace and is required by WheelStyle and
            // other parts whose local skeleton contains the requested bone.
            if (instanceSkeleton is not null && instanceSkeleton.Bones.Count > 0)
            {
                var childTarget = instanceSkeleton.Bones.FindIndex(
                    bone => string.Equals(bone.Name, requestedName, StringComparison.OrdinalIgnoreCase));
                if (childTarget >= 0)
                {
                    return new AttachmentBoneResolution(
                        "child_name",
                        requestedName,
                        requestedId,
                        instanceSkeleton.Bones[childTarget].Name ?? "",
                        childTarget,
                        instanceSkeletonSource,
                        ResolveBoneWorld(instanceSkeleton, childTarget));
                }
            }

            // Do not reinterpret a named attachment's numeric BoneId inside an
            // unrelated local skeleton.  When the Carbin transform has zero
            // translation, the model is structurally placed by its named car bone;
            // only then may the declared Scene.SkeletonPath namespace be used.
            if (IsBoneOnlyPlacement(instance))
            {
                if (_authoritativeSceneSkeleton is not null)
                {
                    var authoritative = ResolveNamed(
                        _authoritativeSceneSkeleton,
                        requestedName,
                        requestedId,
                        "scene_path_name_bone_only",
                        "scene_skeleton_path");
                    if (authoritative is not null)
                        return authoritative;
                }
                return new AttachmentBoneResolution(
                    "bone_only_scene_name_not_found",
                    requestedName,
                    requestedId,
                    "",
                    -1,
                    _authoritativeSceneSkeleton is null
                        ? "scene_skeleton_unavailable"
                        : $"scene_skeleton_path:{_authoritativeSceneSkeleton.SourceEntry}",
                    null);
            }

            // The Carbin matrix already carries a placement.  If its named local
            // bone cannot be resolved, preserve that matrix rather than applying a
            // same-number bone from another namespace or forcing a scene bone.
            return new AttachmentBoneResolution(
                "named_child_miss_keep_carbin",
                requestedName,
                requestedId,
                "",
                -1,
                instanceSkeleton is null ? "no_instance_skeleton" : instanceSkeletonSource,
                null);
        }

        // With no bone name, a valid numeric ID is local to the instance model
        // bundle, matching the original KFPS resolver. SnapToParent remains
        // preserved as Carbin metadata/audit data; it does not override namespace.
        if (instanceSkeleton is not null
            && requestedId >= 0
            && requestedId < instanceSkeleton.Bones.Count)
        {
            return new AttachmentBoneResolution(
                "id_only",
                requestedName,
                requestedId,
                instanceSkeleton.Bones[requestedId].Name ?? "",
                requestedId,
                instanceSkeletonSource,
                ResolveBoneWorld(instanceSkeleton, requestedId));
        }

        return new AttachmentBoneResolution(
            instanceSkeleton is null || instanceSkeleton.Bones.Count == 0 ? "no_skeleton" : "none",
            requestedName,
            requestedId,
            "",
            -1,
            instanceSkeletonSource,
            null);
    }

    private static Matrix4x4 ResolveBoneWorld(SkeletonBlob skeleton, int target)
    {
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
        return Resolve(target);
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
            instance.SnapToParent,
            instance.AssemblyName,
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

        var renderMinimum = new Vector3(float.PositiveInfinity, float.PositiveInfinity, float.PositiveInfinity);
        var renderMaximum = new Vector3(float.NegativeInfinity, float.NegativeInfinity, float.NegativeInfinity);
        var localMinimum = new Vector3(float.PositiveInfinity, float.PositiveInfinity, float.PositiveInfinity);
        var localMaximum = new Vector3(float.NegativeInfinity, float.NegativeInfinity, float.NegativeInfinity);
        var hasInstanceTransform = effectiveTransform != Matrix4x4.Identity;
        Matrix4x4 inverseInstance = Matrix4x4.Identity;
        if (hasInstanceTransform && !Matrix4x4.Invert(effectiveTransform, out inverseInstance))
            throw new InvalidDataException(
                $"{instance.Identity}/{geometry.Name} effective instance transform is not invertible.");

        foreach (var point in renderPositions)
        {
            if (!float.IsFinite(point.X) || !float.IsFinite(point.Y) || !float.IsFinite(point.Z))
                throw new InvalidDataException($"{instance.Identity}/{geometry.Name} render AABB contains a non-finite point.");
            renderMinimum = Vector3.Min(renderMinimum, point);
            renderMaximum = Vector3.Max(renderMaximum, point);

            var transformed = new Vector3(-point.X, point.Y, point.Z);
            var local = hasInstanceTransform
                ? Vector3.Transform(transformed, inverseInstance)
                : transformed;
            if (!float.IsFinite(local.X) || !float.IsFinite(local.Y) || !float.IsFinite(local.Z))
                throw new InvalidDataException($"{instance.Identity}/{geometry.Name} local AABB contains a non-finite point.");
            localMinimum = Vector3.Min(localMinimum, local);
            localMaximum = Vector3.Max(localMaximum, local);
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
            instance.SnapToParent,
            instance.AssemblyName,
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
            renderPositions.Count,
            [localMinimum.X, localMinimum.Y, localMinimum.Z],
            [localMaximum.X, localMaximum.Y, localMaximum.Z],
            [renderMinimum.X, renderMinimum.Y, renderMinimum.Z],
            [renderMaximum.X, renderMaximum.Y, renderMaximum.Z]));
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
