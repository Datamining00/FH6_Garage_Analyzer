from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
import os
from pathlib import Path
import shutil
from typing import Any, Callable
import zipfile

from .tire_asset import resolve_tire_archive
from .tire_morph_boundary_roles import analyze_native_tire_selector_boundary_roles
from .tire_production_trial_geometry import build_stock_tire_production_trial_geometry
from .tire_spindle_attachment import build_tire_spindle_attachment_contract
from .tire_spindle_glb_merge import merge_tire_spindle_trial_glb
from .tire_viewer_matrix_bake import bake_native_tire_trial_node_matrices
from .wheel_spec import FH6WheelSpecResolver
from .wheel_spec_database import ensure_stock_wheel_database


GLOBAL_NATIVE_TIRE_PREVIEW_REVISION = "stock_native_tire_global_preview_v2"
FXX_NATIVE_TIRE_PREVIEW_REVISION = GLOBAL_NATIVE_TIRE_PREVIEW_REVISION
_PATCH_MARKER = "_fh6_global_stock_native_tire_preview_patched"
_LEGACY_PATCH_MARKER = "_fh6_validated_fxx_native_tire_preview_patched"
_ORIGINAL_CONVERTER = "_fh6_global_stock_native_tire_preview_original_convert_vehicle"
_DIAGNOSTIC_FORMAT = "fh6_global_stock_native_tire_preview_integration_v3"
_DIAGNOSTIC_FILENAME = "native_tire_preview_integration.json"


@dataclass(frozen=True)
class TirePreviewIntegrationResult:
    status: str
    revision: str
    car_id: int
    model_code: str
    source_vehicle_glb: str
    selected_vehicle_glb: str
    applied: bool
    fallback_used: bool
    production_renderer_enabled: bool
    detail: str
    manifest_path: str | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _notify(progress: Callable[[str], None] | None, message: str) -> None:
    if progress is not None:
        progress(message)


def _car_id(asset: Any) -> int:
    try:
        value = int(getattr(asset, "car_id"))
    except (AttributeError, TypeError, ValueError):
        return 0
    return value if value > 0 else 0


def _model_code(asset: Any) -> str:
    return str(getattr(asset, "model_code", "") or "").strip()


def _persistent_diagnostic_manifest_path(car_id: int) -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        runtime_root = Path(base) / "FH6GarageAnalyzer" / "preview3d_runtime"
    else:
        runtime_root = Path.home() / ".fh6garageanalyzer" / "preview3d_runtime"
    return (
        runtime_root
        / "diagnostics"
        / "native_tire_preview"
        / f"car_{int(car_id)}"
        / _DIAGNOSTIC_FILENAME
    )


