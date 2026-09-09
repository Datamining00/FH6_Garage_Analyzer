using System.Numerics;
using ForzaTechStudio.Services;
using ForzaTools.Bundles;
using ForzaTools.Bundles.Blobs;
using ForzaTools.Bundles.Metadata;

namespace Kfps.ChassisConverter;

internal sealed record MaterialTextureBindingDiagnostic(
    string ParameterHash,
    string PathHash,
    string TexturePath);

internal sealed record MaterialAppearanceDiagnostic(
    string ResolutionMode,
    string MaterialSource,
    string MaterialName,
    int ParameterBlobCount,
    int ParameterCount,
    float[]? BaseColor,
    string BaseColorParameterHash,
    float? Roughness,
    string RoughnessParameterHash,
    float? Gloss,
    string GlossParameterHash,
    float? ClearCoatGloss,
    string ClearCoatGlossParameterHash,
    float? Metalness,
    string MetalnessParameterHash,
    bool? MetalSwitch,
    float[]? F0,
    string F0ParameterHash,
    float[]? ClearCoatF0,
    string ClearCoatF0ParameterHash,
    float[]? EmissiveColor,
    string EmissiveColorParameterHash,
    float? EmissiveIntensity,
    string EmissiveIntensityParameterHash,
    float[] UvTiling,
    string UvTilingUParameterHash,
    string UvTilingVParameterHash,
    string UvTilingVectorParameterHash,
    string[] TexturePaths,
    MaterialTextureBindingDiagnostic[] TextureBindings);

internal static class MaterialAppearanceRuntime
{
    // These parameter hashes are shader semantics published by ForzaTechStudio's
    // NameHashService / material renderer. They are global shader identifiers,
    // never vehicle/model-specific appearance overrides.
    private static readonly HashSet<uint> DiffuseColorHashes =
    [
        0xEA718FBE, 0x53A946B6, 0x6B242133, 0x63040D89, 0xF51639BE,
        0x57C321A6, 0x73A9E2DF, 0x1F3EB7A9, 0xEF5CCE09, 0x76BEA808,
        0x1F30F777, 0x1925D9BF, 0xD0F0433A, 0xA76D0485, 0xD9826618,
        0x00FC00E4, 0x1F0BBA20, 0x36976C2B, 0x5D1D0449,
        0x0014A502, 0xC0CB2820, 0x3FA9F5C9, 0x003E4460, 0x8467AAA4,
    ];

    private static readonly HashSet<uint> RoughnessHashes =
    [
        0xA05F6E3F, // Roughness
        0x649F46D0, // F_Roughness
        0x0DECD3CD, // L3_Roughness
    ];

    private static readonly HashSet<uint> GlossHashes =
    [
        0x5FF94E67, // Gloss_floatVal
        0x52E99DA3, // GlossA_floatVal
        0xB9DE26A0, // GlossB_floatVal
        0x99CC69B1, // FlakeGloss_floatVal
        0xD6A86466, // FlakeGlossB_floatVal
    ];

    private const uint ClearCoatGlossHash = 0x7E88DE7D;

    private static readonly HashSet<uint> MetalnessHashes =
    [
        0x1B51AB81, // F_Metalness
        0x72223E9C, // L3_Metalness
        0xDF91836E, // Metalness
    ];

    private const uint MetalSwitchHash = 0x989B026F;

    private static readonly HashSet<uint> F0Hashes =
    [
        0x938926B0, // F0Vector4
        0x1F9B6488, // F0aVector4
        0x9114636B, // F0bVector4
    ];

    private const uint ClearCoatF0Hash = 0x23C8B47A;

    private static readonly HashSet<uint> EmissiveColorHashes =
    [
        0x21EC1E4D, // EmissiveColor
        0xEFBBC518, // EmissiveTint
    ];

    private static readonly HashSet<uint> EmissiveIntensityHashes =
    [
        0x074CCD8C, 0x9421C781, 0xD78943E8, 0x4C6E94DA, 0x22F9702D,
    ];

    // ForzaTechStudio viewport material UV tiling contract. KFPS already bakes
    // MeshBlob.TexCoordTransforms plus the source V flip into exported UVs;
    // these material-level multipliers are the remaining transform.
    private static readonly HashSet<uint> UTilingHashes =
    [
        0x19A7D8F1, // U_Tiling
        0xB01AEE8E, // U_Tiling observed in shaderbin parameter tables
    ];

