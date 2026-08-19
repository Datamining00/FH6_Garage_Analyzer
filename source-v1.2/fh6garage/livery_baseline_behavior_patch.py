from __future__ import annotations

from dataclasses import replace
from typing import Any

from PySide6.QtCore import QEvent, QObject, QSettings, QTimer
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QFrame, QLabel


_APPLIED = False
_FILTER = None
_DECODER_FLAG = "_fh6assistant_source_order_normalized_v1"
_ALLOWED_SCALES = (1, 2, 4, 8, 16)
_SCALE_KEY = "livery_preview_quality_scale_v14"
INACCURATE_WARNING_PREFIX = "[FH6_INACCURATE_PREVIEW]"
INACCURATE_UI_TEXT_KO = "⚠ 구조 해석 경고가 있어 정확하지 않을 수 있습니다."
INACCURATE_UI_TEXT_EN = "⚠ Structural decode warning; this preview may be inaccurate."
_LATEST_INACCURATE_BY_SECTION: dict[str, str] = {}
_STATUS_LABEL_TO_SECTION = {
    "전면": "Front",
    "후면": "Back",
    "상단": "Top",
    "왼쪽": "Left",
    "오른쪽": "Right",
    "스포일러": "Spoiler",
    "앞유리": "FrontWindshield",
    "뒷유리": "BackWindshield",
    "상단 유리": "TopWindow",
    "왼쪽 유리": "LeftWindow",
    "오른쪽 유리": "RightWindow",
    "Front": "Front",
    "Back": "Back",
    "Top": "Top",
    "Left": "Left",
    "Right": "Right",
    "Spoiler": "Spoiler",
    "Front Windshield": "FrontWindshield",
    "Back Windshield": "BackWindshield",
    "Top Window": "TopWindow",
    "Left Window": "LeftWindow",
    "Right Window": "RightWindow",
}


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
    """Use physical C_livery placement order as section z-order when provable.

    Group transforms are already flattened into each placement's final transform
    by the decoder. Reordering only finished placement records by their source
    offsets preserves geometry while preventing tree-walk order from changing
    the serialized layer stack. If offsets are incomplete or ambiguous, retain
    the decoder's original order rather than guessing.
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


def _section_issues(expected_counts, decoded_sections, section: str, section_names) -> tuple[tuple[str, int, int], ...]:
    """Return count mismatches that can affect the requested section.

    These are diagnostics only. They never block rendering. If the requested
    section has usable decoded layers, the renderer shows them and the UI marks
    the result as potentially inaccurate.
    """
    names = tuple(section_names)
    try:
        requested_index = names.index(str(section))
    except ValueError:
        return ((str(section), 0, 0),)

    issues: list[tuple[str, int, int]] = []
    for name in names[: requested_index + 1]:
        expected = int(expected_counts.get(name, 0))
        actual = len(decoded_sections.get(name, ()))
        if expected != actual:
            issues.append((name, expected, actual))
    return tuple(issues)


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


def _install_warning_only_integrity_policy() -> None:
    from . import livery_render_integrity_patch as integrity
    from . import livery_preview_tiled_quality as tiled
    from . import v1_4_preview_final_ui_patch as final_ui
    from .livery_analysis import LIVERY_SECTION_NAMES, analyze_livery_file
    from .livery_preview import LiveryPreviewError, decode_livery_preview

    def verify_warning_only(path, section: str) -> None:
        # Section count/boundary mismatches no longer fail closed. The actual
        # renderer still fails naturally when no decoded layers or mandatory
        # rendering assets exist.
        return None

    integrity.verify_section_integrity = verify_warning_only

    original_scaled = tiled.render_livery_section_scaled

    def render_scaled_warning_only(path, section: str, scale: int = 4):
        _LATEST_INACCURATE_BY_SECTION[str(section)] = ""
        analysis = analyze_livery_file(path)
        decoded = decode_livery_preview(path)
        issues = _section_issues(
            analysis.section_counts,
            decoded.sections,
            section,
            LIVERY_SECTION_NAMES,
        )
        diagnostic_details: list[str] = []
        for name, expected, actual in issues:
            diagnostic_details.append(f"{name} {expected:,}->{actual:,}")

        # Raster provenance is also an integrity diagnostic. Do not stop a
        # preview merely because that provenance cannot be proven; record the
        # uncertainty and let the renderer decide whether available assets are
        # sufficient to produce an image.
        try:
            integrity._verify_raster_provenance(path, section, decoded.sections.get(section, ()))
        except LiveryPreviewError as exc:
            diagnostic_details.append(f"raster provenance: {exc}")

        result = original_scaled(path, section, scale)
        actual_count = len(decoded.sections.get(section, ()))
        if diagnostic_details:
            detail = "; ".join(diagnostic_details)
            warning = (
                f"{INACCURATE_WARNING_PREFIX} 구조 해석 경고가 있어 정확하지 않을 수 있습니다. "
                f"{detail}"
            )
            _LATEST_INACCURATE_BY_SECTION[str(section)] = detail
            return replace(
                result,
                placement_count=int(actual_count),
                warnings=tuple(dict.fromkeys([*result.warnings, warning])),
            )
        return result

    tiled.render_livery_section_scaled = render_scaled_warning_only
    final_ui.render_livery_section_scaled = render_scaled_warning_only


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


def _find_preview_status_label(dialog: QDialog) -> QLabel | None:
    for label in dialog.findChildren(QLabel):
        style = str(label.styleSheet() or "").casefold()
        if "#6f7380" in style and "font-size:9pt" in style.replace(" ", ""):
            return label
    # Style sheets may be normalized by Qt. Fall back to the small centered
    # status label whose text begins with a known section/thumbnail label.
    for label in dialog.findChildren(QLabel):
        text = str(label.text() or "").strip()
        prefix = text.split(" · ", 1)[0]
        if prefix in _STATUS_LABEL_TO_SECTION or prefix in {"썸네일", "Thumbnail"}:
            return label
    return None


def _section_from_status_text(text: str) -> str | None:
    value = str(text or "").strip()
    for suffix in (f" · {INACCURATE_UI_TEXT_KO}", f" · {INACCURATE_UI_TEXT_EN}"):
        if value.endswith(suffix):
            value = value[: -len(suffix)]
            break
    prefix = value.split(" · ", 1)[0].strip()
    return _STATUS_LABEL_TO_SECTION.get(prefix)


def _patch_warning_monitor(dialog: QDialog) -> None:
    if bool(dialog.property("fh6_accuracy_warning_monitor")):
        return
    status = _find_preview_status_label(dialog)
    if status is None:
        return
    dialog.setProperty("fh6_accuracy_warning_monitor", True)

    timer = QTimer(dialog)
    timer.setInterval(120)

    def refresh() -> None:
        text = str(status.text() or "")
        for suffix in (f" · {INACCURATE_UI_TEXT_KO}", f" · {INACCURATE_UI_TEXT_EN}"):
            if text.endswith(suffix):
                text = text[: -len(suffix)]
                break
        section = _section_from_status_text(text)
        detail = _LATEST_INACCURATE_BY_SECTION.get(section or "", "")
        korean = any(token in text for token in _STATUS_LABEL_TO_SECTION if any("가" <= ch <= "힣" for ch in token)) or text.startswith("썸네일")
        if section and detail:
            warning_text = INACCURATE_UI_TEXT_KO if korean else INACCURATE_UI_TEXT_EN
            status.setText(f"{text} · {warning_text}")
            status.setToolTip(detail)
            status.setStyleSheet("color:#ad6400;font-size:9pt;font-weight:600;")
        else:
            status.setText(text)
            status.setToolTip("")
            status.setStyleSheet("color:#6f7380;font-size:9pt;")

    timer.timeout.connect(refresh)
    timer.start()
    dialog.setProperty("fh6_accuracy_warning_timer", timer)


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
            QTimer.singleShot(20, lambda dialog=watched: _patch_scale_combo(dialog))
            QTimer.singleShot(30, lambda dialog=watched: _patch_warning_monitor(dialog))
        return False


def _install_scale_persistence_and_warning_ui() -> None:
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
    """Apply warning-only integrity, persistent scale and source-order stacking."""
    global _APPLIED
    if _APPLIED:
        return
    _install_decoder_order_normalization()
    _install_warning_only_integrity_policy()
    _install_scale_persistence_and_warning_ui()
    _clear_preview_caches()
    _APPLIED = True
