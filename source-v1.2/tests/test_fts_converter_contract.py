from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "tools" / "fts-chassis-converter" / "patch-upstream.ps1"
WORKFLOW = ROOT / ".github" / "workflows" / "build-fts-chassis-converter.yml"


def test_fts_converter_patch_is_pinned_and_structural():
    text = PATCH.read_text(encoding="utf-8")
    assert "6f53ca3c584d78659d06d4b4a39561db67d79345" in text
    assert "4f373c5fb192551ce5249e320dd79b1399b693ca" in text
    assert "geometry.GetRotationMatrix()" in text
    assert "raw.X * mesh.PositionScale.X" in text
    assert "scaled.X + mesh.PositionTranslate.X" in text
    assert "geometry.BoneTransform" in text
    assert "instanceTransform" in text
    assert "fh6_fts_chassis_conversion_v1" in text
    assert "lateral_translation_v1" not in text


def test_fts_converter_workflow_builds_patched_source():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "dotnet publish" in text
    assert "patch-upstream.ps1" in text
    assert "FH6.FtsChassisConverter.exe" in text
    assert "contents: write" in text
