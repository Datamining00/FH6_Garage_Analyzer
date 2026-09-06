using System.Buffers.Binary;
using System.Globalization;
using System.Numerics;
using ForzaTechStudio.Services;
using ForzaTools.Bundles;
using ForzaTools.Bundles.Blobs;
using ForzaTools.Bundles.Metadata;

namespace Kfps.ChassisConverter;

internal sealed record WheelMorphContext(
    byte[] RawData,
    int Stride,
    int VertexStart,
    int TargetCount,
    float[] Weights);

internal static class WheelMorphRuntime
{
    private const uint WheelStylePartType = 44;
    private const int Half4Bytes = 8;
    private const int VerifiedFloat4Format = 10;

    private static string _mode = "none";
    private static float _frontDiameter;
    private static float _frontWidth;
    private static float _rearDiameter;
    private static float _rearWidth;
    private static float _axleSplitZ;
    private static bool _configured;

    public static string Mode => _mode;
    public static int AppliedMeshes { get; private set; }
    public static int AppliedVertices { get; private set; }
    public static float? AxleSplitZ => _mode == "none" || !_configured ? null : _axleSplitZ;

    public static void Disable()
    {
        _mode = "none";
        _configured = false;
        AppliedMeshes = 0;
        AppliedVertices = 0;
    }

    public static void Configure(IReadOnlyList<ModelInstance> instances)
    {
        AppliedMeshes = 0;
        AppliedVertices = 0;
        _mode = (Environment.GetEnvironmentVariable("KFPS_WHEEL_MORPH_MODE") ?? "none")
            .Trim().ToLowerInvariant();
        if (_mode is not ("none" or "diameter" or "width" or "combined"))
            throw new InvalidDataException(
                "KFPS_WHEEL_MORPH_MODE must be none, diameter, width, or combined.");
        if (_mode == "none")
        {
            _configured = false;
            return;
        }

        _frontDiameter = ReadWeight("KFPS_WHEEL_MORPH_FRONT_DIAMETER");
        _frontWidth = ReadWeight("KFPS_WHEEL_MORPH_FRONT_WIDTH");
        _rearDiameter = ReadWeight("KFPS_WHEEL_MORPH_REAR_DIAMETER");
        _rearWidth = ReadWeight("KFPS_WHEEL_MORPH_REAR_WIDTH");

        var wheelZ = instances
            .Where(instance => (uint)instance.PartType == WheelStylePartType)
            .Select(instance => instance.Transform.M43)
            .Where(float.IsFinite)
            .ToArray();
        if (wheelZ.Length < 2)
            throw new InvalidDataException(
                "Wheel morph diagnostic requires at least two WheelStyle instances.");
        var minZ = wheelZ.Min();
        var maxZ = wheelZ.Max();
        if (!float.IsFinite(minZ) || !float.IsFinite(maxZ) || maxZ - minZ <= 1e-4f)
            throw new InvalidDataException(
                "WheelStyle carbin transforms do not form distinct front/rear Z clusters.");
        _axleSplitZ = (minZ + maxZ) * 0.5f;
        _configured = true;
    }

