from __future__ import annotations

from .pipeline_diagnostics import timed, record

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable


CACHE_SCHEMA = "fh6_native_tire_preview_cache_v1"


def _runtime_root() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "FH6GarageAnalyzer" / "preview3d_runtime"
    return Path.home() / ".fh6garageanalyzer" / "preview3d_runtime"


def _file_identity(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    stat = source.stat()
    return {
        "path": str(source),
        "size": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
    }


@timed('tire_cache_key')
def _stable_payload(
    integration_module: Any,
    asset: Any,
    *,
    carbin_entry: str,
    game_or_cars_path: str | Path,
    vehicle_glb: str | Path,
) -> dict[str, Any]:
    # Resolve exactly the same stock tire contract as the production integration.
    # The small database lookup is retained on a cache hit so a DB/spec change can
    # never silently reuse the wrong tire geometry.
    database_path = integration_module.ensure_stock_wheel_database(progress=None)
    spec = integration_module.FH6WheelSpecResolver(database_path).resolve(int(asset.car_id))
    tire_model_name = str(spec.tire_model_name or "").strip()
    if not tire_model_name:
        raise ValueError("stock wheel database returned no TireModelName")
    tire_archive = integration_module.resolve_tire_archive(game_or_cars_path, tire_model_name)

    return {
        "schema": CACHE_SCHEMA,
        "integration_revision": str(integration_module.GLOBAL_NATIVE_TIRE_PREVIEW_REVISION),
        "car_id": int(asset.car_id),
        "model_code": str(getattr(asset, "model_code", "") or ""),
        "carbin_entry": str(carbin_entry or ""),
        "vehicle_glb": _file_identity(vehicle_glb),
        "vehicle_archive": _file_identity(asset.archive_path),
        "wheel_database": _file_identity(database_path),
        "wheel_spec": spec.as_dict(),
        "tire_model_name": tire_model_name,
        "tire_archive": _file_identity(tire_archive),
    }


def _cache_paths(payload: dict[str, Any]) -> tuple[Path, Path]:
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()[:24]
    root = _runtime_root() / "native_tire_cache_v1" / f"car_{int(payload['car_id'])}" / digest
    return root, root / "tire_preview_cache.json"


def _valid_glb(path: Path) -> bool:
    try:
        if not path.is_file() or path.stat().st_size < 20:
            return False
        with path.open("rb") as handle:
            return handle.read(4) == b"glTF"
    except OSError:
        return False


@timed('tire_cache_lookup')
def _load_cached_result(integration_module: Any, payload: dict[str, Any], manifest: Path):
    try:
        stored = json.loads(manifest.read_text(encoding="utf-8"))
        if stored.get("key") != payload:
            return None
        selected = Path(stored["selected_vehicle_glb"]).expanduser().resolve()
        if not _valid_glb(selected):
            return None
        return integration_module.TirePreviewIntegrationResult(
            status="stock_native_tire_preview_cache_hit",
            revision=str(integration_module.GLOBAL_NATIVE_TIRE_PREVIEW_REVISION),
            car_id=int(payload["car_id"]),
            model_code=str(payload["model_code"]),
            source_vehicle_glb=str(Path(payload["vehicle_glb"]["path"])),
            selected_vehicle_glb=str(selected),
            applied=True,
            fallback_used=False,
            production_renderer_enabled=False,
            detail=(
                f"persistent native-tire cache hit; TireModelName={payload['tire_model_name']}"
            ),
            manifest_path=str(manifest),
        )
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def _store_cache_manifest(manifest: Path, payload: dict[str, Any], result: Any) -> None:
    selected = Path(result.selected_vehicle_glb).expanduser().resolve()
    if not bool(getattr(result, "applied", False)) or not _valid_glb(selected):
        return
    manifest.parent.mkdir(parents=True, exist_ok=True)
    temp = manifest.with_suffix(manifest.suffix + ".tmp")
    temp.write_text(
        json.dumps(
            {
                "format": CACHE_SCHEMA,
                "key": payload,
                "selected_vehicle_glb": str(selected),
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        ),
        encoding="utf-8",
    )
    temp.replace(manifest)


def make_native_tire_preview_cache_wrapper(
    original: Callable[..., Any], integration_module: Any
) -> Callable[..., Any]:
    def cached_try_apply(
        asset,
        *,
        carbin_entry,
        game_or_cars_path,
        vehicle_glb,
        work_root,
        progress=None,
        converter_diagnostics=None,
    ):
        try:
            payload = _stable_payload(
                integration_module,
                asset,
                carbin_entry=carbin_entry,
                game_or_cars_path=game_or_cars_path,
                vehicle_glb=vehicle_glb,
            )
            if converter_diagnostics is not None:
                # Transform/rim provenance is required by the production v3
                # attachment path, including when base geometry was cached.
                payload["converter_transform_inventory"] = {
                    key: converter_diagnostics.get(key)
                    for key in ("wheel_style_anchors", "transform_audit")
                }
            cache_root, manifest = _cache_paths(payload)
            cached = _load_cached_result(integration_module, payload, manifest)
        except (OSError, ValueError, TypeError, KeyError):
            payload = None
            cache_root = None
            manifest = None
            cached = None

        record('tire_cache', status="hit" if cached is not None else "miss")
        if cached is not None:
            if progress is not None:
                progress(
                    f"Native stock 타이어 cache hit: {payload['tire_model_name']} · 재생성/재병합을 생략합니다."
                )
            return cached

        # Normal preview uses a persistent derived-data directory. This is safe:
        # the original game/save files stay read-only and only generated GLBs are
        # stored here. If fingerprinting failed, retain the caller's temporary path.
        target_root = cache_root if cache_root is not None else Path(work_root)
        extra = {}
        if converter_diagnostics is not None:
            extra["converter_diagnostics"] = converter_diagnostics
        result = original(
            asset,
            carbin_entry=carbin_entry,
            game_or_cars_path=game_or_cars_path,
            vehicle_glb=vehicle_glb,
            work_root=target_root,
            progress=progress,
            **extra,
        )
        if payload is not None and manifest is not None:
            try:
                _store_cache_manifest(manifest, payload, result)
            except (OSError, ValueError, TypeError, KeyError):
                pass
        return result

    return cached_try_apply


def install_native_tire_preview_cache_patch() -> bool:
    """Persist the fully merged native-tire GLB instead of rebuilding it on every open."""
    from . import tire_preview_integration as integration

    if getattr(integration, "_fh6_native_tire_preview_cache_patched", False):
        return False
    original = integration.try_apply_stock_native_tire_preview
    integration.try_apply_stock_native_tire_preview = make_native_tire_preview_cache_wrapper(
        original, integration
    )
    integration._fh6_native_tire_preview_cache_patched = True
    return True