def _write_manifest_best_effort(path: Path, payload: dict[str, Any]) -> str | None:
    """Persist diagnostics without ever turning a diagnostic I/O error into preview failure."""
    temp = path.with_suffix(path.suffix + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        temp.replace(path)
        return str(path)
    except (OSError, TypeError, ValueError):
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
        return None


def _capture_selector_boundary_report(diagnostic: dict[str, Any]) -> None:
    """Best-effort structural evidence capture for a geometry-stage fallback."""
    archive_path = diagnostic.get("tire_archive")
    if not archive_path or diagnostic.get("selector_boundary_report") is not None:
        return
    try:
        report = analyze_native_tire_selector_boundary_roles(archive_path)
        diagnostic["selector_boundary_report"] = report.as_dict()
        diagnostic["selector_boundary_report_error"] = None
    except Exception as exc:
        diagnostic["selector_boundary_report_error"] = f"{type(exc).__name__}: {exc}"


def _passthrough(
    asset: Any,
    vehicle_glb: Path,
    status: str,
    detail: str,
    *,
    manifest_path: str | None = None,
) -> TirePreviewIntegrationResult:
    return TirePreviewIntegrationResult(
        status=status,
        revision=GLOBAL_NATIVE_TIRE_PREVIEW_REVISION,
        car_id=_car_id(asset),
        model_code=_model_code(asset),
        source_vehicle_glb=str(vehicle_glb),
        selected_vehicle_glb=str(vehicle_glb),
        applied=False,
        fallback_used=status != "not_applicable",
        production_renderer_enabled=False,
        detail=detail,
        manifest_path=manifest_path,
    )


def try_apply_stock_native_tire_preview(
    asset: Any,
    *,
    carbin_entry: str,
    game_or_cars_path: str | Path,
    vehicle_glb: str | Path,
    work_root: str | Path,
    progress: Callable[[str], None] | None = None,
) -> TirePreviewIntegrationResult:
    """Apply stock native tire geometry to any structurally eligible FH6 vehicle."""
    source_glb = Path(vehicle_glb).expanduser().resolve()
    car_id = _car_id(asset)
    if car_id <= 0:
        return _passthrough(
            asset,
            source_glb,
            "not_applicable",
            "vehicle has no valid positive Car ID",
        )

    trial_root = Path(work_root).expanduser().resolve()
    trial_manifest_path = trial_root / _DIAGNOSTIC_FILENAME
    persistent_manifest_path = _persistent_diagnostic_manifest_path(car_id)
    stage = "validate_source_vehicle_glb"
    diagnostic: dict[str, Any] = {
        "format": _DIAGNOSTIC_FORMAT,
        "revision": GLOBAL_NATIVE_TIRE_PREVIEW_REVISION,
        "status": "in_progress",
        "car_id": car_id,
        "model_code": _model_code(asset),
        "source_vehicle_glb": str(source_glb),
        "selected_vehicle_glb": str(source_glb),
        "source_vehicle_archive": None,
        "carbin_entry": str(carbin_entry or "").strip(),
        "tire_model_name": None,
        "tire_archive": None,
        "wheel_spec": None,
        "geometry_report": None,
        "selector_boundary_report": None,
        "selector_boundary_report_error": None,
        "attachment_contract": None,
        "attachment_count": 0,
        "merge_report": None,
        "viewer_matrix_bake": None,
        "baked_tire_vertex_count": 0,
        "baked_tire_triangle_count": 0,
        "single_left_side_reuse_count": 0,
        "failed_stage": None,
        "error_type": None,
        "error": None,
        "detail": None,
        "temporary_manifest_path": str(trial_manifest_path),
        "persistent_manifest_path": str(persistent_manifest_path),
        "fallback_on_failure": True,
        "production_renderer_enabled": False,
    }

    try:
        if not source_glb.is_file():
            raise FileNotFoundError(f"converted vehicle GLB does not exist: {source_glb}")

        stage = "validate_source_archive"
        source_archive = Path(getattr(asset, "archive_path")).expanduser().resolve()
        diagnostic["source_vehicle_archive"] = str(source_archive)
        if not source_archive.is_file():
            raise FileNotFoundError(f"vehicle archive does not exist: {source_archive}")

        stage = "validate_carbin_entry"
        selected_carbin = str(carbin_entry or "").strip()
        diagnostic["carbin_entry"] = selected_carbin
        if not selected_carbin:
            raise ValueError("selected carbin entry is empty")
        indexed_entries = tuple(str(item) for item in getattr(asset, "carbin_entries", ()) or ())
        if indexed_entries and selected_carbin not in indexed_entries:
            raise ValueError(f"selected carbin is not indexed in the vehicle archive: {selected_carbin}")

        stage = "resolve_stock_wheel_spec"
        _notify(progress, "Stock native 타이어 데이터를 확인합니다...")
        database_path = ensure_stock_wheel_database(progress)
        spec = FH6WheelSpecResolver(database_path).resolve(car_id)
        if int(spec.car_id) != car_id:
            raise ValueError(
                f"stock wheel database returned unexpected Car ID {spec.car_id}; expected {car_id}"
            )
        diagnostic["wheel_spec"] = spec.as_dict()
        tire_model_name = str(spec.tire_model_name or "").strip()
        diagnostic["tire_model_name"] = tire_model_name
        if not tire_model_name:
            raise ValueError("stock wheel database returned no TireModelName")

        stage = "resolve_tire_archive"
        tire_archive = resolve_tire_archive(game_or_cars_path, tire_model_name)
        diagnostic["tire_archive"] = str(tire_archive)

        stage = "prepare_trial_directory"
        shutil.rmtree(trial_root, ignore_errors=True)
        trial_root.mkdir(parents=True, exist_ok=False)

        stage = "build_tire_geometry"
        geometry_report = build_stock_tire_production_trial_geometry(
            spec,
            tire_archive,
            trial_root / "tire_geometry",
        )
        diagnostic["geometry_report"] = geometry_report.as_dict()

        stage = "read_carbin"
        with zipfile.ZipFile(source_archive, "r") as archive:
            try:
                carbin_data = archive.read(selected_carbin)
            except KeyError as exc:
                raise ValueError(
                    f"selected carbin entry disappeared from vehicle archive: {selected_carbin}"
                ) from exc

        stage = "build_spindle_attachment"
        contract_path = trial_root / "native_tire_spindle_attachment_contract.json"
        attachment = build_tire_spindle_attachment_contract(
            carbin_data,
            geometry_report.as_dict(),
            output_path=contract_path,
        )
        attachment_payload = attachment.as_dict()
        diagnostic["attachment_contract"] = attachment_payload
        attachments = attachment_payload.get("attachments", [])
        if isinstance(attachments, list):
            diagnostic["attachment_count"] = len(attachments)
        side_reuse_count = sum(
            1
            for item in attachments
            if isinstance(item, dict)
            and item.get("side_source_mode") == "single_left_model_reused_by_native_spindle"
        )
        diagnostic["single_left_side_reuse_count"] = side_reuse_count

        stage = "merge_tire_glb"
        output_glb = trial_root / f"{source_glb.stem}__native_tires.glb"
        diagnostic["selected_vehicle_glb"] = str(output_glb)
        merge_report = merge_tire_spindle_trial_glb(
            source_glb,
            attachment_payload,
            output_glb,
        )
        diagnostic["merge_report"] = merge_report.as_dict()
        if not merge_report.trial_vehicle_glb_ready or not output_glb.is_file():
            raise RuntimeError("native tire merge did not produce a ready trial vehicle GLB")

        stage = "bake_spindle_matrix"
        viewer_matrix_bake = bake_native_tire_trial_node_matrices(output_glb)
        diagnostic["viewer_matrix_bake"] = viewer_matrix_bake
        baked_nodes = int(viewer_matrix_bake.get("node_count", 0))
        baked_vertices = int(viewer_matrix_bake.get("vertex_count", 0))
        baked_triangles = int(viewer_matrix_bake.get("triangle_winding_reversed_count", 0))
        diagnostic["baked_tire_vertex_count"] = baked_vertices
        diagnostic["baked_tire_triangle_count"] = baked_triangles

        stage = "validate_final_glb"
        if baked_nodes != 4:
            raise RuntimeError("native tire viewer matrix bake did not process four spindle nodes")
        if baked_vertices <= 0 or baked_triangles <= 0:
            raise RuntimeError(
                "native tire viewer matrix bake produced no drawable tire geometry"
            )

        diagnostic.update(
            {
                "status": "stock_native_tire_preview_applied",
                "failed_stage": None,
                "error_type": None,
                "error": None,
                "detail": (
                    f"TireModelName={tire_model_name}; spindles=4; "
                    f"baked_vertices={baked_vertices}; baked_triangles={baked_triangles}; "
                    f"single_left_side_reuse={side_reuse_count}"
                ),
                "limitations": [
                    "Automatic native tire preview is stock-spec only.",
                    "Known exact tire geometry identities use the validated fast path; an unlisted family must reproduce the validated selector boundary-role pattern read-only before use.",
                    "A tireL_-only native family may reuse its canonical geometry on right spindles; the native WheelStyle RF/RR matrices provide side orientation without a procedural geometry mirror.",
                    "Selector 2..4 remain zero until their game-facing semantics are verified.",
                    "No arbitrary per-car translation, rotation, or scale correction is applied.",
                ],
            }
        )
        temporary_manifest = _write_manifest_best_effort(trial_manifest_path, diagnostic)
        persistent_manifest = _write_manifest_best_effort(persistent_manifest_path, diagnostic)
        manifest_path = persistent_manifest or temporary_manifest

        _notify(
            progress,
            f"Native stock 타이어({tire_model_name}) 적용 완료: "
            f"4 spindles / {baked_vertices:,} vertices / {baked_triangles:,} triangles"
            + (f" / single-left reuse {side_reuse_count}" if side_reuse_count else ""),
        )
        return TirePreviewIntegrationResult(
            status="stock_native_tire_preview_applied",
            revision=GLOBAL_NATIVE_TIRE_PREVIEW_REVISION,
            car_id=car_id,
            model_code=_model_code(asset),
            source_vehicle_glb=str(source_glb),
            selected_vehicle_glb=str(output_glb),
            applied=True,
            fallback_used=False,
            production_renderer_enabled=False,
            detail=str(diagnostic["detail"]),
            manifest_path=manifest_path,
        )
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"
        if stage == "build_tire_geometry":
            _capture_selector_boundary_report(diagnostic)
        diagnostic.update(
            {
                "status": "fallback_existing_vehicle_glb",
                "selected_vehicle_glb": str(source_glb),
                "failed_stage": stage,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "detail": detail,
            }
        )
        temporary_manifest = _write_manifest_best_effort(trial_manifest_path, diagnostic)
        persistent_manifest = _write_manifest_best_effort(persistent_manifest_path, diagnostic)
        manifest_path = persistent_manifest or temporary_manifest
        _notify(
            progress,
            "Native stock tire preview FALLBACK: 기존 차량 GLB를 사용합니다. "
            f"단계={stage}; 원인={detail}"
            + (f"; 진단={manifest_path}" if manifest_path else ""),
        )
        return _passthrough(
            asset,
            source_glb,
            "fallback_existing_vehicle_glb",
            detail,
            manifest_path=manifest_path,
        )


def _with_tire_diagnostics(result: Any, integration: TirePreviewIntegrationResult) -> Any:
    try:
        diagnostics = dict(getattr(result, "diagnostics", {}) or {})
        diagnostics["native_tire_preview"] = integration.as_dict()
        return replace(result, diagnostics=diagnostics)
    except (TypeError, AttributeError):
        return result


def make_stock_native_tire_convert_wrapper(original_convert: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap the normal FHA preview conversion with global stock native-tire integration."""

    def convert_with_stock_native_tires(
        asset: Any,
        progress: Callable[[str], None] | None = None,
        *,
        carbin_entry: str | None = None,
        work_root: str | Path | None = None,
        rim_morph_weights: Any = None,
        converter_override: str | Path | None = None,
    ) -> Any:
        result = original_convert(
            asset,
            progress,
            carbin_entry=carbin_entry,
            work_root=work_root,
            rim_morph_weights=rim_morph_weights,
            converter_override=converter_override,
        )

        if rim_morph_weights is not None or converter_override is not None:
            return result
        car_id = _car_id(asset)
        if car_id <= 0:
            return result

        selected_carbin = str(carbin_entry or "").strip()
        if not selected_carbin:
            entries = tuple(str(item) for item in getattr(asset, "carbin_entries", ()) or ())
            if len(entries) == 1:
                selected_carbin = entries[0]
            else:
                return result

        source_archive = Path(getattr(asset, "archive_path")).expanduser().resolve()
        cars_root = source_archive.parent
        converter_root = (
            Path(work_root).expanduser().resolve()
            if work_root is not None
            else Path(result.output_path).expanduser().resolve().parent
        )
        tire_root = converter_root / "native_tire_preview" / f"car_{car_id}"
        integration = try_apply_stock_native_tire_preview(
            asset,
            carbin_entry=selected_carbin,
            game_or_cars_path=cars_root,
            vehicle_glb=result.output_path,
            work_root=tire_root,
            progress=progress,
        )
        result_with_diagnostics = _with_tire_diagnostics(result, integration)
        if not integration.applied:
            return result_with_diagnostics
        return replace(
            result_with_diagnostics,
            output_path=str(Path(integration.selected_vehicle_glb).resolve()),
        )

    convert_with_stock_native_tires.__name__ = getattr(
        original_convert,
        "__name__",
        "convert_vehicle",
    )
    convert_with_stock_native_tires.__doc__ = getattr(original_convert, "__doc__", None)
    return convert_with_stock_native_tires


def install_global_stock_native_tire_preview() -> bool:
    """Lazily install the global stock native-tire wrapper into preview3d.integration."""
    from . import integration as preview_integration

    if bool(getattr(preview_integration, _PATCH_MARKER, False)):
        return False
    if bool(getattr(preview_integration, _LEGACY_PATCH_MARKER, False)):
        return False
    original = preview_integration.convert_vehicle
    setattr(preview_integration, _ORIGINAL_CONVERTER, original)
    preview_integration.convert_vehicle = make_stock_native_tire_convert_wrapper(original)
    setattr(preview_integration, _PATCH_MARKER, True)
    setattr(preview_integration, _LEGACY_PATCH_MARKER, True)
    return True


def try_apply_validated_fxx_native_tire_preview(*args: Any, **kwargs: Any) -> TirePreviewIntegrationResult:
    return try_apply_stock_native_tire_preview(*args, **kwargs)


def make_validated_fxx_tire_convert_wrapper(original_convert: Callable[..., Any]) -> Callable[..., Any]:
    return make_stock_native_tire_convert_wrapper(original_convert)


def install_validated_fxx_native_tire_preview() -> bool:
    return install_global_stock_native_tire_preview()
