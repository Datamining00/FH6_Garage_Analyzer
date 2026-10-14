using ForzaTools.Bundles;
using ForzaTools.Bundles.Blobs;

namespace Kfps.ChassisConverter;

internal sealed record MaterialbinReferenceEntry(
    int Order,
    string SourceKind,
    string SourceField,
    string ParameterHash,
    string PathHash,
    string ReferencePath);

internal sealed record MaterialbinReferenceDiagnostic(
    string Format,
    int Revision,
    string Status,
    string InputPath,
    int BlobCount,
    MaterialbinReferenceEntry[] References,
    string[] Issues,
    bool GameDataModified);

internal static class MaterialbinReferenceRuntime
{
    public const int Revision = 1;

    public static MaterialbinReferenceDiagnostic Diagnose(string inputPath)
    {
        var fullPath = Path.GetFullPath(inputPath);
        if (!File.Exists(fullPath))
            return Empty(fullPath, "materialbin_input_missing", "The materialbin input file does not exist.");

        try
        {
            using var stream = File.OpenRead(fullPath);
            var bundle = new Bundle();
            bundle.Load(stream);

            var references = new List<MaterialbinReferenceEntry>();
            var order = 0;

            // Match the pinned ForzaTechStudio manufacturer-material traversal:
            // every MatLBlob first, and within each blob Path -> PathV1_1 -> PathV1_2.
            foreach (var matl in bundle.Blobs.OfType<MatLBlob>())
            {
                AddMatlReference(references, ref order, "Path", matl.Path);
                AddMatlReference(references, ref order, "PathV1_1", matl.PathV1_1);
                AddMatlReference(references, ref order, "PathV1_2", matl.PathV1_2);
            }

            // Only after MatL references, match FTS by enumerating shader/default
            // parameter blobs and preserving Texture2D parameter order verbatim.
            foreach (var blob in bundle.Blobs)
            {
                if (blob is not MaterialShaderParameterBlob parameterBlob)
                    continue;
                if (parameterBlob.Tag != Bundle.TAG_BLOB_MaterialShaderParameter
                    && parameterBlob.Tag != Bundle.TAG_BLOB_DefaultShaderParameter)
                    continue;

                foreach (var parameter in parameterBlob.Parameters)
                {
                    if (parameter.Type != ShaderParameterType.Texture2D)
                        continue;
                    if (parameter.Value is not TextureParameter texture)
                        continue;
                    if (string.IsNullOrWhiteSpace(texture.Path))
                        continue;

                    references.Add(new MaterialbinReferenceEntry(
                        order++,
                        "texture2d",
                        "TextureParameter.Path",
                        $"{parameter.NameHash:X8}",
                        $"{texture.PathHash:X8}",
                        NormalizePath(texture.Path)));
                }
            }

            return new MaterialbinReferenceDiagnostic(
                "fh6_materialbin_reference_diagnostic_v1",
                Revision,
                "materialbin_references_parsed",
                fullPath,
                bundle.Blobs.Count,
                references.ToArray(),
                [],
                false);
        }
        catch (Exception error)
        {
            return Empty(
                fullPath,
                "materialbin_parse_failed",
                $"{error.GetType().Name}: {error.Message}");
        }
    }

    private static void AddMatlReference(
        List<MaterialbinReferenceEntry> output,
        ref int order,
        string field,
        string? path)
    {
        if (string.IsNullOrWhiteSpace(path))
            return;
        output.Add(new MaterialbinReferenceEntry(
            order++,
            "matl",
            field,
            string.Empty,
            string.Empty,
            NormalizePath(path)));
    }

    private static string NormalizePath(string path)
        => path.Trim().Replace('\\', '/');

    private static MaterialbinReferenceDiagnostic Empty(
        string inputPath,
        string status,
        string issue)
        => new(
            "fh6_materialbin_reference_diagnostic_v1",
            Revision,
            status,
            inputPath,
            0,
            [],
            [issue],
            false);
}
