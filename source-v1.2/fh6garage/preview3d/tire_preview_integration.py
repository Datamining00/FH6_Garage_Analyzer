from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
from pathlib import Path
import shutil
from typing import Any, Callable
import zipfile

from .tire_asset import resolve_tire_archive
from .tire_production_trial_geometry import build_stock_tire_production_trial_geometry
from .tire_spindle_attachment import build_tire_spindle_attachment_contract
from .tire_spindle_glb_merge import merge_tire_spindle_trial_glb
from .tire_viewer_matrix_bake import bake_native_tire_trial_node_matrices
from .wheel_spec import FH6WheelSpecResolver
from .wheel_spec_database import ensure_stock_wheel_database


FXX_NATIVE_TIRE_PREVIEW_REVISION = "fxx_1006_slick_lazy_preview_v2"
_FXX_CAR_ID = 1006
_FXX_MODEL_CODE = "FER_FXX_05"
_PATCH_MARKER = "_fh6_validated_fxx_native_tire_preview_patched"
_ORIGINAL_CONVERTER = "_fh6_validated_fxx_native_tire_preview_original_convert_vehicle"


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


def _is_validated_fxx(asset: Any) -> bool:
    try:
        car_id = int(getattr(asset, "car_id"))
    except (TypeError, ValueError):
        return False
    model_code = str(getattr(asset, "model_code", "") or "").strip()
    return car_id == _FXX_CAR_ID and model_code.casefold() == _FXX_MODEL_CODE.casefold()


def _passthrough(asset: Any, vehicle_glb: Path, status: str, detail: str) -> TirePreviewIntegrationResult:
    return TirePreviewIntegrationResult(
        status=status,
        revision=FXX_NATIVE_TIRE_PREVIEW_REVISION,
        car_id=int(getattr(asset, "car_id", 0) or 0),
        model_code=str(getattr(asset, "model_code", "") or ""),
        source_vehicle_glb=str(vehicle_glb),
        selected_vehicle_glb=str(vehicle_glb),
        applied=False,
        fallback_used=status != "not_applicable",
        production_renderer_enabled=False,
        detail=detail,
        manifest_path=None,
    )


