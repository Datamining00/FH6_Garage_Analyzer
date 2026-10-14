from __future__ import annotations

from .pipeline_diagnostics import timed, record

import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any


CACHE_SCHEMA = "fh6_preview3d_geometry_cache_v2"


def _stable_payload(asset: Any, carbin_entry: str, morph: Any) -> dict[str, Any]:
    from .chassis_converter import CONVERTER_COMMIT
    from .near_lod_archive import NORMALIZATION_REVISION
    from .neutral_geometry import NEUTRAL_GEOMETRY_REVISION
    from .wheel_visibility import WHEEL_VISIBILITY_REVISION
    from .wheel_morph_helper import WHEEL_MORPH_HELPER_REVISION
    from .wheel_morph_runtime import WHEEL_MORPH_RUNTIME_REVISION

    archive = Path(asset.archive_path).resolve()
    stat = archive.stat()
    weights = None
    if getattr(morph, "weights", None) is not None:
        try:
            weights = asdict(morph.weights)
        except TypeError:
            weights = repr(morph.weights)
    payload = {
        "schema": CACHE_SCHEMA,
        "car_id": int(asset.car_id),
        "model_code": str(asset.model_code),
        "archive_path": str(archive),
        "archive_size": int(stat.st_size),
        "archive_mtime_ns": int(stat.st_mtime_ns),
        "carbin_entry": str(carbin_entry),
        "converter_commit": CONVERTER_COMMIT,
        "near_lod_revision": NORMALIZATION_REVISION,
        "neutral_geometry_revision": NEUTRAL_GEOMETRY_REVISION,
        "wheel_visibility_revision": WHEEL_VISIBILITY_REVISION,
        "wheel_morph_helper_revision": WHEEL_MORPH_HELPER_REVISION,
        "wheel_morph_runtime_revision": WHEEL_MORPH_RUNTIME_REVISION,
        "automatic_morph_status": str(getattr(morph, "status", "unknown")),
        "automatic_morph_source_revision": getattr(morph, "source_revision", None),
        "automatic_morph_weights": weights,
    }
    from ..app_options import load_options
    if load_options().skip_vehicle_materials:
        payload['skip_vehicle_materials'] = True
    return payload


def _cache_paths(asset: Any, payload: dict[str, Any]) -> tuple[Path, Path]:
    from .chassis_converter import app_data_root

    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()[:20]
    model = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(asset.model_code))
    # Keep the converter's canonical GLB basename inside a fingerprinted directory.
    # Native material/texture sidecars are named relative to that basename; keeping
    # it unchanged avoids disconnecting those side products from the cached GLB.
    root = (
        app_data_root()
        / "geometry_cache_v1"
        / f"car_{int(asset.car_id)}_{model}"
        / digest
    )
    root.mkdir(parents=True, exist_ok=True)
    return root / f"car_{int(asset.car_id)}_{model}.glb", root / "manifest.json"


@timed("geometry_cache_lookup")
def _valid_cached_glb(glb: Path, manifest: Path, payload: dict[str, Any]) -> bool:
    try:
        if not glb.is_file() or glb.stat().st_size < 20:
            return False
        with glb.open("rb") as handle:
            if handle.read(4) != b"glTF":
                return False
        stored = json.loads(manifest.read_text(encoding="utf-8"))
        return stored.get("key") == payload and isinstance(stored.get("diagnostics"), dict)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False


def install_geometry_cache_patch() -> bool:
    """Persist verified converted GLBs and skip repeated KFPS conversion per vehicle."""
    from . import chassis_converter
    from .wheel_morph_auto import resolve_automatic_stock_rim_morph

    if getattr(chassis_converter, "_fh6_geometry_cache_patched", False):
        return False

    original = chassis_converter.convert_vehicle

    def cached_convert_vehicle(asset, progress=None, *, carbin_entry=None, work_root=None,
                               rim_morph_weights=None, converter_override=None):
        # Explicit overrides/custom morph requests are diagnostic paths: do not
        # cache them because their provenance may be external or caller-defined.
        from ..app_options import load_options
        if not load_options().render_cache or converter_override is not None or rim_morph_weights is not None:
            return original(
                asset,
                progress=progress,
                carbin_entry=carbin_entry,
                work_root=work_root,
                rim_morph_weights=rim_morph_weights,
                converter_override=converter_override,
            )

        if carbin_entry is None:
            if len(asset.carbin_entries) != 1:
                return original(asset, progress=progress, carbin_entry=carbin_entry, work_root=work_root)
            carbin_entry = asset.carbin_entries[0]

        morph = resolve_automatic_stock_rim_morph(asset.car_id, asset.model_code, progress=None)
        try:
            payload = _stable_payload(asset, carbin_entry, morph)
            glb, manifest = _cache_paths(asset, payload)
        except (OSError, ValueError, TypeError):
            return original(asset, progress=progress, carbin_entry=carbin_entry, work_root=work_root)

        if _valid_cached_glb(glb, manifest, payload):
            record("geometry_cache", status="hit", glb_path=str(glb))
            stored = json.loads(manifest.read_text(encoding="utf-8"))
            diagnostics = dict(stored["diagnostics"])
            diagnostics.update(status="cache_hit", cache_schema=CACHE_SCHEMA)
            if progress:
                progress(f"3D geometry cache hit: Car ID {asset.car_id} 변환을 생략합니다.")
            return chassis_converter.ConversionResult(
                output_path=str(glb),
                helper_path="persistent_geometry_cache",
                diagnostics=diagnostics,
            )

        record("geometry_cache", status="miss", glb_path=str(glb))
        if progress:
            progress(f"3D geometry cache miss: Car ID {asset.car_id} 최초 변환을 수행합니다.")

        # Store the full converter output and all native material side products under
        # LocalAppData rather than the dialog TemporaryDirectory. The original FH6
        # archive remains read-only; only derived cache files are persistent.
        result = original(
            asset,
            progress=progress,
            carbin_entry=carbin_entry,
            work_root=glb.parent,
            rim_morph_weights=getattr(morph, "weights", None),
            converter_override=None,
        )
        produced = Path(result.output_path)
        try:
            if produced.resolve() != glb.resolve():
                # This should not normally happen because glb.parent is passed as
                # work_root. Avoid moving a GLB whose adjacent sidecars would then
                # lose basename-relative provenance; simply use the produced path.
                return result
            temporary_manifest = manifest.with_suffix(".tmp")
            temporary_manifest.write_text(
                json.dumps({"key": payload, "diagnostics": dict(result.diagnostics or {})},
                           ensure_ascii=False, sort_keys=True, indent=2),
                encoding="utf-8",
            )
            temporary_manifest.replace(manifest)
        except (OSError, TypeError, ValueError):
            # Cache persistence is an optimization only. A valid produced GLB
            # remains usable even if the manifest cannot be written.
            return result

        diagnostics = dict(result.diagnostics or {})
        diagnostics["status"] = "cache_miss_converted"
        diagnostics["cache_schema"] = CACHE_SCHEMA
        return chassis_converter.ConversionResult(
            output_path=str(glb),
            helper_path=result.helper_path,
            diagnostics=diagnostics,
        )

    chassis_converter.convert_vehicle = cached_convert_vehicle
    chassis_converter._fh6_geometry_cache_patched = True

    integration = sys.modules.get(f"{__package__}.integration")
    if integration is not None and getattr(integration, "convert_vehicle", None) is original:
        integration.convert_vehicle = cached_convert_vehicle
    return True
