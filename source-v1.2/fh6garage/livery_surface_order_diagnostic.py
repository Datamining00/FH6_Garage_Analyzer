from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


_APPLIED = False
_PATCH_FLAG = "_fh6assistant_surface_order_diagnostic_v1"
_WARNING_PREFIX = "[FH6_SURFACE_ORDER_DIAG]"
_WRITE_LOCK = threading.RLock()


def _app_data_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "FH6GarageAnalyzer"
    return Path.home() / ".fh6garage"


def _diagnostic_dir() -> Path:
    return _app_data_dir() / "livery_surface_order_diagnostics"


def _source_offset(layer: dict[str, Any]) -> int | None:
    try:
        value = layer.get("source_offset")
        if value is None:
            return None
        offset = int(value)
        return offset if offset >= 0 else None
    except (TypeError, ValueError):
        return None


def _is_mask(layer: dict[str, Any]) -> bool:
    for key in ("mask", "is_mask", "isMask"):
        if bool(layer.get(key)):
            return True
    return False


def _safe_number(value: Any) -> int | float | str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value != value:
            return "nan"
        if value == float("inf"):
            return "inf"
        if value == float("-inf"):
            return "-inf"
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return str(value)


def _compact_layer_record(
    layer: dict[str, Any],
    *,
    original_index: int,
    normalized_index: int | None,
) -> dict[str, Any]:
    data = list(layer.get("data") or [])
    color = layer.get("color")
    record: dict[str, Any] = {
        "original_index": int(original_index),
        "normalized_index": int(normalized_index) if normalized_index is not None else None,
        "source_offset": _source_offset(layer),
        "type": _safe_number(layer.get("type")),
        "mask": _is_mask(layer),
        "is_raster_logo": bool(layer.get("is_raster_logo")),
    }
    if layer.get("raster_id") is not None:
        record["raster_id"] = _safe_number(layer.get("raster_id"))
    if data:
        record["data"] = [_safe_number(item) for item in data[:10]]
    if isinstance(color, (list, tuple)):
        record["color"] = [_safe_number(item) for item in list(color)[:4]]
    return record


def _section_diagnostic(
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
) -> dict[str, Any]:
    after_positions = {id(layer): index for index, layer in enumerate(after)}
    offsets = [_source_offset(layer) for layer in before]
    offsets_complete = bool(before) and all(value is not None for value in offsets)
    offsets_unique = offsets_complete and len(set(offsets)) == len(offsets)

    descents = 0
    if offsets_complete:
        numeric_offsets = [int(value) for value in offsets if value is not None]
        descents = sum(
            1 for left, right in zip(numeric_offsets, numeric_offsets[1:]) if left > right
        )

    moved = 0
    moved_masks = 0
    moved_visible = 0
    max_displacement = 0
    records: list[dict[str, Any]] = []
    for original_index, layer in enumerate(before):
        normalized_index = after_positions.get(id(layer))
        if normalized_index is not None and normalized_index != original_index:
            moved += 1
            displacement = abs(int(normalized_index) - int(original_index))
            max_displacement = max(max_displacement, displacement)
            if _is_mask(layer):
                moved_masks += 1
            else:
                moved_visible += 1
        records.append(
            _compact_layer_record(
                layer,
                original_index=original_index,
                normalized_index=normalized_index,
            )
        )

    changed = len(before) != len(after) or any(
        index >= len(after) or before[index] is not after[index]
        for index in range(len(before))
    )
    if moved_masks:
        risk = "high"
    elif changed:
        risk = "medium"
    else:
        risk = "none"

    return {
        "layer_count": len(before),
        "source_offsets_complete": offsets_complete,
        "source_offsets_unique": offsets_unique,
        "source_offset_descents": descents,
        "order_changed": changed,
        "moved_layer_count": moved,
        "moved_visible_layer_count": moved_visible,
        "moved_mask_layer_count": moved_masks,
        "max_index_displacement": max_displacement,
        "stacking_risk": risk,
        "layers": records,
    }


def build_surface_order_diagnostic(
    before_layers: list[dict[str, Any]],
    after_layers: list[dict[str, Any]],
    section_names,
) -> dict[str, Any]:
    names = tuple(str(name) for name in section_names)
    before_by_section: dict[str, list[dict[str, Any]]] = {name: [] for name in names}
    after_by_section: dict[str, list[dict[str, Any]]] = {name: [] for name in names}

    for layer in before_layers:
        section = str(layer.get("source_section") or "")
        if section in before_by_section:
            before_by_section[section].append(layer)
    for layer in after_layers:
        section = str(layer.get("source_section") or "")
        if section in after_by_section:
            after_by_section[section].append(layer)

    sections = {
        name: _section_diagnostic(before_by_section[name], after_by_section[name])
        for name in names
    }
    return {
        "behavior_changed_by_diagnostic_patch": False,
        "purpose": (
            "Record decoder order versus the Warning Only Render Test source-offset "
            "normalization. The diagnostic patch does not reverse or reorder layers."
        ),
        "sections": sections,
    }


