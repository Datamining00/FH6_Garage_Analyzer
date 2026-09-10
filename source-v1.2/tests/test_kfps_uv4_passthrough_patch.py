from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.patch_kfps_materialbin_diagnostic import _ensure_native_uv4_passthrough
from tools.patch_kfps_uv4_passthrough import PINNED_KFPS_COMMIT, patch


PROGRAM = '''
var uvChannelCount = geometry.UvChannels.Count(item =>
    item.Key is >= 0 and <= 3 && item.Value.Length == vertexCount);

private static Dictionary<int, Vector2[]> TransformUvChannels(ForzaGeometryData geometry, int vertexCount)
{
    foreach (var (channel, source) in geometry.UvChannels)
    {
        if (channel is < 0 or > 3 || source.Length != vertexCount)
            continue;
    }
}
'''

WRITER = '''
foreach (var (channel, values) in mesh.UvChannels.OrderBy(item => item.Key))
    attributes[$"TEXCOORD_{channel}"] = AddVector2Accessor(binary, bufferViews, accessors, values, 34962);
'''


class KfpsUv4PassthroughPatchTests(unittest.TestCase):
    def _fixture(self, temp: str) -> tuple[Path, Path, Path]:
        root = Path(temp)
        converter = root / "tools" / "livery" / "chassis-converter"
        converter.mkdir(parents=True)
        program = converter / "Program.cs"
        writer = converter / "GlbWriter.cs"
        program.write_text(PROGRAM, encoding="utf-8")
        writer.write_text(WRITER, encoding="utf-8")
        return root, program, writer

    def test_patch_extends_native_channel_range_without_synthesizing_uv4(self):
        self.assertEqual(PINNED_KFPS_COMMIT, "6f53ca3c584d78659d06d4b4a39561db67d79345")
        with tempfile.TemporaryDirectory() as temp:
            root, program, writer = self._fixture(temp)

            patch(root)

            patched = program.read_text(encoding="utf-8")
            self.assertIn("item.Key is >= 0 and <= 4", patched)
            self.assertIn("channel is < 0 or > 4", patched)
            self.assertNotIn("item.Key is >= 0 and <= 3", patched)
            self.assertNotIn("channel is < 0 or > 3", patched)
            self.assertNotIn("TEXCOORD_4", patched)
            self.assertEqual(writer.read_text(encoding="utf-8"), WRITER)

    def test_material_patch_ensures_uv4_when_workflow_omits_dedicated_patch(self):
        with tempfile.TemporaryDirectory() as temp:
            root, program, _ = self._fixture(temp)

            _ensure_native_uv4_passthrough(root, program)

            patched = program.read_text(encoding="utf-8")
            self.assertIn("item.Key is >= 0 and <= 4", patched)
            self.assertIn("channel is < 0 or > 4", patched)
            self.assertNotIn("item.Key is >= 0 and <= 3", patched)
            self.assertNotIn("channel is < 0 or > 3", patched)

    def test_material_patch_accepts_already_patched_uv4_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root, program, _ = self._fixture(temp)
            patch(root)
            before = program.read_bytes()

            _ensure_native_uv4_passthrough(root, program)

            self.assertEqual(program.read_bytes(), before)

    def test_material_patch_fails_closed_on_ambiguous_uv4_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root, program, _ = self._fixture(temp)
            program.write_text(PROGRAM.replace("<= 3", "<= 2"), encoding="utf-8")

            with self.assertRaises(RuntimeError):
                _ensure_native_uv4_passthrough(root, program)

    def test_patch_fails_closed_when_upstream_contract_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root, program, _ = self._fixture(temp)
            program.write_text(PROGRAM.replace("<= 3", "<= 2"), encoding="utf-8")
            with self.assertRaises(RuntimeError):
                patch(root)


if __name__ == "__main__":
    unittest.main()
