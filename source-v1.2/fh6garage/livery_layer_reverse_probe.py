from __future__ import annotations

import threading
from dataclasses import replace
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QFrame, QPushButton


_APPLIED = False
_FILTER = None
_RENDER_LOCK = threading.RLock()
_PENDING_LOCK = threading.RLock()
_PENDING_REVERSE: set[tuple[str, int]] = set()
_BUTTON_NAME = "liveryPreviewReverseLayersButton"


def _normalize_key(section: str, scale: int) -> tuple[str, int]:
    try:
        normalized_scale = int(scale)
    except (TypeError, ValueError):
        normalized_scale = 4
    return str(section), normalized_scale


def request_transient_reverse(section: str, scale: int) -> None:
    """Arm exactly one reverse-order render for the requested section/scale."""
    with _PENDING_LOCK:
        _PENDING_REVERSE.add(_normalize_key(section, scale))


def consume_transient_reverse(section: str, scale: int) -> bool:
    key = _normalize_key(section, scale)
    with _PENDING_LOCK:
        if key not in _PENDING_REVERSE:
            return False
        _PENDING_REVERSE.remove(key)
        return True


def _reverse_container(values):
    reversed_values = tuple(reversed(tuple(values)))
    if isinstance(values, tuple):
        return reversed_values
    if isinstance(values, list):
        return list(reversed_values)
    return reversed_values


def _render_reversed_uncached(original_scaled, path, section: str, scale: int):
    """Render one section in reverse z-order without reading or writing preview PNG caches.

    This is intentionally a probe path. The decoded section is reversed only
    while the render call is executing, then restored. Both memory render caches
    and disk PNG caches are bypassed so a probe can never replace the normal
    preview cached for the same livery/section/scale.
    """
    from . import livery_preview_quality_pipeline as quality
    from . import livery_preview_tiled_quality as tiled
    from .livery_preview import LiveryPreviewError, _decode_cached, _file_signature

    source = Path(path)
    signature = _file_signature(source)
    decoded = _decode_cached(*signature)
    original_layers = decoded.sections.get(str(section))
    if not original_layers:
        raise LiveryPreviewError("이 영역에는 역전 시험에 사용할 해석된 레이어가 없습니다.")

    reversed_layers = _reverse_container(original_layers)

    old_quality_read = quality._read_disk_cache
    old_quality_write = quality._write_disk_cache
    old_tiled_read = tiled._read_disk_cache
    old_tiled_write = tiled._write_disk_cache

    def no_cache_read(*_args: Any, **_kwargs: Any):
        return None

    def no_cache_write(*_args: Any, **_kwargs: Any) -> None:
        return None

    # Flush both memory caches before the temporary layer substitution. This
    # guarantees that the probe cannot return a previously cached normal image.
    quality.clear_quality_pipeline_cache()
    tiled.clear_tiled_quality_cache()
    decoded.sections[str(section)] = reversed_layers
    quality._read_disk_cache = no_cache_read
    quality._write_disk_cache = no_cache_write
    tiled._read_disk_cache = no_cache_read
    tiled._write_disk_cache = no_cache_write

    try:
        result = original_scaled(path, section, scale)
        note = "레이어 순서 역전 시험 렌더 — 이 결과는 캐시에 저장하지 않았습니다."
        return replace(
            result,
            warnings=tuple(dict.fromkeys([*result.warnings, note])),
        )
    finally:
        decoded.sections[str(section)] = original_layers
        quality._read_disk_cache = old_quality_read
        quality._write_disk_cache = old_quality_write
        tiled._read_disk_cache = old_tiled_read
        tiled._write_disk_cache = old_tiled_write
        # The reverse result may have populated an lru_cache even though disk
        # writes were disabled. Drop it immediately so the next normal request
        # always uses the normal layer order/cache contract.
        quality.clear_quality_pipeline_cache()
        tiled.clear_tiled_quality_cache()


def _install_renderer_probe() -> None:
    from . import livery_preview_tiled_quality as tiled
    from . import v1_4_preview_final_ui_patch as final_ui

    original_scaled = final_ui.render_livery_section_scaled
    if bool(getattr(original_scaled, "_fh6_reverse_probe_wrapper", False)):
        return

    def render_with_optional_reverse(path, section: str, scale: int = 4):
        with _RENDER_LOCK:
            if consume_transient_reverse(section, scale):
                return _render_reversed_uncached(original_scaled, path, section, scale)
            return original_scaled(path, section, scale)

    render_with_optional_reverse._fh6_reverse_probe_wrapper = True
    final_ui.render_livery_section_scaled = render_with_optional_reverse
    # Keep any other runtime caller routed through the same one-shot policy.
    tiled.render_livery_section_scaled = render_with_optional_reverse


