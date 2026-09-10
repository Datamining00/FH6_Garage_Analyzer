from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Sequence

from ..scanner import SaveLayoutError, resolve_layout
from .chassis_converter import ChassisConverterError, convert_vehicle
from .livery_paint_provenance import (
    LiveryPaintProvenanceError,
    diagnose_livery_paint,
)
from .manufacturer_colors import CUSTOM_COLOR_SELECTOR
from .manufacturer_materialbin_diagnostics import trace_manufacturer_materialbin_payloads
from .manufacturer_overlay_diagnostics import diagnose_manufacturer_overlay
from .vehicle_index import (
    VehicleAsset,
    VehicleIndexError,
    load_vehicle_asset,
    preferred_carbin_entry,
)
from .wheel_morph_helper import (
    WHEEL_MORPH_HELPER_REVISION,
    WHEEL_MORPH_HELPER_SHA256,
    WheelMorphHelperError,
    verified_bundled_wheel_morph_helper,
)


MANUFACTURER_MATERIALBIN_CLI_FORMAT = "fh6_manufacturer_materialbin_cli_v1"
MANUFACTURER_MATERIALBIN_CLI_REVISION = 2

_LIVERY_CONTAINER_RE = re.compile(
    r"^(?P<kind>BaseLivery|SoulBoundLivery|Livery)_(?P<car_id>\d+)(?:_|$)",
    re.IGNORECASE,
)
_LIVERY_KIND_PRIORITY = {
    "baselivery": 1,
    "soulboundlivery": 2,
    "livery": 3,
}


class P3FAutoInputError(RuntimeError):
    pass


def _existing_file(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"Input file does not exist: {path}")
    return path


def _existing_directory(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_dir():
        raise argparse.ArgumentTypeError(f"Input directory does not exist: {path}")
    return path


def _validation_status(report: dict) -> str:
    if report.get("status") != "manufacturer_materialbin_payloads_diagnosed":
        return "diagnostic_unavailable"
    if int(report.get("exact_resolved_count") or 0) > 0:
        return "exact_swatch_chain_resolved"
    if int(report.get("exact_shader_resolved_count") or 0) > 0:
        return "exact_material_shader_chain_resolved"
    if int(report.get("candidate_count") or 0) == 0:
        return "no_materialbin_candidate"
    if int(report.get("blocked_count") or 0) > 0:
        return "materialbin_chain_blocked"
    return "materialbin_chain_unresolved"


def _emit_error(message: str) -> None:
    stream = getattr(sys, "stderr", None)
    if stream is not None:
        print(message, file=stream)


def _write_result(result: dict[str, Any], output: Path | None) -> None:
    payload = json.dumps(result, indent=2, ensure_ascii=False)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload + "\n", encoding="utf-8")
    stream = getattr(sys, "stdout", None)
    if stream is not None:
        print(payload, file=stream)


def _base_cli_report(status: str) -> dict[str, Any]:
    return {
        "cli_format": MANUFACTURER_MATERIALBIN_CLI_FORMAT,
        "cli_revision": MANUFACTURER_MATERIALBIN_CLI_REVISION,
        "status": status,
        "helper_revision": WHEEL_MORPH_HELPER_REVISION,
        "helper_sha256": WHEEL_MORPH_HELPER_SHA256,
        "rendering_enabled": False,
        "rendering_applied": False,
        "game_data_modified": False,
    }


