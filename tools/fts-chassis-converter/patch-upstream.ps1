param(
    [Parameter(Mandatory = $true)]
    [string]$KfpsRoot
)

$ErrorActionPreference = 'Stop'

$ftsCommit = '4f373c5fb192551ce5249e320dd79b1399b693ca'
$kfpsCommit = '6f53ca3c584d78659d06d4b4a39561db67d79345'
$programBlob = 'c1bd7cf0175a14bbeaff15a7fa41a89e706d94ed'
$programRelative = 'tools/livery/chassis-converter/Program.cs'
$program = Join-Path $KfpsRoot $programRelative
$modelImporter = Join-Path $KfpsRoot 'tools/livery/chassis-converter/vendor/ForzaTechStudio/ModelImporter.cs'
$glbWriter = Join-Path $KfpsRoot 'tools/livery/chassis-converter/GlbWriter.cs'

if (-not (Test-Path $program)) {
    throw "Pinned KFPS Program.cs not found: $program"
}
if (-not (Test-Path $modelImporter)) {
    throw "Vendored ForzaTechStudio ModelImporter.cs not found: $modelImporter"
}
if (-not (Test-Path $glbWriter)) {
    throw "Pinned KFPS GlbWriter.cs not found: $glbWriter"
}

$actualCommit = (git -C $KfpsRoot rev-parse HEAD).Trim()
if ($actualCommit -ne $kfpsCommit) {
    throw "Unexpected KFPS source commit. Expected $kfpsCommit, got $actualCommit"
}

$actualProgramBlob = (git -C $KfpsRoot hash-object $programRelative).Trim()
if ($actualProgramBlob -ne $programBlob) {
    throw "Pinned Program.cs blob mismatch. Expected $programBlob, got $actualProgramBlob"
}

$importerText = Get-Content -Raw -LiteralPath $modelImporter
foreach ($required in @('GetRotationMatrix()', 'RawPositions', 'PositionScale', 'PositionTranslate', 'BoneTransform')) {
    if (-not $importerText.Contains($required)) {
        throw "Vendored FTS ModelImporter contract missing: $required"
    }
}

$text = Get-Content -Raw -LiteralPath $program
$newMethod = @'
    // FTS parity: mirror ForzaTechStudio ViewportPage.CarbinRendering.BuildCurrentRenderPositions.
    // Reconstruction order is raw -> PositionScale -> mesh rotation -> PositionTranslate
    // -> modelbin rigid-bone world transform -> carbin instance transform -> GLB handedness flip.
    private static Vector3[] TransformPositions(ForzaGeometryData geometry, Matrix4x4 instanceTransform)
    {
        var mesh = geometry.SourceMesh;
        var output = new Vector3[geometry.RawPositions.Length];
        var rotation = geometry.GetRotationMatrix();
        var hasRotation = rotation != Matrix4x4.Identity;

        for (var index = 0; index < output.Length; index++)
        {
            var raw = geometry.RawPositions[index];
            var scaled = new Vector3(
                raw.X * mesh.PositionScale.X,
                raw.Y * mesh.PositionScale.Y,
                raw.Z * mesh.PositionScale.Z);
            if (hasRotation)
                scaled = Vector3.Transform(scaled, rotation);

            var local = new Vector3(
                scaled.X + mesh.PositionTranslate.X,
                scaled.Y + mesh.PositionTranslate.Y,
                scaled.Z + mesh.PositionTranslate.Z);
            var transformed = geometry.BoneTransform == Matrix4x4.Identity
                ? local
                : Vector3.Transform(local, geometry.BoneTransform);
            if (instanceTransform != Matrix4x4.Identity)
                transformed = Vector3.Transform(transformed, instanceTransform);

            if (!float.IsFinite(transformed.X) || !float.IsFinite(transformed.Y) || !float.IsFinite(transformed.Z))
                throw new InvalidDataException($"Mesh {geometry.Name} produced a non-finite FTS vehicle-space vertex.");

            output[index] = new Vector3(-transformed.X, transformed.Y, transformed.Z);
        }
        return output;
    }

'@

$pattern = '(?s)    private static Vector3\[\] TransformPositions\(ForzaGeometryData geometry, Matrix4x4 instanceTransform\)\s*\{.*?\r?\n    \}\r?\n\r?\n(?=    private static Vector3\[\] TransformNormals)'
$matches = [regex]::Matches($text, $pattern)
if ($matches.Count -ne 1) {
    throw "Verified Program.cs contained $($matches.Count) TransformPositions method matches; expected exactly 1."
}
$text = [regex]::Replace($text, $pattern, [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $newMethod }, 1)