def try_apply_validated_fxx_native_tire_preview(
    asset: Any,
    *,
    carbin_entry: str,
    game_or_cars_path: str | Path,
    vehicle_glb: str | Path,
    work_root: str | Path,
    progress: Callable[[str], None] | None = None,
) -> TirePreviewIntegrationResult:
    """Add the empirically validated FXX/Slick tire trial to a derived preview GLB.

    This is deliberately narrow and fail-open for the UI: only Car ID 1006 with the
    exact FER_FXX_05 model code is attempted. Any missing/changed prerequisite leaves
    the already valid converter GLB selected. Native FH6 archives are read only.
    """

    source_glb = Path(vehicle_glb).expanduser().resolve()
    if not _is_validated_fxx(asset):
        return _passthrough(
            asset,
            source_glb,
            "not_applicable",
            "validated native tire preview is currently restricted to FER_FXX_05 (Car ID 1006)",
        )

    trial_root = Path(work_root).expanduser().resolve()
    try:
        if not source_glb.is_file():
            raise FileNotFoundError(f"converted vehicle GLB does not exist: {source_glb}")

        source_archive = Path(getattr(asset, "archive_path")).expanduser().resolve()
        if not source_archive.is_file():
            raise FileNotFoundError(f"vehicle archive does not exist: {source_archive}")

        selected_carbin = str(carbin_entry or "").strip()
        if not selected_carbin:
            raise ValueError("selected carbin entry is empty")
        indexed_entries = tuple(str(item) for item in getattr(asset, "carbin_entries", ()) or ())
        if selected_carbin not in indexed_entries:
            raise ValueError(f"selected carbin is not indexed in the vehicle archive: {selected_carbin}")

        _notify(progress, "검증된 FXX native Slick 타이어를 준비합니다...")
        database_path = ensure_stock_wheel_database(progress)
        spec = FH6WheelSpecResolver(database_path).resolve(_FXX_CAR_ID)
        if int(spec.car_id) != _FXX_CAR_ID:
            raise ValueError(f"stock wheel database returned unexpected Car ID {spec.car_id}")
        if str(spec.tire_model_name or "").casefold() != "slick":
            raise ValueError(
                f"validated FXX native tire preview requires TireModelName='Slick', got {spec.tire_model_name!r}"
            )

        tire_archive = resolve_tire_archive(game_or_cars_path, spec.tire_model_name)

        # This directory contains derived preview-only files. It is always separate
        # from the source vehicle ZIP and generated base GLB.
        shutil.rmtree(trial_root, ignore_errors=True)
        trial_root.mkdir(parents=True, exist_ok=False)

        geometry_report = build_stock_tire_production_trial_geometry(
            spec,
            tire_archive,
            trial_root / "tire_geometry",
        )

        with zipfile.ZipFile(source_archive, "r") as archive:
            try:
                carbin_data = archive.read(selected_carbin)
            except KeyError as exc:
                raise ValueError(
                    f"selected carbin entry disappeared from vehicle archive: {selected_carbin}"
                ) from exc

        contract_path = trial_root / "native_tire_spindle_attachment_contract.json"
        attachment = build_tire_spindle_attachment_contract(
            carbin_data,
            geometry_report.as_dict(),
            output_path=contract_path,
        )

        output_glb = trial_root / f"{source_glb.stem}__native_tires.glb"
        merge_report = merge_tire_spindle_trial_glb(
            source_glb,
            attachment.as_dict(),
            output_glb,
        )
        if not merge_report.trial_vehicle_glb_ready or not output_glb.is_file():
            raise RuntimeError("native tire merge did not produce a ready trial vehicle GLB")

        # FinalVerify1 historically renders converter meshes from baked world-space
        # POSITION arrays and does not traverse glTF node matrices. Bake only the
        # four newly added native tire matrices into their derivative POSITION
        # streams. This preserves the exact WheelStyle transforms while leaving
        # every pre-existing vehicle mesh untouched.
        viewer_matrix_bake = bake_native_tire_trial_node_matrices(output_glb)
        if int(viewer_matrix_bake.get("node_count", 0)) != 4:
            raise RuntimeError("native tire viewer matrix bake did not process four spindle nodes")

        manifest_path = trial_root / "native_tire_preview_integration.json"
        manifest = {
            "format": "fh6_validated_native_tire_preview_integration_v1",
            "revision": FXX_NATIVE_TIRE_PREVIEW_REVISION,
            "status": "validated_fxx_native_tire_preview_applied",
            "car_id": _FXX_CAR_ID,
            "model_code": _FXX_MODEL_CODE,
            "source_vehicle_glb": str(source_glb),
            "selected_vehicle_glb": str(output_glb),
            "source_vehicle_archive": str(source_archive),
            "carbin_entry": selected_carbin,
            "tire_archive": str(tire_archive),
            "wheel_spec": spec.as_dict(),
            "geometry_report": geometry_report.as_dict(),
            "attachment_contract": attachment.as_dict(),
            "merge_report": merge_report.as_dict(),
            "viewer_matrix_bake": viewer_matrix_bake,
            "fallback_on_failure": True,
            "production_renderer_enabled": False,
            "limitations": [
                "Automatic native tire preview is currently restricted to the visually validated FER_FXX_05 stock Slick case.",
                "No arbitrary per-car translation, rotation, or scale correction is applied.",
                "The exact native WheelStyle node matrices are baked into the four derivative tire POSITION streams for FinalVerify1 viewer compatibility.",
                "Other tire families and vehicles remain on the existing preview path until independently validated.",
            ],
        }
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        _notify(progress, "FXX native Slick 타이어를 WheelStyle spindle에 적용했습니다.")
        return TirePreviewIntegrationResult(
            status="validated_fxx_native_tire_preview_applied",
            revision=FXX_NATIVE_TIRE_PREVIEW_REVISION,
            car_id=_FXX_CAR_ID,
            model_code=_FXX_MODEL_CODE,
            source_vehicle_glb=str(source_glb),
            selected_vehicle_glb=str(output_glb),
            applied=True,
            fallback_used=False,
            production_renderer_enabled=False,
            detail="validated stock FXX/Slick derivative selected for the 3D preview",
            manifest_path=str(manifest_path),
        )
    except Exception as exc:
        # The native tire path must never make a previously valid 3D preview fail.
        shutil.rmtree(trial_root, ignore_errors=True)
        detail = f"{type(exc).__name__}: {exc}"
        _notify(
            progress,
            "Native tire trial을 적용하지 못해 기존 차량 GLB로 계속합니다 "
            f"({detail}).",
        )
        return _passthrough(asset, source_glb, "fallback_existing_vehicle_glb", detail)


def make_validated_fxx_tire_convert_wrapper(original_convert: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap only the preview controller's converter result; the converter itself is unchanged."""

    def convert_with_validated_fxx_tires(
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

        # Explicit diagnostic/converter overrides are intentionally kept byte-for-byte
        # on their existing path. The automatic native-tire trial belongs only to the
        # normal FHA 3D preview request.
        if rim_morph_weights is not None or converter_override is not None:
            return result
        if not _is_validated_fxx(asset):
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
        tire_root = converter_root / "native_tire_preview"
        integration = try_apply_validated_fxx_native_tire_preview(
            asset,
            carbin_entry=selected_carbin,
            game_or_cars_path=cars_root,
            vehicle_glb=result.output_path,
            work_root=tire_root,
            progress=progress,
        )
        if not integration.applied:
            return result
        return replace(result, output_path=str(Path(integration.selected_vehicle_glb).resolve()))

    convert_with_validated_fxx_tires.__name__ = getattr(
        original_convert,
        "__name__",
        "convert_vehicle",
    )
    convert_with_validated_fxx_tires.__doc__ = getattr(original_convert, "__doc__", None)
    return convert_with_validated_fxx_tires


def install_validated_fxx_native_tire_preview() -> bool:
    """Lazily install the FXX-only preview wrapper into preview3d.integration.

    Returns True only on the first installation. Importing FHA or opening non-3D UI
    does not activate this path; the FinalVerify1 3D tab calls this installer lazily.
    """

    from . import integration as preview_integration

    if bool(getattr(preview_integration, _PATCH_MARKER, False)):
        return False
    original = preview_integration.convert_vehicle
    setattr(preview_integration, _ORIGINAL_CONVERTER, original)
    preview_integration.convert_vehicle = make_validated_fxx_tire_convert_wrapper(original)
    setattr(preview_integration, _PATCH_MARKER, True)
    return True
