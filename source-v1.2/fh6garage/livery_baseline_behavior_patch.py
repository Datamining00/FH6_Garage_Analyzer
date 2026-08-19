from __future__ import annotations

from dataclasses import replace
from typing import Any

from PySide6.QtCore import QEvent, QObject, QSettings, QTimer
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QFrame


_APPLIED = False
_FILTER = None
_DECODER_FLAG = "_fh6assistant_source_order_normalized_v1"
_ALLOWED_SCALES = (1, 2, 4, 8, 16)
_SCALE_KEY = "livery_preview_quality_scale_v14"


def _offset_value(layer: dict[str, Any]) -> int | None:
    try:
        value = layer.get("source_offset")
        if value is None:
            return None
        result = int(value)
        return result if result >= 0 else None
    except (TypeError, ValueError):
        return None


def normalize_decoded_layer_order(decoded: Any, section_names) -> tuple[Any, tuple[str, ...]]:
    """Use physical C_livery placement order as the section z-order.

    Group transforms are already flattened into each placement's final transform
    by the decoder.  Reordering only the finished placement records by their
    source offsets therefore preserves geometry while preventing tree-walk order
    from changing the serialized layer stack.  If offsets are incomplete or
    ambiguous, the decoder's original order is retained rather than guessed.
    """
    layers = [layer for layer in list(getattr(decoded, "layers", ()) or ()) if isinstance(layer, dict)]
    if not layers:
        return decoded, ()

    names = tuple(str(name) for name in section_names)
    by_section: dict[str, list[dict[str, Any]]] = {name: [] for name in names}
    unknown: list[dict[str, Any]] = []
    for layer in layers:
        section = str(layer.get("source_section") or "")
        if section in by_section:
            by_section[section].append(layer)
        else:
            unknown.append(layer)

    changed: list[str] = []
    rebuilt: list[dict[str, Any]] = []
    for section in names:
        items = by_section[section]
        offsets = [_offset_value(item) for item in items]
        if (
            len(items) > 1
            and all(offset is not None for offset in offsets)
            and len(set(offsets)) == len(offsets)
        ):
            ordered = [
                item
                for _offset, _index, item in sorted(
                    (int(offsets[index]), index, item) for index, item in enumerate(items)
                )
            ]
            if any(left is not right for left, right in zip(items, ordered)):
                items = ordered
                changed.append(section)
        rebuilt.extend(items)
    rebuilt.extend(unknown)

    decoded.layers = rebuilt
    if changed:
        report = dict(getattr(decoded, "report", {}) or {})
        warnings = [str(item) for item in list(report.get("warnings") or ())]
        warnings.extend(
            f"{section}: render layer order normalized by C_livery source offsets."
            for section in changed
        )
        report["warnings"] = list(dict.fromkeys(warnings))
        report["fh6assistant_source_order_sections"] = list(changed)
        decoded.report = report
    return decoded, tuple(changed)


def _section_state(expected_counts, decoded_sections, section: str, section_names):
    """Return exact/partial/fatal status for one requested section."""
    names = tuple(section_names)
    try:
        requested_index = names.index(str(section))
    except ValueError:
        return ("fatal", str(section), 0, 0, True)

    for index, name in enumerate(names[: requested_index + 1]):
        expected = int(expected_counts.get(name, 0))
        actual = len(decoded_sections.get(name, ()))
        if expected == actual:
            continue
        if index < requested_index:
            return ("fatal", name, expected, actual, True)
        if expected > 0 and 0 < actual < expected:
            return ("partial", name, expected, actual, False)
        return ("fatal", name, expected, actual, False)
    return ("exact", str(section), int(expected_counts.get(section, 0)), len(decoded_sections.get(section, ())), False)


def _install_decoder_order_normalization() -> None:
    from .livery_preview import _load_backend

    decoder, _renderer = _load_backend()
    if bool(getattr(decoder, _DECODER_FLAG, False)):
        return
    original = decoder.decode_forza_source

    def decode_ordered(path, allow_locked: bool = False, game: str | None = "fh6"):
        decoded = original(path, allow_locked=allow_locked, game=game)
        if str(getattr(decoded, "source_kind", "")).casefold() == "clivery":
            section_names = tuple(getattr(decoder, "LIVERY_SECTION_NAMES", ()))
            if section_names:
                decoded, _changed = normalize_decoded_layer_order(decoded, section_names)
        return decoded

    decoder.decode_forza_source = decode_ordered
    setattr(decoder, _DECODER_FLAG, True)