def _persisted_save_path() -> Path | None:
    """Read the same path-only setting used by the normal FH6 Assistant UI."""
    env = str(os.environ.get("FH6_SAVE_PATH") or "").strip()
    if env:
        path = Path(env).expanduser()
        if path.is_dir():
            return path.resolve()

    try:
        from PySide6.QtCore import QSettings
    except Exception:
        return None

    try:
        value = QSettings("LocalOnly", "FH6 Assistant").value(
            "last_save_path", "", str
        )
    except Exception:
        return None
    raw = str(value or "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path.resolve() if path.is_dir() else None


def _resolve_save_path(explicit: Path | None) -> tuple[Path, Path, str, str]:
    """Return (selected path, ContainersRoot, active version, provenance)."""
    if explicit is not None:
        candidate = explicit.expanduser().resolve()
        source = "explicit_save_root"
        try:
            _, containers_root, active_version = resolve_layout(candidate)
        except SaveLayoutError as exc:
            raise P3FAutoInputError(
                f"Explicit FH6 save path is not a supported save layout: {candidate}: {exc}"
            ) from exc
        return candidate, containers_root.resolve(), active_version, source

    candidate = _persisted_save_path()
    if candidate is None:
        raise P3FAutoInputError(
            "No FH6 save path is available for automatic C_livery selection. "
            "Open FH6 Assistant once and select the save folder, set FH6_SAVE_PATH, "
            "or pass --save-root."
        )
    try:
        _, containers_root, active_version = resolve_layout(candidate)
    except SaveLayoutError as exc:
        raise P3FAutoInputError(
            f"The persisted FH6 save path is no longer a supported save layout: {candidate}: {exc}"
        ) from exc
    source = (
        "environment_FH6_SAVE_PATH"
        if str(os.environ.get("FH6_SAVE_PATH") or "").strip()
        else "qsettings_last_save_path"
    )
    return candidate, containers_root.resolve(), active_version, source


def _file_mtime_ns(path: Path) -> int:
    try:
        return int(path.stat().st_mtime_ns)
    except OSError:
        return 0


def _paint_candidate_summary(path: Path, kind: str, car_id: int) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "path": str(path.resolve()),
        "container": path.parent.name,
        "kind": kind,
        "car_id": car_id,
        "parsed_car_id": None,
        "status": "paint_provenance_unavailable",
        "manufacturer_ready": False,
        "manufacturer_selector_count": 0,
        "custom_primary_active": False,
        "mtime_ns": _file_mtime_ns(path),
        "error": None,
    }
    try:
        report = diagnose_livery_paint(path)
    except (OSError, ValueError, LiveryPaintProvenanceError) as exc:
        summary["error"] = f"{type(exc).__name__}: {exc}"
        return summary

    summary["status"] = str(report.get("status") or "")
    try:
        summary["parsed_car_id"] = int(report.get("car_id"))
    except (TypeError, ValueError):
        summary["parsed_car_id"] = None
    records = [row for row in (report.get("records") or []) if isinstance(row, dict)]
    custom_primary_active = any(bool(row.get("primary_color_enabled")) for row in records)
    manufacturer_selector_count = 0
    for row in records:
        try:
            selector = int(row.get("manufacturer_color_selector"))
        except (TypeError, ValueError):
            continue
        if selector != CUSTOM_COLOR_SELECTOR:
            manufacturer_selector_count += 1
    exact_car = summary["parsed_car_id"] in (None, car_id)
    parsed = summary["status"] == "paint_descriptor_parsed"
    summary["custom_primary_active"] = custom_primary_active
    summary["manufacturer_selector_count"] = manufacturer_selector_count
    summary["manufacturer_ready"] = bool(
        exact_car
        and parsed
        and not custom_primary_active
        and manufacturer_selector_count > 0
    )
    return summary


def _auto_select_paint(
    car_id: int,
    save_root: Path | None,
) -> tuple[Path, dict[str, Any]]:
    selected_save, containers_root, active_version, save_source = _resolve_save_path(save_root)
    candidates: list[dict[str, Any]] = []

    try:
        containers = sorted(
            (path for path in containers_root.iterdir() if path.is_dir()),
            key=lambda path: path.name.casefold(),
        )
    except OSError as exc:
        raise P3FAutoInputError(
            f"Could not enumerate FH6 save containers: {containers_root}: {exc}"
        ) from exc

    for container in containers:
        match = _LIVERY_CONTAINER_RE.match(container.name)
        if match is None:
            continue
        try:
            container_car_id = int(match.group("car_id"))
        except ValueError:
            continue
        if container_car_id != car_id:
            continue
        paint = container / "C_livery"
        if not paint.is_file():
            continue
        candidates.append(
            _paint_candidate_summary(
                paint,
                match.group("kind"),
                car_id,
            )
        )

    matching = [
        item
        for item in candidates
        if item.get("parsed_car_id") in (None, car_id)
        and item.get("status") == "paint_descriptor_parsed"
    ]
    if not matching:
        detail = "; ".join(
            f"{Path(str(item.get('path'))).parent.name}: {item.get('status')}"
            for item in candidates[:8]
        )
        if not detail:
            detail = "no matching livery containers were found"
        raise P3FAutoInputError(
            f"No parseable C_livery for Car ID {car_id} was found under "
            f"{containers_root}. {detail}"
        )

    def rank(item: dict[str, Any]) -> tuple[int, int, int, str]:
        kind_key = str(item.get("kind") or "").casefold()
        return (
            1 if item.get("manufacturer_ready") else 0,
            _LIVERY_KIND_PRIORITY.get(kind_key, 0),
            int(item.get("mtime_ns") or 0),
            str(item.get("container") or "").casefold(),
        )

    matching.sort(key=rank, reverse=True)
    selected = matching[0]
    paint_path = Path(str(selected["path"])).resolve()
    ready_count = sum(1 for item in matching if item.get("manufacturer_ready"))
    selection_reason = (
        "manufacturer_ready_then_kind_then_newest"
        if ready_count
        else "parseable_matching_car_then_kind_then_newest"
    )
    metadata = {
        "mode": "automatic_car_id_match",
        "save_path": str(selected_save),
        "save_path_source": save_source,
        "containers_root": str(containers_root),
        "active_version": active_version,
        "car_id": car_id,
        "candidate_count": len(candidates),
        "parseable_matching_count": len(matching),
        "manufacturer_ready_count": ready_count,
        "selection_reason": selection_reason,
        "selected_container": selected.get("container"),
        "selected_kind": selected.get("kind"),
        "selected_paint": str(paint_path),
        "selected_manufacturer_ready": bool(selected.get("manufacturer_ready")),
        "selected_mtime_ns": int(selected.get("mtime_ns") or 0),
        "game_data_modified": False,
    }
    return paint_path, metadata


