from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

from fh6garage.preview3d import kfps_render_backend as backend
from fh6garage.preview3d import livery_paint_runtime_patch as runtime_patch


@dataclass(frozen=True)
class _Result:
    source_path: Path
    output_dir: Path


class LiveryPaintRuntimePatchTests(unittest.TestCase):
    def setUp(self):
        self.original_render = backend.render_clivery_sections

    def tearDown(self):
        backend.render_clivery_sections = self.original_render

    def test_runtime_patch_writes_transient_diagnostic_without_changing_render_result_contract(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "C_livery"
            source.write_bytes(b"unchanged")
            out = root / "render"
            out.mkdir()
            result = _Result(source, out)
            logs: list[str] = []

            def fake_render(*args, **kwargs):
                return result

            backend.render_clivery_sections = fake_render
            report = {
                "format": "fh6_livery_paint_provenance_v1",
                "status": "paint_descriptor_parsed",
                "records": [{"finish_code": 7, "manufacturer_color_selector": 9}],
                "rendering_applied": False,
                "game_data_modified": False,
            }
            with patch.object(runtime_patch, "diagnose_livery_paint", return_value=report):
                self.assertTrue(runtime_patch.install_livery_paint_provenance_runtime_patch())
                wrapped = backend.render_clivery_sections
                returned = wrapped(source, output_root=out, log=logs.append)

            self.assertIs(returned, result)
            self.assertEqual(source.read_bytes(), b"unchanged")
            self.assertEqual(returned._fh6_paint_provenance, report)
            diagnostic = returned._fh6_paint_provenance_path
            self.assertEqual(diagnostic.name, "paint_provenance.json")
            stored = json.loads(diagnostic.read_text(encoding="utf-8"))
            self.assertEqual(stored, report)
            self.assertTrue(any("Paint P1 provenance" in line for line in logs))

    def test_diagnostic_failure_is_nonfatal_and_does_not_replace_render_output(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            result = _Result(root / "C_livery", root)
            backend.render_clivery_sections = lambda *args, **kwargs: result
            with patch.object(runtime_patch, "diagnose_livery_paint", side_effect=RuntimeError("bad descriptor")):
                self.assertTrue(runtime_patch.install_livery_paint_provenance_runtime_patch())
                returned = backend.render_clivery_sections(result.source_path)
            self.assertIs(returned, result)
            self.assertEqual(returned._fh6_paint_provenance["status"], "paint_provenance_unresolved")
            self.assertFalse(returned._fh6_paint_provenance["rendering_applied"])
            self.assertIsNone(returned._fh6_paint_provenance_path)

    def test_installer_is_idempotent(self):
        backend.render_clivery_sections = lambda *args, **kwargs: _Result(Path("C_livery"), Path("."))
        self.assertTrue(runtime_patch.install_livery_paint_provenance_runtime_patch())
        first = backend.render_clivery_sections
        self.assertTrue(runtime_patch.install_livery_paint_provenance_runtime_patch())
        self.assertIs(backend.render_clivery_sections, first)


if __name__ == "__main__":
    unittest.main()