    private static readonly HashSet<uint> VTilingHashes =
    [
        0x4A3D8375, // V_Tiling
        0x3E95E96D, // V_Tiling observed in shaderbin parameter tables
    ];

    public static MaterialAppearanceDiagnostic Resolve(Bundle modelBundle, string materialName)
    {
        var requestedName = (materialName ?? string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(requestedName)
            || string.Equals(requestedName, "Unknown", StringComparison.OrdinalIgnoreCase))
        {
            return Empty("material_name_unavailable", requestedName);
        }

        var candidates = modelBundle.Blobs
            .OfType<MaterialBlob>()
            .Where(blob => string.Equals(
                blob.Metadatas.OfType<NameMetadata>().FirstOrDefault()?.Name ?? string.Empty,
                requestedName,
                StringComparison.OrdinalIgnoreCase))
            .ToList();
        if (candidates.Count == 0)
            return Empty("embedded_material_not_found", requestedName);
        if (candidates.Count != 1)
            return Empty("embedded_material_name_ambiguous", requestedName);

        var material = candidates[0];
        if (material.Bundle is null)
            return Empty("embedded_material_bundle_unparsed", requestedName);

        var parameterBlobs = material.Bundle.Blobs
            .OfType<MaterialShaderParameterBlob>()
            .Where(blob => blob.Tag == Bundle.TAG_BLOB_MaterialShaderParameter
                || blob.Tag == Bundle.TAG_BLOB_DefaultShaderParameter)
            .ToList();
        if (parameterBlobs.Count == 0)
            return Empty("embedded_material_has_no_shader_parameters", requestedName);

        float[]? baseColor = null;
        var baseColorHash = string.Empty;
        float? roughness = null;
        var roughnessHash = string.Empty;
        float? gloss = null;
        var glossHash = string.Empty;
        float? clearCoatGloss = null;
        var clearCoatGlossHash = string.Empty;
        float? metalness = null;
        var metalnessHash = string.Empty;
        bool? metalSwitch = null;
        float[]? f0 = null;
        var f0Hash = string.Empty;
        float[]? clearCoatF0 = null;
        var clearCoatF0Hash = string.Empty;
        float[]? emissiveColor = null;
        var emissiveColorHash = string.Empty;
        float? emissiveIntensity = null;
        var emissiveIntensityHash = string.Empty;
        var uvTiling = new Vector2(1.0f, 1.0f);
        var uvTilingUHash = string.Empty;
        var uvTilingVHash = string.Empty;
        var uvTilingVectorHash = string.Empty;
        var texturePaths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var textureBindings = new Dictionary<string, MaterialTextureBindingDiagnostic>(StringComparer.OrdinalIgnoreCase);
        var parameterCount = 0;

        foreach (var blob in parameterBlobs)
        {
            foreach (var parameter in blob.Parameters)
            {
                parameterCount++;
                var hash = parameter.NameHash;
                var hashText = $"{hash:X8}";
                var parameterName = NameHashService.Instance.GetName(hash) ?? string.Empty;

                if (parameter.Value is Vector2 vector2)
                {
                    if (IsUvTilingVectorParameter(parameterName))
                    {
                        uvTiling.X = SanitizeTilingValue(vector2.X);
                        uvTiling.Y = SanitizeTilingValue(vector2.Y);
                        uvTilingVectorHash = hashText;
                    }
                }
                else if (parameter.Value is Vector4 vector)
                {
                    if (IsUvTilingVectorParameter(parameterName))
                    {
                        uvTiling.X = SanitizeTilingValue(vector.X);
                        uvTiling.Y = SanitizeTilingValue(vector.Y);
                        uvTilingVectorHash = hashText;
                    }
                    if (DiffuseColorHashes.Contains(hash))
                    {
                        baseColor = VectorValues(vector);
                        baseColorHash = hashText;
                    }
                    if (F0Hashes.Contains(hash))
                    {
                        f0 = VectorValues(vector);
                        f0Hash = hashText;
                    }
                    if (hash == ClearCoatF0Hash)
                    {
                        clearCoatF0 = VectorValues(vector);
                        clearCoatF0Hash = hashText;
                    }
                    if (EmissiveColorHashes.Contains(hash))
                    {
                        emissiveColor = VectorValues(vector);
                        emissiveColorHash = hashText;
                    }
                }
                else if (parameter.Value is float scalar && float.IsFinite(scalar))
                {
                    if (UTilingHashes.Contains(hash)
                        || parameterName.Equals("U_Tiling", StringComparison.OrdinalIgnoreCase))
                    {
                        uvTiling.X = SanitizeTilingValue(scalar);
                        uvTilingUHash = hashText;
                    }
                    else if (VTilingHashes.Contains(hash)
                        || parameterName.Equals("V_Tiling", StringComparison.OrdinalIgnoreCase))
                    {
                        uvTiling.Y = SanitizeTilingValue(scalar);
                        uvTilingVHash = hashText;
                    }
                    else if (RoughnessHashes.Contains(hash))
                    {
                        roughness = scalar;
                        roughnessHash = hashText;
                    }
                    else if (GlossHashes.Contains(hash))
                    {
                        gloss = scalar;
                        glossHash = hashText;
                    }
                    else if (hash == ClearCoatGlossHash)
                    {
                        clearCoatGloss = scalar;
                        clearCoatGlossHash = hashText;
                    }
                    else if (MetalnessHashes.Contains(hash))
                    {
                        metalness = scalar;
                        metalnessHash = hashText;
                    }
                    else if (EmissiveIntensityHashes.Contains(hash))
                    {
                        emissiveIntensity = scalar;
                        emissiveIntensityHash = hashText;
                    }
                }
                else if (hash == MetalSwitchHash && parameter.Value is bool enabled)
                {
                    metalSwitch = enabled;
                }
                else if (parameter.Type == ShaderParameterType.Texture2D
                    && parameter.Value is TextureParameter texture
                    && !string.IsNullOrWhiteSpace(texture.Path))
                {
                    // Preserve exact binding provenance. Decoding/sampling remains
                    // downstream; no diffuse/normal/roughness role is guessed here.
                    var texturePath = texture.Path.Replace('\\', '/');
                    var pathHashText = $"{texture.PathHash:X8}";
                    texturePaths.Add(texturePath);
                    textureBindings[$"{hashText}|{pathHashText}|{texturePath}"] =
                        new MaterialTextureBindingDiagnostic(hashText, pathHashText, texturePath);
                }
            }
        }

        return new MaterialAppearanceDiagnostic(
            "embedded_material_shader_parameters",
            "model_bundle_material_blob",
            requestedName,
            parameterBlobs.Count,
            parameterCount,
            baseColor,
            baseColorHash,
            roughness,
            roughnessHash,
            gloss,
            glossHash,
            clearCoatGloss,
            clearCoatGlossHash,
            metalness,
            metalnessHash,
            metalSwitch,
            f0,
            f0Hash,
            clearCoatF0,
            clearCoatF0Hash,
            emissiveColor,
            emissiveColorHash,
            emissiveIntensity,
            emissiveIntensityHash,
            [uvTiling.X, uvTiling.Y],
            uvTilingUHash,
            uvTilingVHash,
            uvTilingVectorHash,
            texturePaths.OrderBy(value => value, StringComparer.OrdinalIgnoreCase).Take(32).ToArray(),
            textureBindings.Values
                .OrderBy(value => value.ParameterHash, StringComparer.OrdinalIgnoreCase)
                .ThenBy(value => value.PathHash, StringComparer.OrdinalIgnoreCase)
                .ThenBy(value => value.TexturePath, StringComparer.OrdinalIgnoreCase)
                .Take(64)
                .ToArray());
    }

    private static float[] VectorValues(Vector4 value) => [value.X, value.Y, value.Z, value.W];

    private static bool IsUvTilingVectorParameter(string parameterName) =>
        parameterName.Contains("uvtiling", StringComparison.OrdinalIgnoreCase)
        || parameterName.Contains("tilingoverride", StringComparison.OrdinalIgnoreCase)
        || parameterName.Equals("BaseColorAlphaTilingOverride", StringComparison.OrdinalIgnoreCase)
        || parameterName.Equals("BaseColorTilingOverride", StringComparison.OrdinalIgnoreCase);

    private static float SanitizeTilingValue(float value) =>
        float.IsFinite(value) && MathF.Abs(value) > 1e-6f ? value : 1.0f;

    private static MaterialAppearanceDiagnostic Empty(string mode, string materialName) =>
        new(
            mode,
            "",
            materialName,
            0,
            0,
            null,
            "",
            null,
            "",
            null,
            "",
            null,
            "",
            null,
            null,
            "",
            null,
            "",
            null,
            "",
            null,
            "",
            [1.0f, 1.0f],
            "",
            "",
            "",
            [],
            []);
}
