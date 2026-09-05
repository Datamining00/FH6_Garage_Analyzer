from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QObject, QSize, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QGridLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from . import v1_3_2_alias_manager_change_card_fix as _alias_fix
from . import v1_3_2_change_dialog_runtime_fix as _legacy_runtime
from . import v1_3_2_memory_state_patch as _memory_state
from .card_icons import icon as card_icon, toggle_icon as card_toggle_icon
from .i18n import get_language, tr
from .ui import CopyValueLabel


ICON_SIZE = 20
EDGE_MARGIN = 5
BUTTON_GAP = 3
ROW_HEIGHT = 34
THUMBNAIL_MIN_HEIGHT = 240
CARD_MIN_HEIGHT = 325
CARD_METADATA_HEIGHT = 80
CLASSIFICATION_ACTIVE_COLORS = {
    "check": "#16a34a",
    "triangle": "#d97706",
    "excluded": "#dc2626",
}
LOCK_ACTIVE_BACKGROUND = "#6e4bf2"
LOCK_ACTIVE_BORDER = "#5f39d8"
LOCK_ACTIVE_ICON = "#ffffff"


def _txt(ko: str, en: str) -> str:
    return ko if (get_language() or "ko").lower().startswith("ko") else en


def _line_icon(kind: str, *, active: bool = False) -> QIcon:
    mapped = "memo_written" if kind == "memo" and active else kind
    if kind == "lock":
        mapped = "lock" if active else "unlock"
        return card_icon(mapped, LOCK_ACTIVE_ICON if active else "#555a68")
    return card_icon(mapped, "#6e4bf2" if active else "#555a68")


def _card_overlay(card: Any) -> QWidget | None:
    image = getattr(card, "_fh6_image_label", None)
    host = image.parentWidget() if image is not None else None
    stack = host.layout() if host is not None else None
    overlay = stack.currentWidget() if stack is not None and hasattr(stack, "currentWidget") else None
    return overlay if isinstance(overlay, QWidget) else None


def _disable_old_aligners(card: Any, overlay: QWidget) -> None:
    for name in (
        "_fh6_card_action_aligner",
        "_fh6_four_left_action_aligner",
        "_fh6_applied_state_aligner",
        "_fh6_hide_aligner",
    ):
        aligner = getattr(card, name, None)
        if isinstance(aligner, QObject):
            overlay.removeEventFilter(aligner)
            # Older patches also queued direct QTimer callbacks. Removing the
            # event filter does not cancel those already queued calls, so make
            # their eventual reposition harmless as well.
            if hasattr(aligner, "overlay"):
                aligner.overlay = None
            if hasattr(aligner, "card"):
                aligner.card = None
            try:
                aligner.reposition = lambda: None
            except (AttributeError, RuntimeError, TypeError):
                pass


def _placeholder_button(overlay: QWidget, name: str, icon: QIcon, tooltip: str) -> QToolButton:
    button = QToolButton(overlay)
    button.setObjectName(name)
    button.setFixedSize(30, 30)
    button.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
    button.setIcon(icon)
    button.setToolTip(tooltip)
    button.setStyleSheet(
        "QToolButton { background:rgba(255,255,255,238); border:1px solid #dfe1e8; "
        "border-radius:8px; padding:0; }"
        "QToolButton:hover { border-color:#8c74ee; background:#f2edff; }"
        f"QToolButton:checked {{ border-color:{LOCK_ACTIVE_BORDER}; background:{LOCK_ACTIVE_BACKGROUND}; }}"
    )
    return button


def _unique_placeholder(card: Any, overlay: QWidget, attribute: str, name: str, kind: str, tooltip: str) -> QToolButton:
    existing = getattr(card, attribute, None)
    if isinstance(existing, QToolButton):
        return existing
    matches = overlay.findChildren(QToolButton, name)
    button = matches[0] if matches else _placeholder_button(overlay, name, _line_icon(kind), tooltip)
    for duplicate in matches[1:]:
        duplicate.hide()
        duplicate.deleteLater()
    setattr(card, attribute, button)
    return button


def _normalize_metadata(card: Any) -> None:
    label_map = {
        tr("card.vehicle_label"): _txt("차량", "Vehicle"),
        tr("card.creator_label"): _txt("제작", "Creator"),
        tr("card.title_label"): _txt("제목", "Title"),
    }
    for label in card.findChildren(CopyValueLabel):
        replacement = label_map.get(label.prefix)
        if replacement is None:
            continue
        label.prefix = replacement
        label.setCopyValue(label.copy_value)
        label.setToolTip(
            tr("common.copy_value_detail", label=replacement, value=label.copy_value)
        )
        label.setStyleSheet(
            "QLabel { background:transparent; color:#171924; border:0; "
            "padding:0 2px; font-size:10.5pt; font-weight:600; }"
        )
        label.setFixedHeight(24)

    source = card.findChild(QLabel, "fh6AcquisitionPlaceholder")
    if isinstance(source, QLabel):
        source.setText(f"{_txt('출처', 'Source')}:")
        source.setStyleSheet(
            "QLabel { background:transparent; color:#171924; border:0; "
            "padding:0 2px; font-size:10.5pt; font-weight:600; }"
        )
        source.setFixedHeight(24)

    outer = card.layout()
    if isinstance(outer, QVBoxLayout):
        # Keep the metadata block visually symmetric: the lower card margin is
        # identical to the thumbnail-to-first-metadata-row gap.
        outer.setSpacing(BUTTON_GAP)
        margins = outer.contentsMargins()
        outer.setContentsMargins(
            margins.left(), margins.top(), margins.right(), BUTTON_GAP
        )


