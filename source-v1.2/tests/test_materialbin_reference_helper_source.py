from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from fh6garage.preview3d.materialbin_reference_helper import (
    MaterialbinReferenceHelperError,
    diagnose_materialbin_references,
)


# Workflow sentinel: changes here trigger the packaged P3F validation workflow;
# the full regression discovery in that workflow also executes test_p3d_breakdown.py.
ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "tools" / "kfps_wheel_morph" / "MaterialbinReferenceDiagnostic.cs"
PATCHER = ROOT / "tools" / "patch_kfps_materialbin_diagnostic.py"


class MaterialbinReferenceHelperSourceTests(unittest.TestCase):
    def test_helper_preserves_pinned_fts_reference_order_without_path_heuristics(self):
        text = HELPER.read_text(encoding="utf-8")
        matl = text.index("foreach (var matl in bundle.Blobs.OfType<MatLBlob>())")
        path = text.index('AddMatlReference(references, ref order, "Path", matl.Path);', matl)
        path_v11 = text.index('AddMatlReference(references, ref order, "PathV1_1", matl.PathV1_1);', path)
        path_v12 = text.index('AddMatlReference(references, ref order, "PathV1_2", matl.PathV1_2);', path_v11)
        shader = text.index("foreach (var blob in bundle.Blobs)", path_v12)
        texture = text.index("parameter.Type != ShaderParameterType.Texture2D", shader)
        self.assertLess(matl, path)
        self.assertLess(path, path_v11)
        self.assertLess(path_v11, path_v12)
        self.assertLess(path_v12, shader)
        self.assertLess(shader, texture)
        self.assertIn('$"{parameter.NameHash:X8}"', text)
        self.assertIn('$"{texture.PathHash:X8}"', text)
        self.assertIn("bundle.Load(stream)", text)
        self.assertIn("bool GameDataModified", text)
        self.assertIn("false);", text)
        self.assertNotIn("Contains(\"paint\"", text)
        self.assertNotIn("GetFileName", text)
        self.assertNotIn("EndsWith(\"carpaint\"", text)

    def test_followup_patcher_is_modular_and_requires_established_decode_contract(self):
        text = PATCHER.read_text(encoding="utf-8")
        self.assertIn("6f53ca3c584d78659d06d4b4a39561db67d79345", text)
        self.assertIn("--decode-swatchbin", text)
        self.assertIn("--diagnose-materialbin", text)
        self.assertIn("MaterialbinReferenceRuntime.Diagnose", text)
        self.assertIn("Expected exactly one established --decode-swatchbin CLI contract", text)
        self.assertIn("shutil.copy2", text)

    def test_followup_patcher_carries_exact_fh6_v34_sampler_alignment_contract(self):
        text = PATCHER.read_text(encoding="utf-8")
        self.assertIn("MaterialShaderParameterBlob.cs", text)
        self.assertIn("FH6 v3.4 sampler records observed in real shaderbin data", text)
        self.assertIn("VersionMajor == 3 && VersionMinor == 4", text)
        self.assertIn("_ = bs.ReadUInt32();", text)
        self.assertIn("expected exactly one pinned occurrence", text)

    @staticmethod
    def _diagnose_report(safety_field: dict) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "paint.materialbin"
            helper = root / "helper.exe"
            source.write_bytes(b"material")
            helper.write_bytes(b"helper")
            report = {
                "format": "fh6_materialbin_reference_diagnostic_v1",
                "revision": 1,
                "status": "materialbin_references_parsed",
                "references": [],
                **safety_field,
            }
            completed = subprocess.CompletedProcess(
                args=[str(helper), "--diagnose-materialbin", str(source)],
                returncode=0,
                stdout=json.dumps(report),
                stderr="",
            )
            with mock.patch(
                "fh6garage.preview3d.materialbin_reference_helper.subprocess.run",
                return_value=completed,
            ):
                return diagnose_materialbin_references(source, helper_path=helper)

    def test_runtime_accepts_native_snake_case_read_only_field(self):
        report = self._diagnose_report({"game_data_modified": False})
        self.assertIs(report["game_data_modified"], False)

    def test_runtime_keeps_legacy_camel_case_read_only_compatibility(self):
        report = self._diagnose_report({"gameDataModified": False})
        self.assertIs(report["gameDataModified"], False)

    def test_runtime_rejects_missing_read_only_field(self):
        with self.assertRaisesRegex(
            MaterialbinReferenceHelperError,
            "explicitly report game_data_modified=false",
        ):
            self._diagnose_report({})

    def test_runtime_rejects_true_read_only_field(self):
        with self.assertRaisesRegex(
            MaterialbinReferenceHelperError,
            "explicitly report game_data_modified=false",
        ):
            self._diagnose_report({"game_data_modified": True})

    def test_native_snake_case_field_takes_precedence_if_both_are_present(self):
        with self.assertRaisesRegex(
            MaterialbinReferenceHelperError,
            "explicitly report game_data_modified=false",
        ):
            self._diagnose_report(
                {"game_data_modified": True, "gameDataModified": False}
            )


if __name__ == "__main__":
    unittest.main()