if (-not $text.Contains('kfps_local_chassis_conversion_v5')) {
    throw 'Pinned converter format marker was not found.'
}
$text = $text.Replace('kfps_local_chassis_conversion_v5', 'fh6_fts_chassis_conversion_v1')

Set-Content -LiteralPath $program -Value $text -Encoding utf8NoBOM

# Preserve every position morph target in the imported model. The upstream damage-only
# path omitted non-damage wheel morphs and addressed morph vertices without MinVertexIndex.
$importerText = Get-Content -Raw -LiteralPath $modelImporter
$fieldMarker = '        public Vector3[] DamageRawPositions;'
if (-not $importerText.Contains($fieldMarker)) {
    throw 'ForzaGeometryData damage morph field marker was not found.'
}
$importerText = $importerText.Replace(
    $fieldMarker,
    $fieldMarker + "`r`n        public Vector3[][] MorphRawPositionDeltas = Array.Empty<Vector3[]>();")

$decodeCallPattern = '(?s)                        // Decode damage morph buffer if mesh has a morph target.*?                        result\.Meshes\.Add\(geo\);'
$decodeCall = @'
                        // Preserve damage and non-damage position morphs. Wheel geometry uses
                        // non-damage targets for axial width and radial size.
                        if (mesh.MorphDataBufferIndex >= 0 && geo.RawPositions != null)
                        {
                            MorphBufferBlob morphBlob = null;
                            foreach (var mb in morphBlobs)
                            {
                                var idMeta = mb.Metadatas.OfType<IdentifierMetadata>().FirstOrDefault();
                                if (idMeta != null && (int)idMeta.Id == mesh.MorphDataBufferIndex)
                                {
                                    morphBlob = mb;
                                    break;
                                }
                            }
                            if (morphBlob == null && mesh.MorphDataBufferIndex < morphBlobs.Length)
                                morphBlob = morphBlobs[mesh.MorphDataBufferIndex];

                            if (morphBlob != null)
                            {
                                geo.MorphRawPositionDeltas = DecodeMorphPositionDeltas(
                                    morphBlob, geo.RawPositions.Length, geo.MinVertexIndex, mesh);
                                if (mesh.IsMorphDamage && geo.MorphRawPositionDeltas.Length > 0)
                                {
                                    var damage = new Vector3[geo.RawPositions.Length];
                                    for (int i = 0; i < damage.Length; i++)
                                        damage[i] = geo.RawPositions[i] + geo.MorphRawPositionDeltas[0][i];
                                    geo.DamageRawPositions = damage;
                                }
                            }
                        }
                        result.Meshes.Add(geo);
'@
$decodeMatches = [regex]::Matches($importerText, $decodeCallPattern)
if ($decodeMatches.Count -ne 1) {
    throw "ModelImporter contained $($decodeMatches.Count) morph decode call matches; expected exactly 1."
}
$importerText = [regex]::Replace(
    $importerText,
    $decodeCallPattern,
    [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $decodeCall },
    1)