def _remove_recent_deleted_heading(widget: QWidget) -> QWidget:
    """Remove the historical 'Before removal' strip even when the card is root."""
    for label in widget.findChildren(QLabel):
        if label.text().strip() in {"삭제 전", "Before removal"}:
            label.hide()
            label.deleteLater()
    return widget


def _arrange_card(card: Any) -> None:
    if bool(card.property("fh6ArchiveCard")):
        return
    overlay = _card_overlay(card)
    image = getattr(card, "_fh6_image_label", None)
    if overlay is None or image is None:
        return

    required = {
        "move": getattr(card, "_fh6_game_move_button", None),
        "zoom": getattr(card, "_fh6_zoom_button", None),
        "memo": getattr(card, "_fh6_memo_button", None),
        "info": getattr(card, "_fh6_info_button", None),
        "folder": getattr(card, "_fh6_folder_button", None),
        "paint": getattr(card, "_fh6_applied_state_button", None),
        "hide": getattr(card, "_fh6_hide_button", None),
        "check": getattr(card, "_fh6_check_box", None),
        "triangle": getattr(card, "_fh6_triangle_box", None),
        "excluded": getattr(card, "_fh6_excluded_box", None),
    }
    # SoulBound/auction cards intentionally have no My Designs navigation button.
    # Treat that as a supported card variant instead of aborting all v1.3.4
    # geometry/metadata normalization. Every other action remains mandatory.
    mandatory = ("zoom", "memo", "info", "folder", "paint", "hide", "check", "triangle", "excluded")
    if not all(isinstance(required[name], QToolButton) for name in mandatory):
        return
    move = required["move"] if isinstance(required["move"], QToolButton) else None
    grid = getattr(card, "_fh6_action_grid", None)
    if not isinstance(grid, QGridLayout):
        return

    _disable_old_aligners(card, overlay)

    required["info"].setIcon(_line_icon("info"))
    required["folder"].setIcon(_line_icon("folder"))
    if move is not None:
        move.setIcon(card_icon("move", "#6e4bf2"))
    required["zoom"].setIcon(card_icon("zoom"))
    required["check"].setIcon(
        card_toggle_icon("circle", on_color=CLASSIFICATION_ACTIVE_COLORS["check"])
    )
    required["triangle"].setIcon(
        card_toggle_icon("triangle", on_color=CLASSIFICATION_ACTIVE_COLORS["triangle"])
    )
    required["excluded"].setIcon(
        card_toggle_icon("excluded", on_color=CLASSIFICATION_ACTIVE_COLORS["excluded"])
    )

    lock = None
    if move is not None:
        lock = _unique_placeholder(
            card, overlay, "_fh6_lock_placeholder_button", "fh6LockPlaceholderButton", "lock", "잠금 기능 준비 중"
        )
        if not lock.isCheckable():
            lock.setCheckable(True)
            lock.toggled.connect(lambda active, target=lock: target.setIcon(_line_icon("lock", active=active)))
        lock.setIcon(
            card_toggle_icon(
                "unlock", "lock", on_color=LOCK_ACTIVE_ICON
            )
        )
    export = _unique_placeholder(
        card, overlay, "_fh6_export_placeholder_button", "fh6ExportPlaceholderButton", "export", "내보내기 기능 준비 중"
    )
    export.setEnabled(False)

    left = [required[name] for name in ("move", "zoom", "memo", "info", "folder")]
    left.append(export)
    right = [required["paint"], lock]
    right.extend(required[name] for name in ("hide", "check", "triangle", "excluded"))

    # The grid is created by the original card constructor. This final feature
    # layer only fills its reserved cells and normalizes icons; it never creates
    # a competing overlay, event filter, or absolute-position owner. Missing
    # SoulBound move/lock controls leave their normal row slots empty so every
    # remaining icon keeps the same spacing as a standard livery card.
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(0)
    grid.setVerticalSpacing(BUTTON_GAP)
    grid.setColumnStretch(0, 1)
    grid.setColumnStretch(1, 1)
    for row, (left_button, right_button) in enumerate(zip(left, right)):
        for button in (left_button, right_button):
            if isinstance(button, QToolButton):
                button.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
                button.show()
        grid.setRowMinimumHeight(row, ROW_HEIGHT)
        vertical = Qt.AlignmentFlag.AlignTop if row == 0 else Qt.AlignmentFlag.AlignBottom if row == 5 else Qt.AlignmentFlag.AlignVCenter
        if isinstance(left_button, QToolButton):
            grid.addWidget(left_button, row, 0, Qt.AlignmentFlag.AlignLeft | vertical)
        if isinstance(right_button, QToolButton):
            grid.addWidget(right_button, row, 1, Qt.AlignmentFlag.AlignRight | vertical)

    def enforce_grid() -> None:
        # Cards can be replaced before the 50/150 ms layout callbacks fire.
        # Accessing a deleted C++ layout raises RuntimeError in PySide6, so make
        # already-queued maintenance callbacks explicitly lifetime-safe.
        try:
            grid.invalidate()
            grid.activate()
        except RuntimeError:
            return

    card._fh6_v134_action_grid = grid

    image.setMinimumHeight(THUMBNAIL_MIN_HEIGHT)
    card.setMinimumHeight(CARD_MIN_HEIGHT)
    aspect = getattr(card, "_fh6_aspect_thumbnail_controller", None)
    original_target_height = getattr(aspect, "target_height", None)
    if callable(original_target_height) and not bool(getattr(aspect, "_fh6_v134_minimum_installed", False)):
        aspect.target_height = lambda width=None, target=original_target_height: max(
            THUMBNAIL_MIN_HEIGHT,
            target(width),
        )
        aspect._fh6_v134_minimum_installed = True
        original_apply = aspect.apply

        def apply_with_card_height() -> None:
            try:
                original_apply()
                host = getattr(aspect, "host", None)
                host_height = host.height() if host is not None else THUMBNAIL_MIN_HEIGHT
                card.setMinimumHeight(max(CARD_MIN_HEIGHT, host_height + CARD_METADATA_HEIGHT))
            except RuntimeError:
                return

        aspect.apply = apply_with_card_height
        aspect.schedule()
        QTimer.singleShot(0, apply_with_card_height)
        QTimer.singleShot(50, apply_with_card_height)
    QTimer.singleShot(0, enforce_grid)
    QTimer.singleShot(50, enforce_grid)
    QTimer.singleShot(150, enforce_grid)

    _normalize_metadata(card)