def _selected_section(dialog: QDialog) -> str | None:
    try:
        from .livery_baseline_behavior_patch import (
            _find_preview_status_label,
            _section_from_status_text,
        )

        status = _find_preview_status_label(dialog)
        if status is None:
            return None
        return _section_from_status_text(str(status.text() or ""))
    except Exception:
        return None


def _restore_button(button: QPushButton) -> None:
    if button is None:
        return
    button.setEnabled(True)
    button.setText("레이어 순서 역전")


def _trigger_probe(dialog: QDialog, button: QPushButton) -> None:
    section = _selected_section(dialog)
    top_bar = dialog.findChild(QFrame, "liveryPreviewTopBar")
    combo = top_bar.findChild(QComboBox) if top_bar is not None else None
    if section is None or combo is None or combo.currentIndex() < 0:
        button.setText("면을 먼저 선택")
        QTimer.singleShot(900, lambda target=button: _restore_button(target))
        return

    try:
        scale = int(combo.currentData())
    except (TypeError, ValueError):
        scale = 4

    original_index = combo.currentIndex()
    alternate_index = next(
        (index for index in range(combo.count()) if index != original_index),
        -1,
    )
    if alternate_index < 0:
        button.setText("재렌더 불가")
        QTimer.singleShot(900, lambda target=button: _restore_button(target))
        return

    # Arm only the original section/scale. The temporary scale change exists
    # solely to invoke the dialog's existing clear-and-rerender path; it cannot
    # consume this request because its scale differs.
    request_transient_reverse(section, scale)
    button.setEnabled(False)
    button.setText("역전 렌더 중…")

    combo.setCurrentIndex(alternate_index)

    def return_to_original() -> None:
        combo.setCurrentIndex(original_index)
        # Rendering can take much longer than this; the button may be used again
        # after the request was submitted. The render request itself remains
        # strictly one-shot and is never persisted.
        QTimer.singleShot(900, lambda target=button: _restore_button(target))

    QTimer.singleShot(0, return_to_original)


def _inject_reverse_button(dialog: QDialog) -> None:
    top_bar = dialog.findChild(QFrame, "liveryPreviewTopBar")
    if top_bar is None or top_bar.findChild(QPushButton, _BUTTON_NAME) is not None:
        return
    layout = top_bar.layout()
    if layout is None:
        return

    try:
        from .livery_preview_ui_polish import _LIGHT_BUTTON_STYLE
    except Exception:
        _LIGHT_BUTTON_STYLE = ""

    button = QPushButton("레이어 순서 역전", top_bar)
    button.setObjectName(_BUTTON_NAME)
    button.setCheckable(False)
    button.setToolTip(
        "현재 선택한 면만 레이어 순서를 역전해 다시 렌더합니다. "
        "이 시험 상태와 결과는 저장하지 않습니다."
    )
    if _LIGHT_BUTTON_STYLE:
        button.setStyleSheet(_LIGHT_BUTTON_STYLE)
    button.clicked.connect(lambda _checked=False, d=dialog, b=button: _trigger_probe(d, b))

    # Put the probe immediately before the existing overflow menu when possible.
    more = top_bar.findChild(QObject, "liveryPreviewMoreButton")
    more_index = layout.indexOf(more) if more is not None else -1
    insert_widget = getattr(layout, "insertWidget", None)
    if more_index >= 0 and callable(insert_widget):
        insert_widget(more_index, button)
    else:
        layout.addWidget(button)


class _ReverseProbeFilter(QObject):
    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Show and isinstance(watched, QDialog):
            # Preview UI polish and scale migration run first on Show. Inject
            # after those patches have finalized the top-bar controls.
            QTimer.singleShot(80, lambda dialog=watched: _inject_reverse_button(dialog))
        return False


def _install_button_probe() -> None:
    global _FILTER
    app = QApplication.instance()
    if app is None or _FILTER is not None:
        return
    _FILTER = _ReverseProbeFilter(app)
    app.installEventFilter(_FILTER)


def apply_livery_layer_reverse_probe() -> None:
    """Enable a non-persistent one-shot layer-order reverse test button."""
    global _APPLIED
    if _APPLIED:
        return
    _install_renderer_probe()
    _install_button_probe()
    _APPLIED = True