$decodeMethodPattern = '(?s)        private static Vector3\[\] DecodeMorphDeltas\(.*?\r?\n        \}\r?\n\r?\n(?=        private static float HalfToFloat)'
$decodeMethod = @'
        private static Vector3[][] DecodeMorphPositionDeltas(
            MorphBufferBlob morphBlob,
            int vertexCount,
            int minVertexIndex,
            MeshBlob mesh)
        {
            if (vertexCount <= 0 || mesh.MorphTargetCount == 0)
                return Array.Empty<Vector3[]>();

            byte[] data;
            int baseOffset;
            var rawData = morphBlob.Header?.GetRawData();
            if (rawData != null && rawData.Length > 0)
            {
                data = rawData;
                baseOffset = 0;
            }
            else
            {
                data = morphBlob.GetContents();
                baseOffset = MODEL_BUFFER_HEADER_SIZE;
            }
            if (data == null || data.Length == 0)
                return Array.Empty<Vector3[]>();

            int stride = morphBlob.Header?.Stride > 0 ? morphBlob.Header.Stride : 8;
            int fmt = (int)(morphBlob.Header?.Format ?? 0);
            int availableVectorLanes = stride / 8;
            int targetCount = Math.Min(checked((int)mesh.MorphTargetCount), availableVectorLanes);
            if (targetCount <= 0)
                return Array.Empty<Vector3[]>();

            var targets = new Vector3[targetCount][];
            for (int target = 0; target < targetCount; target++)
                targets[target] = new Vector3[vertexCount];

            ReadOnlySpan<byte> span = new ReadOnlySpan<byte>(data);
            for (int i = 0; i < vertexCount; i++)
            {
                // Match normal vertex addressing: source index + BaseVertexLocation.
                long vertexId = (long)minVertexIndex + mesh.IndexedVertexOffset + i;
                for (int target = 0; target < targetCount; target++)
                {
                    long addr = baseOffset + vertexId * stride + target * 8L;
                    if (addr < baseOffset || addr + 8 > data.Length)
                        continue;
                    var s = span.Slice((int)addr, 8);
                    float dx, dy, dz;
                    if (fmt == 10)
                    {
                        dx = HalfToFloat(BinaryPrimitives.ReadUInt16LittleEndian(s));
                        dy = HalfToFloat(BinaryPrimitives.ReadUInt16LittleEndian(s.Slice(2)));
                        dz = HalfToFloat(BinaryPrimitives.ReadUInt16LittleEndian(s.Slice(4)));
                    }
                    else
                    {
                        dx = Math.Clamp(BinaryPrimitives.ReadInt16LittleEndian(s) / 32767f, -1f, 1f);
                        dy = Math.Clamp(BinaryPrimitives.ReadInt16LittleEndian(s.Slice(2)) / 32767f, -1f, 1f);
                        dz = Math.Clamp(BinaryPrimitives.ReadInt16LittleEndian(s.Slice(4)) / 32767f, -1f, 1f);
                    }
                    if (!float.IsFinite(dx) || !float.IsFinite(dy) || !float.IsFinite(dz))
                        throw new InvalidDataException("Morph position delta contains a non-finite value.");
                    targets[target][i] = new Vector3(dx, dy, dz);
                }
            }
            return targets;
        }

'@
$decodeMethodMatches = [regex]::Matches($importerText, $decodeMethodPattern)
if ($decodeMethodMatches.Count -ne 1) {
    throw "ModelImporter contained $($decodeMethodMatches.Count) morph decode method matches; expected exactly 1."
}
$importerText = [regex]::Replace(
    $importerText,
    $decodeMethodPattern,
    [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $decodeMethod },
    1)
Set-Content -LiteralPath $modelImporter -Value $importerText -Encoding utf8NoBOM

# Carry transformed morph deltas through the headless converter without choosing an
# unverified default weight. GLB weights remain zero until stock/tune data supplies them.
$text = Get-Content -Raw -LiteralPath $program
function Replace-ExactlyOnce([string]$InputText, [string]$Pattern, [string]$Replacement, [string]$Description) {
    $found = [regex]::Matches($InputText, $Pattern).Count
    if ($found -ne 1) {
        throw "$Description matched $found locations; expected exactly 1."
    }
    return [regex]::Replace(
        $InputText,
        $Pattern,
        [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $Replacement },
        1)
}

$text = Replace-ExactlyOnce $text `
    '    Dictionary<int, Vector2\[\]> UvChannels,\r?\n    int\[\] Indices\);' `
    "    Dictionary<int, Vector2[]> UvChannels,`n    Vector3[][] MorphPositionDeltas,`n    int[] Indices);" `
    'ChassisMesh morph field insertion'
$text = Replace-ExactlyOnce $text `
    '            var normals = TransformNormals\(geometry, instanceTransform\);' `
    "            var normals = TransformNormals(geometry, instanceTransform);`n            var morphPositionDeltas = TransformMorphPositionDeltas(geometry, instanceTransform);" `
    'Morph transform call insertion'
$text = Replace-ExactlyOnce $text `
    '                \+ uvs\.Values\.Sum\(values => \(long\)values\.Length \* 8L\)' `
    "                + uvs.Values.Sum(values => (long)values.Length * 8L)`n                + morphPositionDeltas.Sum(values => (long)values.Length * 12L)" `
    'Morph byte accounting insertion'
$text = Replace-ExactlyOnce $text `
    '                normals,\r?\n                uvs,\r?\n                indices\)\);' `
    "                normals,`n                uvs,`n                morphPositionDeltas,`n                indices));" `
    'ChassisMesh morph constructor insertion'