def _install_partial_render_policy() -> None:
    from . import livery_render_integrity_patch as integrity
    from . import livery_preview_tiled_quality as tiled
    from . import v1_4_preview_final_ui_patch as final_ui
    from .livery_analysis import LIVERY_SECTION_NAMES, analyze_livery_file
    from .livery_preview import LiveryPreviewError, decode_livery_preview

    def verify_partial_friendly(path, section: str) -> None:
        analysis = analyze_livery_file(path)
        decoded = decode_livery_preview(path)
        state, failed_section, expected, actual, cascaded = _section_state(
            analysis.section_counts,
            decoded.sections,
            section,
            LIVERY_SECTION_NAMES,
        )
        if state == "fatal":
            if cascaded:
                raise LiveryPreviewError(
                    f"정확 미리보기 중단: 앞선 {failed_section} 영역이 C_livery 기록 "
                    f"{expected:,}개 중 {actual:,}개만 구조적으로 해석되어 "
                    f"이후 {section} 영역의 시작 경계를 신뢰할 수 없습니다."
                )
            raise LiveryPreviewError(
                f"미리보기 중단: {failed_section} 영역의 C_livery 기록은 {expected:,}개지만 "
                f"{actual:,}개가 해석되었습니다. 안전한 부분 렌더 조건에 해당하지 않습니다."
            )

        # A shortage in the requested section itself is allowed. Raster claims
        # for the placements that did decode must still agree with source bytes.
        integrity._verify_raster_provenance(path, section, decoded.sections.get(section, ()))

    integrity.verify_section_integrity = verify_partial_friendly

    original_scaled = tiled.render_livery_section_scaled

    def render_scaled_partial(path, section: str, scale: int = 4):
        analysis = analyze_livery_file(path)
        decoded = decode_livery_preview(path)
        state, _name, expected, actual, _cascaded = _section_state(
            analysis.section_counts,
            decoded.sections,
            section,
            LIVERY_SECTION_NAMES,
        )
        result = original_scaled(path, section, scale)
        if state == "partial":
            warning = (
                f"{section}: 부분 미리보기 — C_livery 기록 {expected:,}개 중 "
                f"구조적으로 해석된 {actual:,}개만 렌더링했습니다."
            )
            return replace(
                result,
                placement_count=int(actual),
                warnings=tuple(dict.fromkeys([*result.warnings, warning])),
            )
        return result

    tiled.render_livery_section_scaled = render_scaled_partial
    final_ui.render_livery_section_scaled = render_scaled_partial


def _saved_scale() -> int:
    settings = QSettings()
    try:
        value = int(settings.value(_SCALE_KEY, 4))
    except (TypeError, ValueError):
        value = 4
    return value if value in _ALLOWED_SCALES else 4


def _persist_scale(combo: QComboBox) -> None:
    try:
        value = int(combo.currentData())
    except (TypeError, ValueError):
        return
    if value not in _ALLOWED_SCALES:
        return
    settings = QSettings()
    settings.setValue(_SCALE_KEY, value)
    settings.sync()


def _patch_scale_combo(dialog: QDialog) -> None:
    top_bar = dialog.findChild(QFrame, "liveryPreviewTopBar")
    if top_bar is None:
        return
    combo = top_bar.findChild(QComboBox)
    if combo is None:
        return

    if combo.findData(1) < 0:
        combo.insertItem(0, "1× · 빠름", 1)
    wanted = _saved_scale()
    target = combo.findData(wanted)
    if target >= 0 and combo.currentIndex() != target:
        combo.setCurrentIndex(target)
    combo.setEnabled(True)

    if not bool(combo.property("fh6_persistent_scale_bound")):
        combo.setProperty("fh6_persistent_scale_bound", True)
        combo.currentIndexChanged.connect(lambda _index, target_combo=combo: _persist_scale(target_combo))
    _persist_scale(combo)


class _ScalePersistenceFilter(QObject):
    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Show and isinstance(watched, QDialog):
            # The existing UI-polish filter migrates the old quick/quality
            # controls on the same Show event. Apply persistence just after it.
            QTimer.singleShot(20, lambda dialog=watched: _patch_scale_combo(dialog))
        return False


def _install_scale_persistence() -> None:
    global _FILTER
    app = QApplication.instance()
    if app is None or _FILTER is not None:
        return
    _FILTER = _ScalePersistenceFilter(app)
    app.installEventFilter(_FILTER)


def _clear_preview_caches() -> None:
    try:
        from .livery_preview import clear_livery_preview_cache
        clear_livery_preview_cache()
    except Exception:
        pass
    try:
        from .livery_preview_quality_pipeline import clear_quality_pipeline_cache
        clear_quality_pipeline_cache()
    except Exception:
        pass
    try:
        from .livery_preview_tiled_quality import clear_tiled_quality_cache
        clear_tiled_quality_cache()
    except Exception:
        pass


def apply_livery_baseline_behavior_patch() -> None:
    """Apply partial rendering, persistent scale and source-order z stacking."""
    global _APPLIED
    if _APPLIED:
        return
    _install_decoder_order_normalization()
    _install_partial_render_policy()
    _install_scale_persistence()
    _clear_preview_caches()
    _APPLIED = True