def _diagnostic_identity(source: Path) -> str:
    try:
        stat = source.stat()
        payload = f"{source.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"
    except OSError:
        payload = str(source)
    return hashlib.sha256(payload.encode("utf-8", errors="surrogatepass")).hexdigest()[:20]


def _write_diagnostic(decoded: Any, diagnostic: dict[str, Any]) -> Path | None:
    source_text = str(getattr(decoded, "source_path", "") or "")
    if not source_text:
        return None
    source = Path(source_text)
    payload = dict(diagnostic)
    payload["diagnostic_version"] = 1
    payload["created_utc"] = datetime.now(timezone.utc).isoformat()
    payload["source_name"] = source.name
    payload["source_path"] = source_text

    destination = _diagnostic_dir() / f"{source.stem or 'C_livery'}-{_diagnostic_identity(source)}.json"
    temporary = destination.with_suffix(".tmp")
    try:
        with _WRITE_LOCK:
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temporary, destination)
        return destination
    except OSError:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        return None


def _summary_warning(diagnostic: dict[str, Any], log_path: Path | None) -> str | None:
    sections = diagnostic.get("sections")
    if not isinstance(sections, dict):
        return None

    changed: list[str] = []
    preferred = ("Left", "Right", "Front", "Back", "Top")
    names = [*preferred, *(name for name in sections if name not in preferred)]
    for name in names:
        section = sections.get(name)
        if not isinstance(section, dict) or not bool(section.get("order_changed")):
            continue
        moved = int(section.get("moved_layer_count", 0) or 0)
        masks = int(section.get("moved_mask_layer_count", 0) or 0)
        descents = int(section.get("source_offset_descents", 0) or 0)
        changed.append(f"{name}: moved={moved}, masks={masks}, offset-descents={descents}")

    if not changed:
        return None
    detail = "; ".join(changed[:6])
    if len(changed) > 6:
        detail += f"; +{len(changed) - 6} sections"
    location = f" Log: {log_path}" if log_path is not None else ""
    return f"{_WARNING_PREFIX} {detail}.{location}"


def install_surface_order_diagnostic() -> None:
    """Instrument Warning Only Render Test stacking without changing its result.

    This wrapper is installed before apply_livery_baseline_behavior_patch(). The
    baseline patch therefore still performs its existing ascending source_offset
    normalization. We only snapshot the decoder order, compare it with the
    baseline result, write a JSON diagnostic, and append a warning summary.
    """
    global _APPLIED
    if _APPLIED:
        return

    from . import livery_baseline_behavior_patch as baseline

    original: Callable[..., tuple[Any, tuple[str, ...]]] = baseline.normalize_decoded_layer_order
    if bool(getattr(original, _PATCH_FLAG, False)):
        _APPLIED = True
        return

    def normalize_with_diagnostic(decoded: Any, section_names):
        before_layers = [
            layer for layer in list(getattr(decoded, "layers", ()) or ())
            if isinstance(layer, dict)
        ]
        normalized, changed = original(decoded, section_names)
        after_layers = [
            layer for layer in list(getattr(normalized, "layers", ()) or ())
            if isinstance(layer, dict)
        ]

        try:
            diagnostic = build_surface_order_diagnostic(
                before_layers,
                after_layers,
                section_names,
            )
            log_path = _write_diagnostic(normalized, diagnostic)
            warning = _summary_warning(diagnostic, log_path)
            if warning:
                report = dict(getattr(normalized, "report", {}) or {})
                warnings = [str(item) for item in list(report.get("warnings") or ())]
                warnings.append(warning)
                report["warnings"] = list(dict.fromkeys(warnings))
                report["fh6assistant_surface_order_diagnostic"] = diagnostic
                if log_path is not None:
                    report["fh6assistant_surface_order_diagnostic_path"] = str(log_path)
                normalized.report = report
        except Exception as exc:
            # Diagnostics must never change whether a livery can be decoded or rendered.
            report = dict(getattr(normalized, "report", {}) or {})
            warnings = [str(item) for item in list(report.get("warnings") or ())]
            warnings.append(f"{_WARNING_PREFIX} diagnostic collection failed: {exc}")
            report["warnings"] = list(dict.fromkeys(warnings))
            normalized.report = report

        return normalized, changed

    setattr(normalize_with_diagnostic, _PATCH_FLAG, True)
    baseline.normalize_decoded_layer_order = normalize_with_diagnostic
    _APPLIED = True
