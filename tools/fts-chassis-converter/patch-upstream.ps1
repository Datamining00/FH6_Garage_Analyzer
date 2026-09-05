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

if (-not (Test-Path $program)) {
    throw "Pinned KFPS Program.cs not found: $program"
}
if (-not (Test-Path $modelImporter)) {
    throw "Vendored ForzaTechStudio ModelImporter.cs not found: $modelImporter"
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

Write-Host "Patched pinned KFPS headless exporter to ForzaTechStudio geometry semantics."
Write-Host "KFPS base: $kfpsCommit"
Write-Host "Program blob: $programBlob"
Write-Host "FTS reference: $ftsCommit"
