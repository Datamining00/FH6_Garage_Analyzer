from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any

from .wheel_morph_helper import (
    WheelMorphHelperError,
    verified_bundled_wheel_morph_helper,
)


MATERIALBIN_REFERENCE_HELPER_FORMAT = "fh6_materialbin_reference_diagnostic_v1"
MATERIALBIN_REFERENCE_HELPER_REVISION = 1


class MaterialbinReferenceHelperError(RuntimeError):
    pass


def _explicit_game_data_unmodified(report: dict[str, Any]) -> bool:
    """Accept the helper's native snake_case safety field and legacy camelCase only.

    The patched KFPS helper serializes with JsonNamingPolicy.SnakeCaseLower, so the
    C# ``GameDataModified`` field is emitted as ``game_data_modified``.  Keep the
    older camelCase spelling for compatibility, but require an explicit boolean
    false from either spelling; absence, null, or true remains fail-closed.
    """
    if "game_data_modified" in report:
        return report.get("game_data_modified") is False
    if "gameDataModified" in report:
        return report.get("gameDataModified") is False
    return False


def diagnose_materialbin_references(
    materialbin_path: str | Path,
    *,
    helper_path: str | Path | None = None,
) -> dict[str, Any]:
    """Parse one materialbin with the SHA-verified patched KFPS/ForzaTools helper."""
    source = Path(materialbin_path).expanduser().resolve()
    if not source.is_file():
        raise MaterialbinReferenceHelperError(f"Materialbin input does not exist: {source}")

    if helper_path is None:
        try:
            helper = verified_bundled_wheel_morph_helper()
        except WheelMorphHelperError as exc:
            raise MaterialbinReferenceHelperError(str(exc)) from exc
        if helper is None:
            raise MaterialbinReferenceHelperError(
                "The SHA-verified KFPS helper is unavailable for materialbin diagnostics."
            )
    else:
        helper = Path(helper_path).expanduser().resolve()
        if not helper.is_file():
            raise MaterialbinReferenceHelperError(f"Materialbin helper does not exist: {helper}")

    try:
        completed = subprocess.run(
            [str(helper), "--diagnose-materialbin", str(source)],
            cwd=str(source.parent),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise MaterialbinReferenceHelperError(
            f"Materialbin helper could not be executed: {type(exc).__name__}: {exc}"
        ) from exc

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise MaterialbinReferenceHelperError(
            f"Materialbin helper exited with code {completed.returncode}: {detail}"
        )
    payload = (completed.stdout or "").strip()
    if not payload:
        raise MaterialbinReferenceHelperError("Materialbin helper returned no JSON diagnostic.")
    try:
        report = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise MaterialbinReferenceHelperError(
            f"Materialbin helper returned invalid JSON: {exc}"
        ) from exc
    if not isinstance(report, dict):
        raise MaterialbinReferenceHelperError("Materialbin helper JSON root is not an object.")
    if report.get("format") != MATERIALBIN_REFERENCE_HELPER_FORMAT:
        raise MaterialbinReferenceHelperError(
            f"Unexpected materialbin helper format: {report.get('format')!r}"
        )
    if report.get("revision") != MATERIALBIN_REFERENCE_HELPER_REVISION:
        raise MaterialbinReferenceHelperError(
            f"Unexpected materialbin helper revision: {report.get('revision')!r}"
        )
    if not _explicit_game_data_unmodified(report):
        raise MaterialbinReferenceHelperError(
            "Materialbin helper did not explicitly report game_data_modified=false."
        )
    return report
