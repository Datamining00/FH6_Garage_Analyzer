from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fh6garage.preview3d.material_shader_parameter_helper import (
    MaterialShaderParameterHelperError,
    diagnose_material_shader_parameters,
)


class _Completed:
    def __init__(
        self,
        payload: dict | None = None,
        *,
        stdout: str | None = None,
        stderr: str = "",
        returncode: int = 0,
    ):
        self.returncode = returncode
        self.stdout = json.dumps(payload) if stdout is None else stdout
        self.stderr = stderr


class MaterialShaderParameterHelperTests(unittest.TestCase):
    def _paths(self, root: Path) -> tuple[Path, Path, Path]:
        material = root / "paint.materialbin"
        shader = root / "paint.shaderbin"
        helper = root / "Kfps.ChassisConverter.WheelMorph.exe"
        material.write_bytes(b"material")
        shader.write_bytes(b"shader")
        helper.write_bytes(b"helper")
        return material, shader, helper

    @staticmethod
    def _payload() -> dict:
        return {
            "format": "fh6_material_shader_parameter_diagnostic_v1",
            "revision": 1,
            "status": "material_shader_parameters_composed",
            "rendering_enabled": False,
            "game_data_modified": False,
            "effective_parameters": [],
        }

    def test_invokes_exact_read_only_material_shader_mode(self):
        with tempfile.TemporaryDirectory() as temp:
            material, shader, helper = self._paths(Path(temp))
            payload = self._payload()
            with patch(
                "fh6garage.preview3d.material_shader_parameter_helper.subprocess.run",
                return_value=_Completed(payload),
            ) as run:
                report = diagnose_material_shader_parameters(
                    material,
                    shader,
                    helper_path=helper,
                )

            self.assertEqual(report["status"], "material_shader_parameters_composed")
            command = run.call_args.args[0]
            self.assertEqual(command[0], str(helper.resolve()))
            self.assertEqual(command[1], "--diagnose-material-shader-parameters")
            self.assertEqual(command[2], str(material.resolve()))
            self.assertEqual(command[3], str(shader.resolve()))

    def test_accepts_camel_case_csharp_safety_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            material, shader, helper = self._paths(Path(temp))
            payload = {
                "format": "fh6_material_shader_parameter_diagnostic_v1",
                "revision": 1,
                "status": "material_shader_parameters_composed",
                "renderingEnabled": False,
                "gameDataModified": False,
            }
            with patch(
                "fh6garage.preview3d.material_shader_parameter_helper.subprocess.run",
                return_value=_Completed(payload),
            ):
                report = diagnose_material_shader_parameters(
                    material,
                    shader,
                    helper_path=helper,
                )
            self.assertFalse(report["renderingEnabled"])
            self.assertFalse(report["gameDataModified"])

    def test_accepts_terminal_json_after_forzatools_bundle_stdout_diagnostics(self):
        with tempfile.TemporaryDirectory() as temp:
            material, shader, helper = self._paths(Path(temp))
            payload = self._payload()
            stdout = (
                "Error reading blob at index 2: unsupported metadata\n"
                "Error reading blob at index 7: unsupported metadata\n"
                + json.dumps(payload)
                + "\n"
            )
            with patch(
                "fh6garage.preview3d.material_shader_parameter_helper.subprocess.run",
                return_value=_Completed(stdout=stdout, stderr="helper warning\n"),
            ):
                report = diagnose_material_shader_parameters(
                    material,
                    shader,
                    helper_path=helper,
                )

            self.assertEqual(report["status"], "material_shader_parameters_composed")
            self.assertEqual(
                report["stdout_diagnostics"],
                [
                    "Error reading blob at index 2: unsupported metadata",
                    "Error reading blob at index 7: unsupported metadata",
                ],
            )
            self.assertEqual(report["stderr_diagnostics"], ["helper warning"])

    def test_rejects_terminal_json_with_non_whitespace_suffix(self):
        with tempfile.TemporaryDirectory() as temp:
            material, shader, helper = self._paths(Path(temp))
            stdout = "prefix\n" + json.dumps(self._payload()) + "\ntrailing-noise"
            with patch(
                "fh6garage.preview3d.material_shader_parameter_helper.subprocess.run",
                return_value=_Completed(stdout=stdout),
            ):
                with self.assertRaises(MaterialShaderParameterHelperError):
                    diagnose_material_shader_parameters(
                        material,
                        shader,
                        helper_path=helper,
                    )

    def test_rejects_prefixed_output_without_matching_terminal_helper_json(self):
        with tempfile.TemporaryDirectory() as temp:
            material, shader, helper = self._paths(Path(temp))
            stdout = "Error reading blob at index 1: bad blob\n{\"format\":\"other\"}\n"
            with patch(
                "fh6garage.preview3d.material_shader_parameter_helper.subprocess.run",
                return_value=_Completed(stdout=stdout),
            ):
                with self.assertRaises(MaterialShaderParameterHelperError):
                    diagnose_material_shader_parameters(
                        material,
                        shader,
                        helper_path=helper,
                    )

    def test_rejects_missing_or_true_safety_contracts(self):
        cases = [
            {
                "format": "fh6_material_shader_parameter_diagnostic_v1",
                "revision": 1,
                "status": "material_shader_parameters_composed",
                "rendering_enabled": False,
            },
            {
                "format": "fh6_material_shader_parameter_diagnostic_v1",
                "revision": 1,
                "status": "material_shader_parameters_composed",
                "rendering_enabled": False,
                "game_data_modified": True,
            },
            {
                "format": "fh6_material_shader_parameter_diagnostic_v1",
                "revision": 1,
                "status": "material_shader_parameters_composed",
                "game_data_modified": False,
                "rendering_enabled": True,
            },
        ]
        with tempfile.TemporaryDirectory() as temp:
            material, shader, helper = self._paths(Path(temp))
            for payload in cases:
                with self.subTest(payload=payload):
                    with patch(
                        "fh6garage.preview3d.material_shader_parameter_helper.subprocess.run",
                        return_value=_Completed(payload),
                    ):
                        with self.assertRaises(MaterialShaderParameterHelperError):
                            diagnose_material_shader_parameters(
                                material,
                                shader,
                                helper_path=helper,
                            )


if __name__ == "__main__":
    unittest.main()
