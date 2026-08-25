from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap
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
    QVBoxLayout,
    QWidget,
)

from . import creator_change_views as _change_view
from .creator_alias_views import creator_display
from .i18n import tr
from .refresh_history import (
    LiveryRefreshChange,
    LiverySnapshotEntry,
    cached_thumbnail_path,
)
from .saved_content_layout import GRID_MAX_COLUMNS, GRID_MIN_COLUMNS

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

def _txt(ko: str, en: str) -> str:
    return _change_view._txt(ko, en)


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
    card.setObjectName("panel" if not heading else "card")
    card.setProperty("fh6ArchiveCard", True)
    card.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
    card.setFixedWidth(card_width)

    layout = QVBoxLayout(card)
    margin = 12 if not heading else 10
    layout.setContentsMargins(margin, margin, margin, margin)
    layout.setSpacing(8 if not heading else 7)

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

    vehicle_text = window._car_label(entry.car_id)
    if not heading:
        vehicle_text = f"{_txt('차량명', 'Vehicle')}: {vehicle_text}"
    vehicle = QLabel(vehicle_text)
    vehicle.setStyleSheet("font-weight:700;font-size:11pt;")
    vehicle.setWordWrap(True)
    layout.addWidget(vehicle)

    metadata = QGridLayout()
    metadata.setContentsMargins(0, 0, 0, 0)
    metadata.setHorizontalSpacing(0)
    title = QLabel(f"{tr('card.title_label')}: {entry.name or '—'}")
    creator = QLabel(f"{tr('card.creator_label')}: {creator_display(window, entry.creator)}")
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

    if heading:
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
    if card is None:
        return _archive_card_like_main(
            window, entry, _txt("현재 기록", "Current snapshot"), card_width
        )
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
        outer.addWidget(_archive_card_like_main(window, change.before, "", card_width))
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
