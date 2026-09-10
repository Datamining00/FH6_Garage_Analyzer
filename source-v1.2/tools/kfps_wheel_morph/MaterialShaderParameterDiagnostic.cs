using ForzaTools.Bundles;
using ForzaTools.Bundles.Blobs;
using System.Numerics;

namespace Kfps.ChassisConverter;

internal sealed record MaterialShaderParameterSnapshot(
    int Order,
    string SourceKind,
    string Key,
    string NameHash,
    int TypeCode,
    string TypeName,
    int VersionMajor,
    int VersionMinor,
    string Guid,
    string ExtraValue,
    string ValueKind,
    bool? BoolValue,
    int? IntValue,
    float? FloatValue,
    float[]? VectorValue,
    string? TexturePath,
    string? TexturePathHash,
    int? SamplerAddressU,
    int? SamplerAddressV,
    int? SamplerMode,
    float[][]? GradientValues,
    string? RawValueText);

internal sealed record MaterialShaderEffectiveParameter(
    int Order,
    string Key,
    string SourceState,
    MaterialShaderParameterSnapshot? ShaderDefault,
    MaterialShaderParameterSnapshot? MaterialOverride,
    MaterialShaderParameterSnapshot Effective);

internal sealed record MaterialShaderParameterDiagnostic(
    string Format,
    int Revision,
    string Status,
    string MaterialPath,
    string ShaderPath,
    int MaterialOverrideCount,
    int ShaderDefaultCount,
    int EffectiveParameterCount,
    int DuplicateMaterialOverrideKeyCount,
    int DuplicateShaderDefaultKeyCount,
    MaterialShaderParameterSnapshot[] MaterialOverrides,
    MaterialShaderParameterSnapshot[] ShaderDefaults,
    MaterialShaderEffectiveParameter[] EffectiveParameters,
    string CompositionRule,
    string[] Issues,
    bool RenderingEnabled,
    bool GameDataModified);

internal static class MaterialShaderParameterRuntime
{
    public const int Revision = 1;
    private const string Format = "fh6_material_shader_parameter_diagnostic_v1";

