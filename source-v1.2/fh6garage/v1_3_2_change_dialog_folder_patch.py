from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QObject, QPoint, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import v1_3_2_change_view_alias_patch as _change_view
from .i18n import tr
from .refresh_history import (
    LiveryRefreshChange,
    LiverySnapshotEntry,
    cached_thumbnail_path,
)
from .v1_3_ui_patch import GRID_MAX_COLUMNS, GRID_MIN_COLUMNS

_RECENT_CARD_FRAME_RULE = (
    "QFrame#panel, QFrame#card { "
    "background:#ffffff; border:1px solid #cfd3dd; border-radius:12px; "
    "}"
)


def _strengthen_recent_card_frames(root: QWidget) -> QWidget:
    frames = ([root] if isinstance(root, QFrame) else []) + root.findChildren(QFrame)
    for frame in frames:
        if frame.objectName() not in {"panel", "card"}:
            continue
        if bool(frame.property("fh6RecentStrongFrame")):
            continue
        existing = frame.styleSheet().rstrip()
        frame.setStyleSheet((existing + "\n" if existing else "") + _RECENT_CARD_FRAME_RULE)
        frame.setProperty("fh6RecentStrongFrame", True)
    return root

CARD_ACTION_BUTTON_SIZE = 30
CARD_ACTION_ICON_SIZE = 20


def _txt(ko: str, en: str) -> str:
    return _change_view._txt(ko, en)


def _center_in_overlay(widget: QWidget, overlay: QWidget) -> QPoint:
    return widget.mapTo(overlay, widget.rect().center())


def _top_left_for_center(center: QPoint, widget: QWidget) -> QPoint:
    return QPoint(
        center.x() - (widget.width() - 1) // 2,
        center.y() - (widget.height() - 1) // 2,
    )


def _card_overlay(card: Any) -> QWidget | None:
    image_label = getattr(card, "_fh6_image_label", None)
    if image_label is None:
        return None
    image_host = image_label.parentWidget()
    stack = image_host.layout() if image_host is not None else None
    overlay = stack.currentWidget() if stack is not None and hasattr(stack, "currentWidget") else None
    return overlay if isinstance(overlay, QWidget) else None


def _open_record_folder(record: Any) -> None:
    raw_path = getattr(record, "container_path", None)
    if raw_path is None:
        return
    path = Path(raw_path)
    if not path.is_dir():
        return
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def _install_folder_button(card: Any, record: Any) -> QToolButton | None:
    existing = getattr(card, "_fh6_folder_button", None)
    if isinstance(existing, QToolButton):
        return existing

    overlay = _card_overlay(card)
    if overlay is None:
        return None

    button = QToolButton(overlay)
    button.setObjectName("fh6FolderButton")
    button.setFixedSize(CARD_ACTION_BUTTON_SIZE, CARD_ACTION_BUTTON_SIZE)
    button.setIconSize(QSize(CARD_ACTION_ICON_SIZE, CARD_ACTION_ICON_SIZE))
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setToolTip(_txt("리버리 폴더 열기", "Open livery folder"))
    button.setIcon(card.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))

    reference = getattr(card, "_fh6_info_button", None)
    if isinstance(reference, QToolButton):
        button.setAutoRaise(reference.autoRaise())
        if reference.styleSheet():
            button.setStyleSheet(reference.styleSheet())

    path = Path(getattr(record, "container_path", ""))
    button.setEnabled(path.is_dir())
    if not path.is_dir():
        button.setToolTip(_txt("리버리 폴더를 찾을 수 없음", "Livery folder not found"))
    button.clicked.connect(lambda _checked=False, r=record: _open_record_folder(r))
    button.show()
    card._fh6_folder_button = button
    return button


