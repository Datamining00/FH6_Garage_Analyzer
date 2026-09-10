from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any


CACHE_SCHEMA = "fh6_preview3d_livery_sections_v1"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _cache_key(source: Path, resolution_key: str, game_folder: str | Path | None) -> tuple[str, dict[str, Any]]:
    from .kfps_render_backend import KFPS_COMMIT, RUNTIME_REVISION, _app_root

    stat = source.stat()
    payload = {
        "schema": CACHE_SCHEMA,
        "source_path": str(source.resolve()),
        "source_size": int(stat.st_size),
        "source_mtime_ns": int(stat.st_mtime_ns),
        "source_sha256": _sha256_file(source),
        "resolution": str(resolution_key),
        "kfps_commit": str(KFPS_COMMIT),
        "runtime_revision": str(RUNTIME_REVISION),
        "game_folder": str(Path(game_folder).resolve()) if game_folder else "",
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    key = hashlib.sha256(encoded).hexdigest()[:28]
    root = _app_root() / "livery_section_cache_v1" / key
    return str(root), payload


def _png_dimensions(path: Path) -> tuple[int, int] | None:
    try:
        with path.open("rb") as handle:
            header = handle.read(24)
        if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
            return None
        return int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big")
    except OSError:
        return None


def _load_cached_result(root: Path, payload: dict[str, Any]):
    from .kfps_render_backend import RenderResult

    manifest = root / "manifest.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if data.get("key") != payload:
            return None
        canvas = tuple(int(v) for v in data["canvas_size"])
        png_paths: dict[str, Path] = {}
        for name in data.get("rendered_sections", []):
            path = root / f"{name}.png"
            if _png_dimensions(path) != canvas:
                return None
            png_paths[str(name)] = path
        return RenderResult(
            source_path=Path(payload["source_path"]),
            output_dir=root,
            car_id=int(data["car_id"]),
            layer_count=int(data["layer_count"]),
            section_counts={str(k): int(v) for k, v in data["section_counts"].items()},
            png_paths=png_paths,
            decoder_warnings=[str(v) for v in data.get("decoder_warnings", [])],
            canvas_size=canvas,
            resolution_name=str(data["resolution_name"]),
            raster_ids=tuple(int(v) for v in data.get("raster_ids", [])),
            raster_skipped_ids=tuple(int(v) for v in data.get("raster_skipped_ids", [])),
            raster_skipped_layer_count=int(data.get("raster_skipped_layer_count", 0)),
        )
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def _store_result(root: Path, payload: dict[str, Any], result: Any) -> None:
    root.mkdir(parents=True, exist_ok=True)
    rendered_sections: list[str] = []
    for section, source in dict(getattr(result, "png_paths", {}) or {}).items():
        source_path = Path(source)
        if not source_path.is_file():
            continue
        target = root / f"{section}.png"
        try:
            shutil.copy2(source_path, target)
        except OSError:
            continue
        rendered_sections.append(str(section))

    manifest = {
        "key": payload,
        "car_id": int(result.car_id),
        "layer_count": int(result.layer_count),
        "section_counts": {str(k): int(v) for k, v in dict(result.section_counts).items()},
        "decoder_warnings": [str(v) for v in list(result.decoder_warnings or [])],
        "canvas_size": [int(v) for v in result.canvas_size],
        "resolution_name": str(result.resolution_name),
        "raster_ids": [int(v) for v in tuple(getattr(result, "raster_ids", ()) or ())],
        "raster_skipped_ids": [int(v) for v in tuple(getattr(result, "raster_skipped_ids", ()) or ())],
        "raster_skipped_layer_count": int(getattr(result, "raster_skipped_layer_count", 0) or 0),
        "rendered_sections": sorted(rendered_sections),
    }
    try:
        (root / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


def install_livery_render_cache_patch() -> bool:
    """Reuse exact rendered section PNGs for the same C_livery/resolution/runtime."""
    from . import kfps_render_backend
    from .livery_resolution import resolve_livery_resolution

    if getattr(kfps_render_backend, "_fh6_livery_render_cache_patched", False):
        return False

    original = kfps_render_backend.render_clivery_sections

    def cached_render_clivery_sections(source, *, game_folder=None, resolution=None, output_root=None, log=None):
        source_path = Path(source)
        try:
            spec = resolve_livery_resolution(resolution)
            root_str, payload = _cache_key(source_path, spec.key, game_folder)
            root = Path(root_str)
            cached = _load_cached_result(root, payload)
        except (OSError, ValueError, TypeError):
            cached = None
            root = None
            payload = None

        if cached is not None:
            if log:
                log(
                    f"Livery section cache hit: {cached.resolution_name} · "
                    f"{len(cached.png_paths)} rendered section(s); decode/render skipped."
                )
            return cached

        if log:
            log("Livery section cache miss: decoding/rendering this C_livery once.")
        result = original(
            source,
            game_folder=game_folder,
            resolution=resolution,
            output_root=output_root,
            log=log,
        )
        if root is not None and payload is not None:
            try:
                _store_result(root, payload, result)
            except Exception:
                pass
        return result

    kfps_render_backend.render_clivery_sections = cached_render_clivery_sections
    kfps_render_backend._fh6_livery_render_cache_patched = True

    integration = sys.modules.get(f"{__package__}.integration")
    if integration is not None and getattr(integration, "render_clivery_sections", None) is original:
        integration.render_clivery_sections = cached_render_clivery_sections
    return True