def _run_busy(owner: Any, action: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    begin = getattr(owner, "_begin_busy", None)
    end = getattr(owner, "_end_busy", None)
    began = callable(begin)
    if began:
        begin(_txt("처리 중", "Processing"))
    try:
        return action(*args, **kwargs)
    finally:
        if began and callable(end):
            end()


def apply_v1_3_4_card_action_layout_patch(MainWindow: Any) -> None:
    if getattr(MainWindow, "_fh6_v134_card_action_layout_patched", False):
        return
    original_make_card = MainWindow._make_saved_content_card

    def make_card(self: Any, content_type: str, record: Any, key: str):
        card = original_make_card(self, content_type, record, key)
        if content_type == "livery":
            _arrange_card(card)
        else:
            _normalize_metadata(card)
        return card

    @staticmethod
    def memo_icon(has_note: bool) -> QIcon:
        return _line_icon("memo", active=has_note)

    original_vehicle_grouping = MainWindow._set_vehicle_grouping
    original_creator_grouping = MainWindow._set_creator_grouping

    def set_vehicle_grouping(self: Any, content_type: str, enabled: bool) -> Any:
        return _run_busy(
            self, original_vehicle_grouping, self, content_type, enabled
        )

    def set_creator_grouping(self: Any, content_type: str, enabled: bool) -> Any:
        return _run_busy(
            self, original_creator_grouping, self, content_type, enabled
        )

    original_status_filter = _memory_state._set_status_filter_mode

    def set_status_filter(window: Any, mode: str) -> Any:
        return _run_busy(window, original_status_filter, window, mode)

    # The v1.3.2 archive cleanup only walked child QFrames, while the grouped
    # recent view passes its archive QFrame as the root widget. Keep all legacy
    # cleanup and additionally remove the root card's historical strip.
    original_archive_cleanup = _alias_fix._remove_deleted_heading_and_match_main_frame

    def archive_cleanup(widget: QWidget) -> QWidget:
        result = original_archive_cleanup(widget)
        return _remove_recent_deleted_heading(result)

    _alias_fix._remove_deleted_heading_and_match_main_frame = archive_cleanup
    MainWindow._make_saved_content_card = make_card
    MainWindow._detail_memo_icon = memo_icon
    MainWindow._set_vehicle_grouping = set_vehicle_grouping
    MainWindow._set_creator_grouping = set_creator_grouping
    _memory_state._set_status_filter_mode = set_status_filter
    # Timers queued by the legacy four-row patch resolve this module global at
    # execution time. Disable that obsolete geometry owner entirely.
    _legacy_runtime._force_card_action_geometry = lambda _card: None
    MainWindow._fh6_v134_card_action_layout_patched = True