class _FourLeftActionAligner(QObject):
    _EVENTS = {
        QEvent.Type.Show,
        QEvent.Type.Resize,
        QEvent.Type.LayoutRequest,
        QEvent.Type.PolishRequest,
    }

    def __init__(self, card: Any, overlay: QWidget) -> None:
        super().__init__(overlay)
        self.card = card
        self.overlay = overlay
        overlay.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() in self._EVENTS:
            QTimer.singleShot(0, self.reposition)
        return False

    def _left_center_x(self) -> int:
        for name in ("_fh6_game_move_button", "_fh6_hide_button", "_fh6_info_button", "_fh6_folder_button"):
            widget = getattr(self.card, name, None)
            if isinstance(widget, QToolButton) and widget.isVisible():
                return _center_in_overlay(widget, self.overlay).x()
        return 8 + (CARD_ACTION_BUTTON_SIZE - 1) // 2

    def reposition(self) -> None:
        rows = (
            ("_fh6_game_move_button", "_fh6_check_box"),
            ("_fh6_hide_button", "_fh6_triangle_box"),
            ("_fh6_info_button", "_fh6_excluded_box"),
            ("_fh6_folder_button", "_fh6_zoom_button"),
        )
        left_x = self._left_center_x()
        for left_name, right_name in rows:
            left = getattr(self.card, left_name, None)
            right = getattr(self.card, right_name, None)
            if not isinstance(left, QToolButton) or not isinstance(right, QToolButton):
                continue
            if not left.isVisible() or not right.isVisible():
                continue
            right_center = _center_in_overlay(right, self.overlay)
            left.move(_top_left_for_center(QPoint(left_x, right_center.y()), left))
            left.raise_()


def _install_four_left_actions(card: Any, record: Any) -> None:
    overlay = _card_overlay(card)
    if overlay is None:
        return
    _install_folder_button(card, record)
    aligner = _FourLeftActionAligner(card, overlay)
    card._fh6_four_left_action_aligner = aligner
    QTimer.singleShot(0, aligner.reposition)