    public static WheelMorphContext? CreateContext(
        Bundle bundle,
        ForzaGeometryData geometry,
        ModelInstance instance)
    {
        if (!_configured || _mode == "none" || (uint)instance.PartType != WheelStylePartType)
            return null;
        var mesh = geometry.SourceMesh;
        if (mesh.IsMorphDamage || mesh.MorphTargetCount == 0 || mesh.MorphDataBufferIndex < 0)
            return null;
        if (mesh.MorphTargetCount > 2)
            throw new InvalidDataException(
                $"Wheel mesh {geometry.Name} declares unsupported morph target count {mesh.MorphTargetCount}.");

        var z = instance.Transform.M43;
        if (!float.IsFinite(z) || MathF.Abs(z - _axleSplitZ) <= 1e-6f)
            throw new InvalidDataException(
                $"WheelStyle instance {instance.Identity} cannot be assigned to a front/rear axle from carbin Z.");
        var front = z > _axleSplitZ;
        var weights = EffectiveWeights(front);
        if (mesh.MorphTargetCount == 1 && MathF.Abs(weights[0]) <= 1e-12f)
            return null;
        if (mesh.MorphTargetCount == 2
            && MathF.Abs(weights[0]) <= 1e-12f
            && MathF.Abs(weights[1]) <= 1e-12f)
            return null;

        var morphBlobs = bundle.Blobs.OfType<MorphBufferBlob>().ToArray();
        MorphBufferBlob? morph = null;
        foreach (var candidate in morphBlobs)
        {
            var id = candidate.Metadatas.OfType<IdentifierMetadata>().FirstOrDefault();
            if (id is not null && (int)id.Id == mesh.MorphDataBufferIndex)
            {
                morph = candidate;
                break;
            }
        }
        if (morph is null && mesh.MorphDataBufferIndex < morphBlobs.Length)
            morph = morphBlobs[mesh.MorphDataBufferIndex];
        if (morph is null)
            throw new InvalidDataException(
                $"Wheel mesh {geometry.Name} morph buffer {mesh.MorphDataBufferIndex} was not resolved.");

        var header = morph.Header
            ?? throw new InvalidDataException($"Wheel mesh {geometry.Name} morph buffer has no header.");
        if ((int)header.Format != VerifiedFloat4Format)
            throw new InvalidDataException(
                $"Wheel mesh {geometry.Name} morph format {(int)header.Format} is not verified for weighted wheel sizing.");
        var stride = (int)header.Stride;
        var targetCount = checked((int)mesh.MorphTargetCount);
        if (stride < targetCount * Half4Bytes)
            throw new InvalidDataException(
                $"Wheel mesh {geometry.Name} morph stride {stride} is too small for {targetCount} target(s).");
        var raw = header.GetRawData();
        if (raw is null || raw.Length == 0)
            throw new InvalidDataException($"Wheel mesh {geometry.Name} morph buffer is empty.");

        var vertexStart = checked(geometry.MinVertexIndex + mesh.IndexedVertexOffset);
        if (vertexStart < 0
            || vertexStart + geometry.RawPositions.Length > header.Length
            || checked((long)(vertexStart + geometry.RawPositions.Length) * stride) > raw.LongLength)
        {
            throw new InvalidDataException(
                $"Wheel mesh {geometry.Name} morph range is outside MBuf: "
                + $"minIndex={geometry.MinVertexIndex}, base={mesh.IndexedVertexOffset}, "
                + $"start={vertexStart}, vertices={geometry.RawPositions.Length}, length={header.Length}.");
        }

        AppliedMeshes++;
        return new WheelMorphContext(raw, stride, vertexStart, targetCount, weights);
    }

    public static Vector3 DecodePositionDelta(WheelMorphContext context, int localVertexIndex)
    {
        if ((uint)localVertexIndex >= (uint)int.MaxValue)
            throw new InvalidDataException("Wheel morph local vertex index is invalid.");
        var record = checked((context.VertexStart + localVertexIndex) * context.Stride);
        var span = context.RawData.AsSpan();
        var delta = Vector3.Zero;
        for (var slot = 0; slot < context.TargetCount; slot++)
        {
            var offset = checked(record + slot * Half4Bytes);
            var x = ReadHalf(span, offset);
            var y = ReadHalf(span, offset + 2);
            var z = ReadHalf(span, offset + 4);
            var selectorRaw = ReadHalf(span, offset + 6);
            var selector = checked((int)MathF.Round(selectorRaw));
            if (!float.IsFinite(selectorRaw)
                || selector < 0
                || selector >= context.Weights.Length
                || MathF.Abs(selectorRaw - selector) > 1e-3f)
            {
                throw new InvalidDataException(
                    $"Wheel morph selector {selectorRaw} is not a verified integer weight index.");
            }
            var weight = context.Weights[selector];
            delta += new Vector3(x, y, z) * weight;
        }
        return delta;
    }

    public static void RecordVertices(int count)
    {
        if (count < 0)
            throw new InvalidDataException("Wheel morph vertex count cannot be negative.");
        AppliedVertices = checked(AppliedVertices + count);
    }

    private static float[] EffectiveWeights(bool front)
    {
        var diameter = front ? _frontDiameter : _rearDiameter;
        var width = front ? _frontWidth : _rearWidth;
        return _mode switch
        {
            "diameter" => [diameter, 0.0f],
            "width" => [0.0f, width],
            "combined" => [diameter, width],
            _ => [0.0f, 0.0f],
        };
    }

    private static float ReadWeight(string name)
    {
        var raw = Environment.GetEnvironmentVariable(name)
            ?? throw new InvalidDataException($"Missing required environment variable {name}.");
        if (!float.TryParse(raw, NumberStyles.Float, CultureInfo.InvariantCulture, out var value)
            || !float.IsFinite(value))
            throw new InvalidDataException($"{name} is not a finite invariant-culture float: {raw}");
        return value;
    }

    private static float ReadHalf(ReadOnlySpan<byte> data, int offset)
    {
        if (offset < 0 || offset + 2 > data.Length)
            throw new InvalidDataException("Wheel morph half-float record is outside MBuf.");
        var bits = BinaryPrimitives.ReadUInt16LittleEndian(data.Slice(offset, 2));
        var value = (float)BitConverter.UInt16BitsToHalf(bits);
        if (!float.IsFinite(value))
            throw new InvalidDataException("Wheel morph record contains a non-finite half float.");
        return value;
    }
}