def _auto_generate_glb(
    asset: VehicleAsset,
    cache: Path,
) -> tuple[Path, dict[str, Any]]:
    carbin_entry = preferred_carbin_entry(asset)
    if carbin_entry is None:
        if not asset.carbin_entries:
            raise P3FAutoInputError(
                f"Vehicle archive {asset.archive_name} has no .carbin scene."
            )
        raise P3FAutoInputError(
            f"Vehicle archive {asset.archive_name} has multiple ambiguous .carbin scenes; "
            "automatic P3F preparation will not guess a scene."
        )

    try:
        helper = verified_bundled_wheel_morph_helper()
    except WheelMorphHelperError as exc:
        raise P3FAutoInputError(
            f"The packaged KFPS helper failed integrity verification: {exc}"
        ) from exc
    if helper is None:
        raise P3FAutoInputError(
            "The SHA-verified packaged KFPS helper is unavailable for automatic GLB generation."
        )

    work_root = cache / "AutoInputs" / f"car_{asset.car_id}_{asset.model_code}"
    try:
        converted = convert_vehicle(
            asset,
            carbin_entry=carbin_entry,
            work_root=work_root,
            converter_override=helper,
        )
    except (OSError, ValueError, ChassisConverterError) as exc:
        raise P3FAutoInputError(
            f"Automatic GLB generation failed for Car ID {asset.car_id}: {exc}"
        ) from exc

    glb = Path(converted.output_path).expanduser().resolve()
    if not glb.is_file():
        raise P3FAutoInputError(
            f"Automatic GLB generation returned no usable output: {glb}"
        )
    metadata = {
        "mode": "automatic_vehicle_zip_conversion",
        "car_id": asset.car_id,
        "model_code": asset.model_code,
        "carbin_entry": carbin_entry,
        "generated_glb": str(glb),
        "helper_path": str(helper),
        "helper_revision": WHEEL_MORPH_HELPER_REVISION,
        "conversion_status": str(
            (converted.diagnostics or {}).get("status")
            or (converted.diagnostics or {}).get("scene_assembled")
            or "completed"
        ),
        "game_data_modified": False,
    }
    return glb, metadata


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only Paint P3F diagnostic: follow P3D-exact manufacturer .materialbin entries "
            "through exact material/shader references and any exact native swatchbin Texture2D reference. "
            "When --glb and/or --paint are omitted, the packaged diagnostic creates the GLB "
            "from --vehicle and resolves a matching C_livery from the saved FH6 save path."
        )
    )
    parser.add_argument("--self-check", action="store_true", help="Verify the packaged P3F module/helper contract only")
    parser.add_argument("--glb", type=_existing_file, help="Optional prebuilt KFPS GLB; omitted = generate from --vehicle")
    parser.add_argument("--paint", type=_existing_file, help="Optional C_livery; omitted = auto-resolve by vehicle Car ID")
    parser.add_argument("--vehicle", type=_existing_file, help="Selected FH6 vehicle ZIP")
    parser.add_argument("--save-root", type=_existing_directory, help="Optional FH6 save root override for automatic C_livery resolution")
    parser.add_argument("--cache", type=Path, help="Writable diagnostic cache root outside FH6 data")
    parser.add_argument("--output", type=Path, help="Optional diagnostic JSON output path")
    return parser


