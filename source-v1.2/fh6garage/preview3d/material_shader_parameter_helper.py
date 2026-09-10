from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any

from .wheel_morph_helper import (
    WheelMorphHelperError,
    verified_bundled_wheel_morph_helper,
)


MATERIAL_SHADER_PARAMETER_HELPER_FORMAT = "fh6_material_shader_parameter_diagnostic_v1"
MATERIAL_SHADER_PARAMETER_HELPER_REVISION = 1
_MAX_TRANSPORT_DIAGNOSTIC_LINES = 32
_MAX_TRANSPORT_DIAGNOSTIC_CHARS = 1000


class MaterialShaderParameterHelperError(RuntimeError):
    pass


def _explicit_false(report: dict[str, Any], snake: str, camel: str) -> bool:
    if snake in report:
        return report.get(snake) is False
    if camel in report:
        return report.get(camel) is False
    return False


def _diagnostic_lines(text: str | None) -> list[str]:
    lines: list[str] = []
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if len(line) > _MAX_TRANSPORT_DIAGNOSTIC_CHARS:
            line = line[:_MAX_TRANSPORT_DIAGNOSTIC_CHARS] + "..."
        lines.append(line)
        if len(lines) >= _MAX_TRANSPORT_DIAGNOSTIC_LINES:
            break
    return lines


def _decode_helper_stdout(payload: str) -> tuple[dict[str, Any], list[str]]:
    """Decode one trusted helper JSON object while preserving prefixed diagnostics.

    ForzaTools Bundle.Load writes recoverable per-blob parse diagnostics to stdout.
    The patched helper then writes its JSON report to the same stream.  Accept that
    transport shape only when there is exactly one matching helper JSON object at
    the end of stdout; arbitrary suffix output or ambiguous matching objects remain
    fail-closed.
    """
    clean = payload.lstrip("\ufeff")
    try:
        direct = json.loads(clean)
    except json.JSONDecodeError as direct_error:
        decoder = json.JSONDecoder()
        matches: list[tuple[int, dict[str, Any]]] = []
        for index, char in enumerate(clean):
            if char != "{":
                continue
            try:
                value, end = decoder.raw_decode(clean, index)
            except json.JSONDecodeError:
                continue
            if clean[end:].strip():
                continue
            if (
                isinstance(value, dict)
                and value.get("format") == MATERIAL_SHADER_PARAMETER_HELPER_FORMAT
            ):
                matches.append((index, value))
        if len(matches) != 1:
            raise MaterialShaderParameterHelperError(
                "Material/shader parameter helper returned invalid JSON: "
                f"{direct_error}; matching terminal helper reports={len(matches)}"
            ) from direct_error
        start, report = matches[0]
        diagnostics = _diagnostic_lines(clean[:start])
        return report, diagnostics

    if not isinstance(direct, dict):
        raise MaterialShaderParameterHelperError(
            "Material/shader parameter helper JSON root is not an object."
        )
    return direct, []


def diagnose_material_shader_parameters(
    materialbin_path: str | Path,
    shaderbin_path: str | Path,
    *,
    helper_path: str | Path | None = None,
) -> dict[str, Any]:
    """Decode and compose one exact materialbin/shaderbin parameter pair read-only.

    The patched KFPS/ForzaTools helper follows the same composition key used by
    ForzaTechStudio's Materials & Shaders workstation: NameHash + parameter type,
    with the first parameter per source retained and the material override taking
    precedence over the linked shader default.
    """
    material = Path(materialbin_path).expanduser().resolve()
    shader = Path(shaderbin_path).expanduser().resolve()
    if not material.is_file():
        raise MaterialShaderParameterHelperError(
            f"Materialbin input does not exist: {material}"
        )
    if not shader.is_file():
        raise MaterialShaderParameterHelperError(
            f"Shaderbin input does not exist: {shader}"
        )

    if helper_path is None:
        try:
            helper = verified_bundled_wheel_morph_helper()
        except WheelMorphHelperError as exc:
            raise MaterialShaderParameterHelperError(str(exc)) from exc
        if helper is None:
            raise MaterialShaderParameterHelperError(
                "The SHA-verified KFPS helper is unavailable for material/shader parameter diagnostics."
            )
    else:
        helper = Path(helper_path).expanduser().resolve()
        if not helper.is_file():
            raise MaterialShaderParameterHelperError(
                f"Material/shader parameter helper does not exist: {helper}"
            )

    try:
        completed = subprocess.run(
            [
                str(helper),
                "--diagnose-material-shader-parameters",
                str(material),
                str(shader),
            ],
            cwd=str(material.parent),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise MaterialShaderParameterHelperError(
            f"Material/shader parameter helper could not be executed: {type(exc).__name__}: {exc}"
        ) from exc

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise MaterialShaderParameterHelperError(
            f"Material/shader parameter helper exited with code {completed.returncode}: {detail}"
        )
    payload = (completed.stdout or "").strip()
    if not payload:
        raise MaterialShaderParameterHelperError(
            "Material/shader parameter helper returned no JSON diagnostic."
        )

    report, stdout_diagnostics = _decode_helper_stdout(payload)
    if report.get("format") != MATERIAL_SHADER_PARAMETER_HELPER_FORMAT:
        raise MaterialShaderParameterHelperError(
            f"Unexpected material/shader parameter helper format: {report.get('format')!r}"
        )
    if report.get("revision") != MATERIAL_SHADER_PARAMETER_HELPER_REVISION:
        raise MaterialShaderParameterHelperError(
            f"Unexpected material/shader parameter helper revision: {report.get('revision')!r}"
        )
    if not _explicit_false(report, "game_data_modified", "gameDataModified"):
        raise MaterialShaderParameterHelperError(
            "Material/shader parameter helper did not explicitly report game_data_modified=false."
        )
    if not _explicit_false(report, "rendering_enabled", "renderingEnabled"):
        raise MaterialShaderParameterHelperError(
            "Material/shader parameter helper did not explicitly report rendering_enabled=false."
        )

    stderr_diagnostics = _diagnostic_lines(completed.stderr)
    if stdout_diagnostics or stderr_diagnostics:
        report = dict(report)
        if stdout_diagnostics:
            report["stdout_diagnostics"] = stdout_diagnostics
        if stderr_diagnostics:
            report["stderr_diagnostics"] = stderr_diagnostics
    return report
