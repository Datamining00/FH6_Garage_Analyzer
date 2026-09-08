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


GLOBAL_NATIVE_TIRE_PREVIEW_REVISION = "stock_native_tire_global_preview_v1"
# Compatibility constant retained for older diagnostics/tests.
FXX_NATIVE_TIRE_PREVIEW_REVISION = GLOBAL_NATIVE_TIRE_PREVIEW_REVISION
_PATCH_MARKER = "_fh6_global_stock_native_tire_preview_patched"
_LEGACY_PATCH_MARKER = "_fh6_validated_fxx_native_tire_preview_patched"
_ORIGINAL_CONVERTER = "_fh6_global_stock_native_tire_preview_original_convert_vehicle"


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


def _passthrough(
    asset: Any,
    vehicle_glb: Path,
    status: str,
    detail: str,
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
        manifest_path=None,
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
    """Apply the supported native stock-tire preview to any eligible FH6 vehicle.

    Eligibility is global at the vehicle level and fail-closed at the native tire
    family/geometry level.  Unsupported or structurally mismatched tire families,
    missing WheelStyle spindle evidence, archive changes, or any merge/bake failure
    leave the already valid converter GLB selected.  Native FH6 files are read only.
    """

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
        if indexed_entries and selected_carbin not in indexed_entries:
            raise ValueError(f"selected carbin is not indexed in the vehicle archive: {selected_carbin}")

        _notify(progress, "Stock native 타이어 데이터를 확인합니다...")
        database_path = ensure_stock_wheel_database(progress)
        spec = FH6WheelSpecResolver(database_path).resolve(car_id)
        if int(spec.car_id) != car_id:
            raise ValueError(
                f"stock wheel database returned unexpected Car ID {spec.car_id}; expected {car_id}"
            )
        tire_model_name = str(spec.tire_model_name or "").strip()
        if not tire_model_name:
            raise ValueError("stock wheel database returned no TireModelName")

        tire_archive = resolve_tire_archive(game_or_cars_path, tire_model_name)

        # Derived preview-only workspace.  Source vehicle/tire archives and the
        # converter's base GLB are never overwritten.
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

        # KFPS converter emits already-world-positioned geometry in render space
        # after its X-axis handedness conversion.  Apply the exact same conversion
        # to the four native tire derivatives before FinalVerify1 consumes them.
        viewer_matrix_bake = bake_native_tire_trial_node_matrices(output_glb)
        if int(viewer_matrix_bake.get("node_count", 0)) != 4:
            raise RuntimeError("native tire viewer matrix bake did not process four spindle nodes")

        manifest_path = trial_root / "native_tire_preview_integration.json"
        manifest = {
            "format": "fh6_global_stock_native_tire_preview_integration_v1",
            "revision": GLOBAL_NATIVE_TIRE_PREVIEW_REVISION,
            "status": "stock_native_tire_preview_applied",
            "car_id": car_id,
            "model_code": _model_code(asset),
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
                "Automatic native tire preview is stock-spec only.",
                "Only exact native tire-family geometry identities admitted by the global preview policy are used; unsupported or structurally mismatched families fall back to the base vehicle GLB.",
                "Selector 2..4 remain zero until their game-facing semantics are verified.",
                "No arbitrary per-car translation, rotation, or scale correction is applied.",
                "WheelStyle spindle matrices and the KFPS render-space handedness conversion are used for placement.",
            ],
        }
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        _notify(
            progress,
            f"Native stock 타이어({tire_model_name})를 WheelStyle spindle에 적용했습니다.",
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
            detail=(
                f"stock native tire preview selected for Car ID {car_id} "
                f"using TireModelName={tire_model_name}"
            ),
            manifest_path=str(manifest_path),
        )
    except Exception as exc:
        # Global native tire preview must never make a previously valid 3D preview fail.
        shutil.rmtree(trial_root, ignore_errors=True)
        detail = f"{type(exc).__name__}: {exc}"
        _notify(
            progress,
            "Native stock tire preview를 적용하지 못해 기존 차량 GLB로 계속합니다 "
            f"({detail}).",
        )
        return _passthrough(asset, source_glb, "fallback_existing_vehicle_glb", detail)


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

        # Explicit diagnostic/converter overrides stay byte-for-byte on their
        # existing path.  Global native tire integration belongs to normal FHA 3D.
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
        if not integration.applied:
            return result
        return replace(result, output_path=str(Path(integration.selected_vehicle_glb).resolve()))

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
    # Retain the old marker so older code cannot install a second wrapper.
    setattr(preview_integration, _LEGACY_PATCH_MARKER, True)
    return True


# Compatibility APIs retained so FinalVerify1 and older diagnostic scripts do not
# need a synchronized import-name migration.  Their behavior is now global.
def try_apply_validated_fxx_native_tire_preview(*args: Any, **kwargs: Any) -> TirePreviewIntegrationResult:
    return try_apply_stock_native_tire_preview(*args, **kwargs)


def make_validated_fxx_tire_convert_wrapper(original_convert: Callable[..., Any]) -> Callable[..., Any]:
    return make_stock_native_tire_convert_wrapper(original_convert)


def install_validated_fxx_native_tire_preview() -> bool:
    return install_global_stock_native_tire_preview()