$normalMarker = '    private static Vector3[] TransformNormals(ForzaGeometryData geometry, Matrix4x4 instanceTransform)'
if (-not $text.Contains($normalMarker)) {
    throw 'TransformNormals marker was not found.'
}
$morphTransform = @'
    private static Vector3[][] TransformMorphPositionDeltas(
        ForzaGeometryData geometry,
        Matrix4x4 instanceTransform)
    {
        if (geometry.MorphRawPositionDeltas is not { Length: > 0 })
            return Array.Empty<Vector3[]>();
        var mesh = geometry.SourceMesh;
        var rotation = geometry.GetRotationMatrix();
        var output = new Vector3[geometry.MorphRawPositionDeltas.Length][];
        for (var target = 0; target < output.Length; target++)
        {
            var rawTarget = geometry.MorphRawPositionDeltas[target];
            if (rawTarget.Length != geometry.RawPositions.Length)
                throw new InvalidDataException($"Mesh {geometry.Name} has a mismatched morph target length.");
            var transformedTarget = new Vector3[rawTarget.Length];
            for (var index = 0; index < rawTarget.Length; index++)
            {
                var raw = rawTarget[index];
                var delta = new Vector3(
                    raw.X * mesh.PositionScale.X,
                    raw.Y * mesh.PositionScale.Y,
                    raw.Z * mesh.PositionScale.Z);
                if (rotation != Matrix4x4.Identity)
                    delta = Vector3.TransformNormal(delta, rotation);
                if (geometry.BoneTransform != Matrix4x4.Identity)
                    delta = Vector3.TransformNormal(delta, geometry.BoneTransform);
                if (instanceTransform != Matrix4x4.Identity)
                    delta = Vector3.TransformNormal(delta, instanceTransform);
                transformedTarget[index] = new Vector3(-delta.X, delta.Y, delta.Z);
            }
            output[target] = transformedTarget;
        }
        return output;
    }

'@
$text = Replace-ExactlyOnce $text ([regex]::Escape($normalMarker)) ($morphTransform + $normalMarker) `
    'Morph transform method insertion'
Set-Content -LiteralPath $program -Value $text -Encoding utf8NoBOM

$writerText = Get-Content -Raw -LiteralPath $glbWriter
$writerText = Replace-ExactlyOnce $writerText `
    ([regex]::Escape('                var indexAccessor = AddIndexAccessor(binary, bufferViews, accessors, mesh.Indices);')) `
    @'
                var morphTargets = mesh.MorphPositionDeltas.Select(values =>
                    new Dictionary<string, int>
                    {
                        ["POSITION"] = AddVector3Accessor(binary, bufferViews, accessors, values, target: 34962, bounds: false),
                    }).ToArray();
                var indexAccessor = AddIndexAccessor(binary, bufferViews, accessors, mesh.Indices);
'@ `
    'GLB morph accessor insertion'
$writerText = Replace-ExactlyOnce $writerText `
    ([regex]::Escape('                    ["kfps_material_binding_hash"] = mesh.MaterialBindingHash.ToString("X16"),')) `
    "                    [`"kfps_material_binding_hash`"] = mesh.MaterialBindingHash.ToString(`"X16`"),`n                    [`"kfps_morph_target_count`"] = morphTargets.Length,`n                    [`"kfps_morph_default_weights_verified`"] = false," `
    'GLB morph metadata insertion'
$writerText = Replace-ExactlyOnce $writerText `
    '                    primitives = new\[\] \{ new \{ attributes, indices = indexAccessor, mode = 4 \} \},\r?\n                    extras,' `
    "                    primitives = new[] { new { attributes, indices = indexAccessor, mode = 4, targets = morphTargets } },`n                    weights = Enumerable.Repeat(0.0f, morphTargets.Length).ToArray(),`n                    extras," `
    'GLB morph primitive insertion'
foreach ($required in @('targets = morphTargets', 'weights = Enumerable.Repeat(0.0f', 'kfps_morph_target_count')) {
    if (-not $writerText.Contains($required)) {
        throw "GlbWriter morph export insertion failed: $required"
    }
}
Set-Content -LiteralPath $glbWriter -Value $writerText -Encoding utf8NoBOM

Write-Host "Patched pinned KFPS headless exporter to ForzaTechStudio geometry semantics."
Write-Host "KFPS base: $kfpsCommit"
Write-Host "Program blob: $programBlob"
Write-Host "FTS reference: $ftsCommit"
Write-Host "Non-damage position morph targets: preserved with zero default weights"