    public static MaterialShaderParameterDiagnostic Diagnose(string materialPath, string shaderPath)
    {
        var fullMaterialPath = Path.GetFullPath(materialPath);
        var fullShaderPath = Path.GetFullPath(shaderPath);
        if (!File.Exists(fullMaterialPath))
            return Empty(fullMaterialPath, fullShaderPath, "material_input_missing", "The materialbin input file does not exist.");
        if (!File.Exists(fullShaderPath))
            return Empty(fullMaterialPath, fullShaderPath, "shader_input_missing", "The shaderbin input file does not exist.");

        try
        {
            var materialBundle = LoadBundle(fullMaterialPath);
            var shaderBundle = LoadBundle(fullShaderPath);

            var materialBlob = materialBundle.Blobs
                .OfType<MaterialShaderParameterBlob>()
                .FirstOrDefault(blob => blob.Tag == Bundle.TAG_BLOB_MaterialShaderParameter);
            var shaderBlob = shaderBundle.Blobs
                .OfType<MaterialShaderParameterBlob>()
                .FirstOrDefault(blob => blob.Tag == Bundle.TAG_BLOB_DefaultShaderParameter);

            if (shaderBlob == null)
                return Empty(fullMaterialPath, fullShaderPath, "shader_default_parameter_blob_missing", "The linked shaderbin has no default shader parameter blob.");

            var materialOverrides = Snapshot(materialBlob?.Parameters, "material_override");
            var shaderDefaults = Snapshot(shaderBlob.Parameters, "shader_default");

            var defaultGroups = shaderDefaults
                .GroupBy(parameter => parameter.Key, StringComparer.OrdinalIgnoreCase)
                .ToArray();
            var overrideGroups = materialOverrides
                .GroupBy(parameter => parameter.Key, StringComparer.OrdinalIgnoreCase)
                .ToArray();

            // Match the ForzaTechStudio Materials & Shaders workstation contract:
            // key = NameHash + Type, first value per source wins, then a material
            // override replaces the linked shader default with the same key.
            var defaultsByKey = defaultGroups.ToDictionary(
                group => group.Key,
                group => group.First(),
                StringComparer.OrdinalIgnoreCase);
            var overridesByKey = overrideGroups.ToDictionary(
                group => group.Key,
                group => group.First(),
                StringComparer.OrdinalIgnoreCase);

            var orderedKeys = new List<string>();
            var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var parameter in shaderDefaults)
            {
                if (seen.Add(parameter.Key))
                    orderedKeys.Add(parameter.Key);
            }
            foreach (var parameter in materialOverrides)
            {
                if (seen.Add(parameter.Key))
                    orderedKeys.Add(parameter.Key);
            }

            var effective = new List<MaterialShaderEffectiveParameter>(orderedKeys.Count);
            for (var index = 0; index < orderedKeys.Count; index++)
            {
                var key = orderedKeys[index];
                defaultsByKey.TryGetValue(key, out var shaderDefault);
                overridesByKey.TryGetValue(key, out var materialOverride);
                var selected = materialOverride ?? shaderDefault!;
                effective.Add(new MaterialShaderEffectiveParameter(
                    index,
                    key,
                    materialOverride != null ? "material_override" : "shader_default",
                    shaderDefault,
                    materialOverride,
                    selected));
            }

            return new MaterialShaderParameterDiagnostic(
                Format,
                Revision,
                "material_shader_parameters_composed",
                fullMaterialPath,
                fullShaderPath,
                materialOverrides.Length,
                shaderDefaults.Length,
                effective.Count,
                overrideGroups.Count(group => group.Count() > 1),
                defaultGroups.Count(group => group.Count() > 1),
                materialOverrides,
                shaderDefaults,
                effective.ToArray(),
                "key=NameHash|Type; first parameter per source; material override wins over linked shader default",
                [],
                false,
                false);
        }
        catch (Exception error)
        {
            return Empty(
                fullMaterialPath,
                fullShaderPath,
                "material_shader_parameter_parse_failed",
                $"{error.GetType().Name}: {error.Message}");
        }
    }

    private static Bundle LoadBundle(string path)
    {
        using var stream = File.OpenRead(path);
        var bundle = new Bundle();
        bundle.Load(stream);
        return bundle;
    }

    private static MaterialShaderParameterSnapshot[] Snapshot(
        IEnumerable<ShaderParameter>? parameters,
        string sourceKind)
    {
        if (parameters == null)
            return [];

        return parameters
            .Select((parameter, index) => Snapshot(parameter, index, sourceKind))
            .ToArray();
    }

    private static MaterialShaderParameterSnapshot Snapshot(
        ShaderParameter parameter,
        int order,
        string sourceKind)
    {
        bool? boolValue = null;
        int? intValue = null;
        float? floatValue = null;
        float[]? vectorValue = null;
        string? texturePath = null;
        string? texturePathHash = null;
        int? samplerAddressU = null;
        int? samplerAddressV = null;
        int? samplerMode = null;
        float[][]? gradientValues = null;
        string? rawValueText = null;
        string valueKind;

        switch (parameter.Type)
        {
            case ShaderParameterType.Vector:
            case ShaderParameterType.Color:
            case ShaderParameterType.Swizzle:
            case ShaderParameterType.FunctionRange:
                valueKind = "vector4";
                if (parameter.Value is Vector4 vector4)
                    vectorValue = [vector4.X, vector4.Y, vector4.Z, vector4.W];
                else
                    rawValueText = parameter.Value?.ToString();
                break;
            case ShaderParameterType.Vector2:
                valueKind = "vector2";
                if (parameter.Value is Vector2 vector2)
                    vectorValue = [vector2.X, vector2.Y];
                else
                    rawValueText = parameter.Value?.ToString();
                break;
            case ShaderParameterType.Float:
                valueKind = "float";
                if (parameter.Value is float scalar)
                    floatValue = scalar;
                else
                    rawValueText = parameter.Value?.ToString();
                break;
            case ShaderParameterType.Bool:
                valueKind = "bool";
                if (parameter.Value is bool boolean)
                    boolValue = boolean;
                else
                    rawValueText = parameter.Value?.ToString();
                break;
            case ShaderParameterType.Int:
                valueKind = "int";
                if (parameter.Value is int integer)
                    intValue = integer;
                else
                    rawValueText = parameter.Value?.ToString();
                break;
            case ShaderParameterType.Texture2D:
                valueKind = "texture2d";
                if (parameter.Value is TextureParameter texture)
                {
                    texturePath = texture.Path;
                    texturePathHash = $"{texture.PathHash:X8}";
                }
                else
                    rawValueText = parameter.Value?.ToString();
                break;
            case ShaderParameterType.Sampler:
                valueKind = "sampler";
                if (parameter.Value is SamplerParameter sampler)
                {
                    samplerAddressU = sampler.AddressU;
                    samplerAddressV = sampler.AddressV;
                    samplerMode = sampler.UnkType;
                }
                else
                    rawValueText = parameter.Value?.ToString();
                break;
            case ShaderParameterType.ColorGradient:
                valueKind = "color_gradient";
                if (parameter.Value is ColorGradientParameter gradient)
                {
                    gradientValues = gradient.Values
                        .Select(value => new[] { value.X, value.Y, value.Z, value.W })
                        .ToArray();
                }
                else
                    rawValueText = parameter.Value?.ToString();
                break;
            default:
                valueKind = "unsupported";
                rawValueText = parameter.Value?.ToString();
                break;
        }

        return new MaterialShaderParameterSnapshot(
            order,
            sourceKind,
            $"{parameter.NameHash:X8}|{(byte)parameter.Type:X2}",
            $"{parameter.NameHash:X8}",
            (byte)parameter.Type,
            parameter.Type.ToString(),
            parameter.VersionMajor,
            parameter.VersionMinor,
            parameter.Guid == Guid.Empty ? string.Empty : parameter.Guid.ToString("D"),
            parameter.UnkV3_1 == 0 ? string.Empty : $"{parameter.UnkV3_1:X8}",
            valueKind,
            boolValue,
            intValue,
            floatValue,
            vectorValue,
            texturePath,
            texturePathHash,
            samplerAddressU,
            samplerAddressV,
            samplerMode,
            gradientValues,
            rawValueText);
    }

    private static MaterialShaderParameterDiagnostic Empty(
        string materialPath,
        string shaderPath,
        string status,
        string issue)
        => new(
            Format,
            Revision,
            status,
            materialPath,
            shaderPath,
            0,
            0,
            0,
            0,
            0,
            [],
            [],
            [],
            "key=NameHash|Type; first parameter per source; material override wins over linked shader default",
            [issue],
            false,
            false);
}
