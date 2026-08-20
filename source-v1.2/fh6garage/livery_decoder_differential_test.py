from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import threading
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QMessageBox


LEGACY_KFPS_COMMIT = "8965780b8966e09d2f2a17e4d0684cdd44d7437c"
CURRENT_KFPS_COMMIT = "004b3b61a57d901e65957b6099805835f91e32f6"
_PATCH_FLAG = "_fh6assistant_decoder_differential_test_v1"
_LEGACY_LOCK = threading.RLock()
_LEGACY_DECODER = None


def _runtime_roots() -> tuple[Path, ...]:
    roots = [Path(__file__).resolve().parents[1]]
    frozen = getattr(sys, "_MEIPASS", None)
    if frozen:
        roots.insert(0, Path(frozen))
    return tuple(dict.fromkeys(roots))


def _legacy_cgroup_dir() -> Path:
    for root in _runtime_roots():
        candidate = root / "vendor" / "kfps_legacy" / "tools" / "cgroup"
        if (candidate / "forza_source_decoder.py").is_file() and (candidate / "shape_identity.py").is_file():
            return candidate
    raise RuntimeError("KFPS 3.1.27 legacy decoder bundle is missing.")


def _load_legacy_decoder_module():
    global _LEGACY_DECODER
    with _LEGACY_LOCK:
        if _LEGACY_DECODER is not None:
            return _LEGACY_DECODER

        cgroup_dir = _legacy_cgroup_dir()
        decoder_path = cgroup_dir / "forza_source_decoder.py"
        module_name = "fh6assistant_kfps_3127_decoder"
        spec = importlib.util.spec_from_file_location(module_name, decoder_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("KFPS 3.1.27 decoder module could not be loaded.")

        # The 3.1.27 decoder has a direct-script fallback that imports
        # shape_identity from its own directory. Keep that path exposed only
        # while the isolated legacy module is initialized.
        previous_path = list(sys.path)
        try:
            sys.path.insert(0, str(cgroup_dir))
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
        finally:
            sys.path[:] = previous_path

        _apply_legacy_fh6assistant_decoder_rules(module)
        _LEGACY_DECODER = module
        return module


def _apply_legacy_fh6assistant_decoder_rules(decoder: Any) -> None:
    """Recreate the last 3.1.27 + FH6 Assistant decoder-only behavior.

    The clean 3.1.31 runtime remains untouched. We temporarily redirect the
    patch modules' backend lookup so each patch attaches to this isolated legacy
    module, then restore the real backend lookup and render cache identities.
    """
    from . import livery_preview
    from . import livery_preview_quality_pipeline as quality_pipeline
    from . import livery_preview_tiled_quality as tiled_quality
    from .livery_bare_parent_transform_fix import apply_livery_bare_parent_transform_fix
    from .livery_compact_shape_guard_patch import apply_livery_compact_shape_guard_patch
    from .livery_consecutive_transform_pair_fix import apply_livery_consecutive_transform_pair_fix
    from .livery_decoder_recovery_patch import apply_livery_decoder_recovery_patch
    from .livery_section_boundary_fix_patch import apply_livery_section_boundary_fix_patch

    real_load_backend = livery_preview._load_backend
    _current_decoder, renderer = real_load_backend()
    quality_version = getattr(quality_pipeline, "CACHE_VERSION", None)
    tiled_version = getattr(tiled_quality, "CACHE_VERSION", None)

    def legacy_backend():
        return decoder, renderer

    livery_preview._load_backend = legacy_backend
    try:
        apply_livery_compact_shape_guard_patch()
        apply_livery_section_boundary_fix_patch()
        apply_livery_decoder_recovery_patch()
        apply_livery_bare_parent_transform_fix()
        apply_livery_consecutive_transform_pair_fix()
    finally:
        livery_preview._load_backend = real_load_backend
        if quality_version is not None:
            quality_pipeline.CACHE_VERSION = quality_version
        if tiled_version is not None:
            tiled_quality.CACHE_VERSION = tiled_version


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    return repr(value)


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _layer_snapshot(layer: dict[str, Any], renderer: Any | None = None) -> dict[str, Any]:
    snapshot = {str(key): _jsonable(value) for key, value in layer.items()}
    type_code = _int_or_none(layer.get("type"))
    if renderer is not None and type_code is not None and not bool(layer.get("is_raster_logo")):
        resolver = getattr(renderer, "_resolve_vinyl_resource", None)
        if callable(resolver):
            try:
                resource = resolver(type_code, layer)
            except Exception:
                resource = None
            snapshot["resolved_resource_current_renderer"] = _jsonable(resource)
    return snapshot


def _semantic_key(layer: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(layer.get("source_section") or ""),
        _int_or_none(layer.get("source_offset")),
        _int_or_none(layer.get("type")),
        _int_or_none(layer.get("type_word")),
        _int_or_none(layer.get("shape_word")),
        bool(layer.get("mask")),
        bool(layer.get("is_raster_logo")),
        _int_or_none(layer.get("raster_id")),
        tuple(_jsonable(layer.get("data") or ())),
        tuple(_jsonable(layer.get("color") or ())),
    )


def _section_layers(decoded: Any, names: tuple[str, ...]) -> dict[str, list[dict[str, Any]]]:
    result = {name: [] for name in names}
    for layer in list(getattr(decoded, "layers", ()) or ()):
        if not isinstance(layer, dict):
            continue
        section = str(layer.get("source_section") or "")
        result.setdefault(section, []).append(layer)
    return result


def _first_order_divergence(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> dict[str, Any] | None:
    left_offsets = [_int_or_none(item.get("source_offset")) for item in left]
    right_offsets = [_int_or_none(item.get("source_offset")) for item in right]
    limit = min(len(left_offsets), len(right_offsets))
    for index in range(limit):
        if left_offsets[index] != right_offsets[index]:
            return {
                "index": index,
                "legacy_source_offset": left_offsets[index],
                "current_source_offset": right_offsets[index],
                "legacy_window": left_offsets[max(0, index - 3) : index + 4],
                "current_window": right_offsets[max(0, index - 3) : index + 4],
            }
    if len(left_offsets) != len(right_offsets):
        return {
            "index": limit,
            "legacy_source_offset": left_offsets[limit] if limit < len(left_offsets) else None,
            "current_source_offset": right_offsets[limit] if limit < len(right_offsets) else None,
            "legacy_window": left_offsets[max(0, limit - 3) : limit + 4],
            "current_window": right_offsets[max(0, limit - 3) : limit + 4],
        }
    return None


def _offset_buckets(layers: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    buckets: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for layer in layers:
        offset = _int_or_none(layer.get("source_offset"))
        if offset is not None:
            buckets[offset].append(layer)
    return dict(buckets)


def compare_decoded_sources(legacy: Any, current: Any, renderer: Any | None = None) -> dict[str, Any]:
    names = tuple(
        dict.fromkeys(
            [
                *getattr(_load_legacy_decoder_module(), "LIVERY_SECTION_NAMES", ()),
                *getattr(current, "report", {}).get("section_names", ()) if isinstance(getattr(current, "report", {}), dict) else (),
                "Front", "Back", "Top", "Left", "Right", "Spoiler",
                "FrontWindshield", "BackWindshield", "TopWindow", "LeftWindow", "RightWindow",
            ]
        )
    )
    legacy_sections = _section_layers(legacy, names)
    current_sections = _section_layers(current, names)

    section_summary: dict[str, Any] = {}
    for name in names:
        old_items = legacy_sections.get(name, [])
        new_items = current_sections.get(name, [])
        section_summary[name] = {
            "legacy_count": len(old_items),
            "current_count": len(new_items),
            "count_delta": len(new_items) - len(old_items),
            "first_order_divergence": _first_order_divergence(old_items, new_items),
        }

    legacy_layers = [item for items in legacy_sections.values() for item in items]
    current_layers = [item for items in current_sections.values() for item in items]
    legacy_by_offset = _offset_buckets(legacy_layers)
    current_by_offset = _offset_buckets(current_layers)
    all_offsets = sorted(set(legacy_by_offset) | set(current_by_offset))

    differences: list[dict[str, Any]] = []
    semantic_difference_count = 0
    missing_in_current = 0
    new_in_current = 0
    duplicate_offset_cases = 0

    for offset in all_offsets:
        old_bucket = legacy_by_offset.get(offset, [])
        new_bucket = current_by_offset.get(offset, [])
        if len(old_bucket) != 1 or len(new_bucket) != 1:
            duplicate_offset_cases += int(bool(old_bucket and new_bucket))
        if not old_bucket:
            new_in_current += len(new_bucket)
            differences.append({
                "kind": "only_current",
                "source_offset": offset,
                "current": [_layer_snapshot(item, renderer) for item in new_bucket],
            })
            continue
        if not new_bucket:
            missing_in_current += len(old_bucket)
            differences.append({
                "kind": "only_legacy",
                "source_offset": offset,
                "legacy": [_layer_snapshot(item, renderer) for item in old_bucket],
            })
            continue

        pair_count = min(len(old_bucket), len(new_bucket))
        for index in range(pair_count):
            old_layer = old_bucket[index]
            new_layer = new_bucket[index]
            if _semantic_key(old_layer) != _semantic_key(new_layer):
                semantic_difference_count += 1
                differences.append({
                    "kind": "semantic_difference",
                    "source_offset": offset,
                    "occurrence": index,
                    "legacy": _layer_snapshot(old_layer, renderer),
                    "current": _layer_snapshot(new_layer, renderer),
                })
        for item in old_bucket[pair_count:]:
            missing_in_current += 1
            differences.append({"kind": "only_legacy_duplicate", "source_offset": offset, "legacy": _layer_snapshot(item, renderer)})
        for item in new_bucket[pair_count:]:
            new_in_current += 1
            differences.append({"kind": "only_current_duplicate", "source_offset": offset, "current": _layer_snapshot(item, renderer)})

    # Keep the file bounded while preserving the earliest structural divergence,
    # which is normally the most useful parser forensic evidence.
    max_differences = 1200
    truncated = max(0, len(differences) - max_differences)
    if truncated:
        differences = differences[:max_differences]

    return {
        "summary": {
            "legacy_total_layers": len(list(getattr(legacy, "layers", ()) or ())),
            "current_total_layers": len(list(getattr(current, "layers", ()) or ())),
            "semantic_difference_count": semantic_difference_count,
            "only_legacy_count": missing_in_current,
            "only_current_count": new_in_current,
            "duplicate_offset_cases": duplicate_offset_cases,
            "reported_differences": len(differences),
            "truncated_difference_count": truncated,
        },
        "sections": section_summary,
        "differences": differences,
        "legacy_report": _jsonable(getattr(legacy, "report", {}) or {}),
        "current_report": _jsonable(getattr(current, "report", {}) or {}),
    }


def _decode_legacy(path: Path):
    from .livery_baseline_behavior_patch import normalize_decoded_layer_order

    decoder = _load_legacy_decoder_module()
    decoded = decoder.decode_forza_source(path, allow_locked=True, game="fh6")
    if str(getattr(decoded, "source_kind", "")).casefold() == "clivery":
        decoded, _changed = normalize_decoded_layer_order(decoded, tuple(decoder.LIVERY_SECTION_NAMES))
    return decoded


def _decode_current(path: Path):
    from .livery_preview import _load_backend

    decoder, renderer = _load_backend()
    decoded = decoder.decode_forza_source(path, allow_locked=True, game="fh6")
    return decoded, renderer


def _diagnostic_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) / "FH6GarageAnalyzer" if base else Path.home() / ".fh6garage"
    target = root / "decoder_differential"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _report_path(source: Path) -> Path:
    key = hashlib.sha1(str(source.resolve()).encode("utf-8", errors="replace")).hexdigest()[:12]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    parent = source.parent.name or source.stem
    safe_parent = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in parent)[:48]
    return _diagnostic_dir() / f"decoder-diff-{safe_parent}-{key}-{stamp}.json"


def generate_decoder_differential_report(path: Path | str) -> Path:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)

    legacy = _decode_legacy(source)
    current, renderer = _decode_current(source)
    comparison = compare_decoded_sources(legacy, current, renderer)
    payload = {
        "format": "FH6 Assistant decoder differential v1",
        "source": str(source),
        "legacy": {
            "kfps_commit": LEGACY_KFPS_COMMIT,
            "fh6assistant_rules": [
                "compact_shape_guard",
                "section_boundary_fix",
                "decoder_recovery",
                "bare_parent_transform_fix",
                "consecutive_transform_pair_fix",
                "source_offset_order_normalization",
            ],
        },
        "current": {
            "kfps_commit": CURRENT_KFPS_COMMIT,
            "fh6assistant_decoder_rules": [],
        },
        **comparison,
    }
    target = _report_path(source)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def apply_livery_decoder_differential_test(MainWindow: type) -> None:
    """Generate a decoder A/B JSON whenever a livery preview is opened."""
    if bool(getattr(MainWindow, _PATCH_FLAG, False)):
        return
    original = MainWindow._show_livery_image

    def show_with_decoder_diff(self, record):
        report_path: Path | None = None
        report_error: Exception | None = None
        livery_path = getattr(record, "livery_path", None)
        if livery_path:
            try:
                report_path = generate_decoder_differential_report(livery_path)
            except Exception as exc:  # diagnostic failure must not block preview
                report_error = exc

        result = original(self, record)

        if report_path is not None:
            QMessageBox.information(
                self,
                "Decoder Differential",
                "3.1.27 patched vs 3.1.31 clean 비교 JSON을 저장했습니다.\n\n"
                + str(report_path),
            )
        elif report_error is not None:
            QMessageBox.warning(
                self,
                "Decoder Differential",
                "비교 JSON 생성에 실패했습니다. 미리보기 자체에는 영향을 주지 않습니다.\n\n"
                + str(report_error),
            )
        return result

    MainWindow._show_livery_image = show_with_decoder_diff
    setattr(MainWindow, _PATCH_FLAG, True)