def _run_self_check(output: Path | None) -> int:
    result = _base_cli_report("packaged_p3f_self_check_failed")
    result["validation_status"] = "packaged_contract_unavailable"
    try:
        helper = verified_bundled_wheel_morph_helper()
    except WheelMorphHelperError as exc:
        result["detail"] = str(exc)
        _write_result(result, output)
        return 4
    if helper is None:
        result["detail"] = "The SHA-verified bundled KFPS helper is unavailable."
        _write_result(result, output)
        return 4
    result["status"] = "packaged_p3f_self_check_passed"
    result["validation_status"] = "packaged_contract_ready"
    result["verified_helper"] = str(helper)
    _write_result(result, output)
    return 0


def run_manufacturer_materialbin_diagnostic(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    output = args.output.expanduser().resolve() if args.output is not None else None

    if args.self_check:
        return _run_self_check(output)

    if args.vehicle is None or args.cache is None:
        _emit_error("--vehicle and --cache are required unless --self-check is used.")
        return 2

    vehicle = args.vehicle.resolve()
    cache = args.cache.expanduser().resolve()
    glb = args.glb.resolve() if args.glb is not None else None
    paint = args.paint.resolve() if args.paint is not None else None
    auto_report: dict[str, Any] = {
        "glb_mode": "explicit" if glb is not None else "automatic",
        "paint_mode": "explicit" if paint is not None else "automatic",
        "game_data_modified": False,
    }

    try:
        asset: VehicleAsset | None = None
        if glb is None or paint is None:
            try:
                asset = load_vehicle_asset(vehicle)
            except VehicleIndexError as exc:
                raise P3FAutoInputError(
                    f"Selected vehicle ZIP could not be indexed for automatic input preparation: {exc}"
                ) from exc

        # Resolve the cheap save-side dependency before running the expensive converter.
        if paint is None:
            assert asset is not None
            paint, paint_meta = _auto_select_paint(asset.car_id, args.save_root)
            auto_report["paint"] = paint_meta

        if glb is None:
            assert asset is not None
            glb, glb_meta = _auto_generate_glb(asset, cache)
            auto_report["glb"] = glb_meta
    except P3FAutoInputError as exc:
        result = _base_cli_report("p3f_input_preparation_failed")
        result["validation_status"] = "input_preparation_failed"
        result["detail"] = str(exc)
        result["vehicle_archive"] = str(vehicle)
        result["cache_root"] = str(cache)
        result["auto_input_preparation"] = auto_report
        _write_result(result, output)
        _emit_error(str(exc))
        return 6

    assert glb is not None
    assert paint is not None
    protected_inputs = {glb, paint, vehicle}
    if output is not None and output in protected_inputs:
        _emit_error("Refusing to overwrite a diagnostic source input with JSON output.")
        return 2
    if cache in protected_inputs:
        _emit_error("Refusing to use a diagnostic source file as the cache root.")
        return 2

    try:
        p3d = diagnose_manufacturer_overlay(glb, paint, vehicle)
        traced = trace_manufacturer_materialbin_payloads(p3d, vehicle, cache)
    except Exception as exc:
        result = _base_cli_report("manufacturer_materialbin_diagnostic_failed")
        result["validation_status"] = "diagnostic_execution_failed"
        result["detail"] = f"{type(exc).__name__}: {exc}"
        result["glb_file"] = str(glb)
        result["paint_source"] = str(paint)
        result["vehicle_archive"] = str(vehicle)
        result["cache_root"] = str(cache)
        result["auto_input_preparation"] = auto_report
        _write_result(result, output)
        return 5

    result = dict(traced)
    result["cli_format"] = MANUFACTURER_MATERIALBIN_CLI_FORMAT
    result["cli_revision"] = MANUFACTURER_MATERIALBIN_CLI_REVISION
    result["validation_status"] = _validation_status(result)
    result["p3d_status"] = p3d.get("status")
    result["p3d_exact_candidate_count"] = p3d.get("exact_candidate_count")
    result["glb_file"] = str(glb)
    result["paint_source"] = str(paint)
    result["vehicle_archive"] = str(vehicle)
    result["cache_root"] = str(cache)
    result["helper_revision"] = WHEEL_MORPH_HELPER_REVISION
    result["helper_sha256"] = WHEEL_MORPH_HELPER_SHA256
    result["auto_input_preparation"] = auto_report
    result["game_data_modified"] = False

    _write_result(result, output)
    return 0


def main() -> int:
    return run_manufacturer_materialbin_diagnostic()


if __name__ == "__main__":
    raise SystemExit(main())