def _main_livery_card_width(window: Any) -> int:
    scroll = getattr(window, "livery_grid_scroll", None)
    layout = getattr(window, "livery_grid_layout", None)
    if scroll is None or layout is None or scroll.viewport() is None:
        return 420
    viewport_width = max(1, scroll.viewport().width())
    counter = getattr(window, "_fh6_grid_column_count", None)
    try:
        columns = int(counter("livery")) if callable(counter) else GRID_MIN_COLUMNS
    except (TypeError, ValueError, RuntimeError):
        columns = GRID_MIN_COLUMNS
    columns = max(GRID_MIN_COLUMNS, min(GRID_MAX_COLUMNS, columns))
    margins = layout.contentsMargins()
    gap = max(0, layout.horizontalSpacing())
    available = viewport_width - margins.left() - margins.right() - gap * (columns - 1) - 4
    return max(1, available // columns)


def _main_livery_columns(window: Any) -> int:
    counter = getattr(window, "_fh6_grid_column_count", None)
    try:
        columns = int(counter("livery")) if callable(counter) else GRID_MIN_COLUMNS
    except (TypeError, ValueError, RuntimeError):
        columns = GRID_MIN_COLUMNS
    return max(GRID_MIN_COLUMNS, min(GRID_MAX_COLUMNS, columns))


def _archive_card_like_main(window: Any, entry: LiverySnapshotEntry, heading: str, card_width: int) -> QFrame:
    card = QFrame()
    card.setObjectName("card")
    card.setProperty("fh6ArchiveCard", True)
    card.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
    card.setFixedWidth(card_width)

    layout = QVBoxLayout(card)
    layout.setContentsMargins(10, 10, 10, 10)
    layout.setSpacing(7)

    image = QLabel()
    image.setAlignment(Qt.AlignmentFlag.AlignCenter)
    image.setStyleSheet("background:#f1f2f6;border-radius:9px;color:#737787;")
    image_width = max(1, card_width - 20)
    image_height = max(180, round(image_width * 9 / 16))
    image.setFixedHeight(image_height)

    path = cached_thumbnail_path(entry)
    pixmap = None
    if path is not None:
        try:
            pixmap = QPixmap(str(path))
        except Exception:
            pixmap = None
    if isinstance(pixmap, QPixmap) and not pixmap.isNull():
        image.setPixmap(
            pixmap.scaled(
                image_width,
                image_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
    else:
        image.setText(_txt("썸네일 없음", "No thumbnail"))
    layout.addWidget(image)

    vehicle = QLabel(window._car_label(entry.car_id))
    vehicle.setStyleSheet("font-weight:700;font-size:11pt;")
    vehicle.setWordWrap(True)
    layout.addWidget(vehicle)

    metadata = QGridLayout()
    metadata.setContentsMargins(0, 0, 0, 0)
    metadata.setHorizontalSpacing(0)
    title = QLabel(f"{tr('card.title_label')}: {entry.name or '—'}")
    creator = QLabel(f"{tr('card.creator_label')}: {_change_view._creator_display(window, entry.creator)}")
    title.setToolTip(title.text())
    creator.setToolTip(
        (_txt("삭제 당시 제작자: ", "Recorded creator: ") + entry.creator)
        if entry.creator else creator.text()
    )
    metadata.addWidget(title, 0, 0)
    metadata.addWidget(creator, 0, 1)
    metadata.setColumnStretch(0, 1)
    metadata.setColumnStretch(1, 1)
    layout.addLayout(metadata)

    if entry.description:
        description = QLabel(entry.description)
        description.setObjectName("muted")
        description.setWordWrap(True)
        layout.addWidget(description)

    record_badge = QLabel(heading)
    record_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    record_badge.setStyleSheet(
        "background:#f0ecff;color:#5f39d8;border-radius:7px;"
        "padding:4px 8px;font-weight:700;"
    )
    layout.addWidget(record_badge)
    return card


def _current_card_same_size(window: Any, entry: LiverySnapshotEntry, card_width: int) -> QWidget:
    card = _change_view._current_change_card(window, entry)
    card.setMinimumWidth(0)
    card.setMaximumWidth(card_width)
    card.setFixedWidth(card_width)
    return card


def _status_badge(status: str) -> QLabel:
    badge = QLabel(_change_view._status_text(status))
    badge.setStyleSheet(
        _change_view._status_style(status)
        + "border-radius:7px;padding:5px 9px;font-weight:700;"
    )
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return badge


def _single_change_item(window: Any, change: LiveryRefreshChange, card_width: int) -> tuple[QWidget, str, int]:
    status = change.status
    wrapper = QWidget()
    wrapper.setFixedWidth(card_width)
    outer = QVBoxLayout(wrapper)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(6)
    outer.addWidget(_status_badge(status), 0, Qt.AlignmentFlag.AlignLeft)

    if status == "added" and change.after is not None:
        outer.addWidget(_current_card_same_size(window, change.after, card_width))
    elif status == "removed" and change.before is not None:
        outer.addWidget(_archive_card_like_main(window, change.before, _txt("삭제 전", "Before removal"), card_width))
    _strengthen_recent_card_frames(wrapper)
    return wrapper, status, 1


def _changed_pair_item(window: Any, change: LiveryRefreshChange, card_width: int, gap: int) -> tuple[QWidget, str, int]:
    wrapper = QWidget()
    wrapper.setFixedWidth(card_width * 2 + gap)
    outer = QVBoxLayout(wrapper)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(6)
    outer.addWidget(_status_badge("changed"), 0, Qt.AlignmentFlag.AlignLeft)

    pair = QHBoxLayout()
    pair.setContentsMargins(0, 0, 0, 0)
    pair.setSpacing(gap)
    if change.before is not None:
        pair.addWidget(_archive_card_like_main(window, change.before, _txt("변경 전", "Before"), card_width))
    if change.after is not None:
        pair.addWidget(_current_card_same_size(window, change.after, card_width))
    pair.addStretch(1)
    outer.addLayout(pair)
    _strengthen_recent_card_frames(wrapper)
    return wrapper, "changed", 2


def _open_change_dialog_same_as_main(window: Any) -> None:
    diff = getattr(window, "_fh6_latest_livery_diff", None)
    if diff is None or getattr(diff, "baseline", False) or getattr(diff, "total", 0) <= 0:
        return

    previous = getattr(window, "_fh6_change_dialog", None)
    if isinstance(previous, QDialog) and previous.isVisible():
        previous.raise_()
        previous.activateWindow()
        return

    dialog = QDialog(window, Qt.WindowType.Window)
    dialog.setWindowTitle(_txt("최근 리버리 변경사항", "Recent livery changes"))
    dialog.setModal(False)
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    dialog.resize(window.size())
    dialog.setMinimumSize(QSize(760, 560))
    window._fh6_change_dialog = dialog
    dialog.destroyed.connect(lambda *_args: setattr(window, "_fh6_change_dialog", None))

    root = QVBoxLayout(dialog)
    root.setContentsMargins(12, 12, 12, 12)
    root.setSpacing(10)

    controls = QHBoxLayout()
    group = QButtonGroup(dialog)
    group.setExclusive(True)
    buttons: dict[str, QPushButton] = {}
    specs = (
        ("all", _txt("전체", "All"), diff.total),
        ("added", _txt("추가", "Added"), len(diff.added)),
        ("removed", _txt("삭제", "Removed"), len(diff.removed)),
        ("changed", _txt("변경", "Changed"), len(diff.changed)),
    )
    for key, label, count in specs:
        button = QPushButton(f"{label} {count}")
        button.setObjectName("secondary")
        button.setCheckable(True)
        if key == "all":
            button.setChecked(True)
        group.addButton(button)
        buttons[key] = button
        controls.addWidget(button)
    controls.addStretch(1)
    close_button = QPushButton(tr("common.close"))
    close_button.setObjectName("primary")
    close_button.clicked.connect(dialog.close)
    controls.addWidget(close_button)
    root.addLayout(controls)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    host = QWidget()
    grid = QGridLayout(host)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(max(0, getattr(window.livery_grid_layout, "horizontalSpacing", lambda: 8)()))
    grid.setVerticalSpacing(max(8, getattr(window.livery_grid_layout, "verticalSpacing", lambda: 10)()))
    grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
    scroll.setWidget(host)
    root.addWidget(scroll, 1)

    card_width = _main_livery_card_width(window)
    columns = _main_livery_columns(window)
    gap = max(8, grid.horizontalSpacing())
    items: list[tuple[QWidget, str, int]] = []
    for change in [*diff.added, *diff.removed]:
        items.append(_single_change_item(window, change, card_width))
    for change in diff.changed:
        items.append(_changed_pair_item(window, change, card_width, gap))

    def repack(filter_name: str) -> None:
        while grid.count():
            item = grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
        row = 0
        col = 0
        for widget, status, span in items:
            if filter_name != "all" and status != filter_name:
                continue
            if span > columns:
                span = columns
            if col + span > columns:
                row += 1
                col = 0
            grid.addWidget(widget, row, col, 1, span)
            widget.show()
            col += span
            if col >= columns:
                row += 1
                col = 0
        for column in range(GRID_MAX_COLUMNS):
            grid.setColumnStretch(column, 0)
        host.adjustSize()

    for key, button in buttons.items():
        button.clicked.connect(lambda _checked=False, k=key: repack(k))
    repack("all")
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()


def apply_v1_3_2_change_dialog_folder_patch(MainWindow) -> None:
    """Match change-view cards to the main grid and add a read-only folder action."""
    if getattr(MainWindow, "_fh6_v132_change_dialog_folder_patched", False):
        return

    original_make_card = MainWindow._make_saved_content_card

    def patched_make_card(self, content_type: str, record: Any, key: str):
        card = original_make_card(self, content_type, record, key)
        if content_type == "livery" and not bool(card.property("fh6ArchiveCard")):
            _install_four_left_actions(card, record)
        return card

    MainWindow._make_saved_content_card = patched_make_card
    _change_view._open_change_dialog = _open_change_dialog_same_as_main
    MainWindow._fh6_v132_change_dialog_folder_patched = True
