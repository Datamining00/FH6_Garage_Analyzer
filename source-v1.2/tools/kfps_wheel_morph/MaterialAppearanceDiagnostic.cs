using System.Numerics;
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

    // ForzaTechStudio's viewport resolves scalar U/V tiling plus Vector2/Vector4
    // parameters whose published names contain "UVTiling" or "TilingOverride".
    // The converter's vendored source subset does not include NameHashService,
    // therefore this set mirrors those exact published names at FTS commit
    // 4f373c5fb192551ce5249e320dd79b1399b693ca instead of guessing from paths.
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

    private static readonly HashSet<uint> UvTilingVectorHashes =
    [
        // Explicit TilingOverride names.
        0xB99646E7, // BaseColorAlphaTilingOverride
        0x1144D400, // BaseColorTilingOverride
        0x8BAB96B3, // RoughMetalAOTilingOverride
        0xF383EB56, // NormalTilingOverride
        0x4CCD7F85, // AlphaTilingOverride

        // Generic UV tiling names.
        0x49455E2C, // UVTiling
        0x292176F3, // UVTiling1
        0x9F4459F8, // UVTiling_1
        0xC325B227, // UVTiling_2
        0x50700B46, // UVTiling_3
        0x4A138397, // UVTiling_4
        0x426FC232, // UVTiling_5
        0xAF07D9C0, // UVTiling_6
        0x6B33A7C0, // UVTiling_7
        0xA1AB3F08, // UVTiling_8
        0xADBA1134, // UVTiling_9
        0x708065F7, // UVTiling_10
        0x9A7DB1FA, // UVTiling_11
        0xFD6BB566, // UVTiling_12
        0x32879008, // UVTiling_13
        0x52E3B8D7, // UVTiling_14
        0x0318C562, // UVTiling_15
        0x0C0672D0, // UVTilingA
        0x3AD36FA3, // SlowUVTiling
        0x12D9D5DD, // FastUVTiling
        0x4111A187, // SlowUVTiling_1
        0x691B1BF9, // FastUVTiling_1

        // Diffuse/base-colour and pattern tiling.
        0x5EFF55B5, // CH1DiffuseUVTiling
        0x8C9998CD, // CH1DiffuseUVTiling_1
        0xF91D9509, // CH1DiffuseUVTiling_2
        0x35A9A138, // CH1DiffuseUVTiling_3
        0x6DB70810, // CH2DiffuseTextureUVTiling
        0x61E2989E, // CH2DiffuseUVTiling
        0x84659583, // CH1DiffuseMapUVTiling
        0x8D7CA8AF, // DiffuseMasks_UVTiling
        0xC30E6C10, // DiffuseVarTexture_UVTiling
        0xC996F379, // DiffusePatternUVTiling
        0xEA33F406, // BaseColorRoughnessTiledDirtUVTiling

        // Normal/clearcoat/flake tiling.
        0x28120924, // CH1NormalMapUVTiling
        0xD5C29BCB, // CH1NormalMapUVTiling_1
        0x3FAE8362, // CH1NormalMapUVTiling_2
        0xF18DA88C, // CH1NormalUVTiling
        0xF568373C, // CH1NormalUVTiling_1
        0xDCA083CE, // CH2NormalUVTiling
        0x76941D62, // CH2NormalMapUVTiling
        0x76B4575A, // CH2NormalUVTiling_1
        0x841064ED, // CH2NormalMapA_UVTiling
        0x6F27DFEE, // CH2NormalMapB_UVTiling
        0x6248E636, // CH1_CLCNormalMapUVTiling
        0xF189C35D, // CH1_CLCNormalMapUVTiling_1
        0x3B2652BE, // DetailNomalAUVTiling
        0x630F91BE, // NormalUVTiling
        0x9A8A08E0, // OrangePeelUVTiling
        0x9EFBEA4A, // FlakeNormalUVTiling
        0xAF68C0AB, // FlakeTintUVTiling
        0x2BAFF6C7, // FlakeUVTiling
        0xEBF24437, // CH1Mask_Blur_UVTiling
        0x19F682E4, // CH1Normal_Blur_UVTiling

        // Gloss/roughness/specular/AO tiling.
        0xACB544D0, // CH1GlossUVTiling
        0x46AA5E2B, // CH2GlossMaskUVTiling
        0x6F17677C, // CH1GlossDiffMaskUVTiling
        0x19F25E41, // CH1GlossDiffMaskUVTiling_1
        0x061BA6B4, // GlossMaskUVTiling
        0xE1008FC5, // GlossTextureMaskUVTiling
        0xA1A59714, // GlossAUVTiling
        0x894A360A, // GlossUVTiling
        0xD5E8D0C1, // GlassRoughnessUVTiling
        0xE8EC0028, // CH1AOUVTiling
        0xFEBBD17D, // CH1AOUVTiling_1

        // Mask/alpha/opacity/reflection tiling.
        0x327CFB31, // CH1MaskUVTiling
        0x9D013746, // CH1MaskUVTiling_1
        0xB3B9EA51, // CH1MaskUVTiling_2
        0xEA24DC3F, // CH1MaskUVTiling_3
        0xAD410690, // Ch2MaskUVTiling
        0xCEF3CC60, // Ch2MaskUVTiling_1
        0x3A2D8D16, // CH1LERPMaskUVTiling
        0xCD060FD0, // CH1PatternMaskUVTiling
        0x84776FB1, // CH1OpacityUVTiling
        0xE81E684D, // CH1OpacityMapUVTiling
        0xEA97A943, // CH1OpacityMapUVTiling_1
        0xB1981147, // CH1OppacityUVTiling
        0xE5AEA6D6, // MaskUVTiling
        0x7B5D1FC6, // CH1RTintUVTiling
        0x5499D039, // CH2RTintUVTiling
        0xCF1717DD, // Reflected_RTint_UVTiling
        0x488F29C3, // MaskAUVTiling
        0xA3B892C0, // MaskBUVTiling
        0x6103BD29, // MaskClouds_L_UVTiling
        0x58640C72, // MaskClouds_R_UVTiling
        0x694E917B, // ScrollingPixel1_UVTiling
        0x82792A78, // ScrollingPixel2_UVTiling
        0x60416837, // ScrollingAlphaMask_UVTiling

        // Light/emissive/text/radiosity tiling.
        0x42B7C070, // CH2LightMapUVTilingA
        0xA9807B73, // CH2LightMapUVTilingB
        0x60CD4B5E, // CH1LightMaskMaskUVTiling
        0x59983117, // StaticCH1LightMapUVTiling
        0xDDE93258, // CH1LightMapUVTiling
        0x599C16D0, // CH1LightMapUVTiling_1
        0xEF1DA25B, // CH1IlluminationUVTiling
        0xB31ACBB2, // CH2LightMapUVTiling
        0x5039ECB0, // CH3RadiosityMapUVTiling
        0x51D94226, // TextTextureArrayUVTiling0
        0xF7AE4992, // TextTextureArrayUVTiling1
        0xDAD0F024, // TextUVTiling

        // General material/effect UV tiling names still consumed by the same FTS
        // material-wide resolver when their value is Vector2/Vector4.
        0x9A1F8805, // CH1CloudinessMapUVTiling
        0x4C2D24B8, // dyRTintUVTiling
        0x7BD0DEE5, // CH1MultiplyMaskUVTiling
        0xEC71D28B, // CH2RetroPatternMaskUVTiling
        0xF6C42060, // MotionVector_Y_UVTiling
        0x7315BB5A, // MotionVector_UVTiling_Z
        0xD6B5228F, // Texture2_UVTiling
        0xC97B65FE, // Texture1_UVTiling
        0x60686A61, // Texture3_UVTiling
        0x218CEB47, // Texture1_UVTiling_1
        0xF275BE80, // StripeUVTiling
        0x1AAC2FED, // LargeUVTiling
        0xD711B59A, // MidUVTiling
        0xC91B0EBA, // ModulateUVTiling
        0xA976318F, // MacroUVTiling
        0xA0D72C0A, // MicroUVTiling
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

                if (parameter.Value is Vector2 vector2)
                {
                    if (UvTilingVectorHashes.Contains(hash))
                    {
                        uvTiling.X = SanitizeTilingValue(vector2.X);
                        uvTiling.Y = SanitizeTilingValue(vector2.Y);
                        uvTilingVectorHash = hashText;
                    }
                }
                else if (parameter.Value is Vector4 vector)
                {
                    if (UvTilingVectorHashes.Contains(hash))
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
                    if (UTilingHashes.Contains(hash))
                    {
                        uvTiling.X = SanitizeTilingValue(scalar);
                        uvTilingUHash = hashText;
                    }
                    else if (VTilingHashes.Contains(hash))
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

    private static float SanitizeTilingValue(float value) =>
        float.IsFinite(value) && MathF.Abs(value) > 1e-6f ? value : 1.0f;

    private static MaterialAppearanceDiagnostic Empty(string mode, string materialName) =>
        new(
            ResolutionMode: mode,
            MaterialSource: "",
            MaterialName: materialName,
            ParameterBlobCount: 0,
            ParameterCount: 0,
            BaseColor: null,
            BaseColorParameterHash: "",
            Roughness: null,
            RoughnessParameterHash: "",
            Gloss: null,
            GlossParameterHash: "",
            ClearCoatGloss: null,
            ClearCoatGlossParameterHash: "",
            Metalness: null,
            MetalnessParameterHash: "",
            MetalSwitch: null,
            F0: null,
            F0ParameterHash: "",
            ClearCoatF0: null,
            ClearCoatF0ParameterHash: "",
            EmissiveColor: null,
            EmissiveColorParameterHash: "",
            EmissiveIntensity: null,
            EmissiveIntensityParameterHash: "",
            UvTiling: [1.0f, 1.0f],
            UvTilingUParameterHash: "",
            UvTilingVParameterHash: "",
            UvTilingVectorParameterHash: "",
            TexturePaths: [],
            TextureBindings: []);
}