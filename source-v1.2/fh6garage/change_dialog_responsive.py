from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QEvent, QObject, QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from . import v1_3_2_change_dialog_folder_patch as _feature
from .i18n import tr
from .ui import APP_STYLE
from .v1_3_ui_patch import (
    GRID_MAX_COLUMNS,
    GRID_MIN_COLUMNS,
    GRID_TARGET_CARD_WIDTH,
)

_DIALOG_BACKGROUND = "#f7f8fb"
_DIALOG_MIN_SIZE = QSize(760, 560)
_RESIZE_DEBOUNCE_MS = 55


def _dialog_grid_metrics(
    viewport_width: int,
    gap: int,
    *,
    left_margin: int = 0,
    right_margin: int = 0,
) -> tuple[int, int]:
    """Return the same 2/3/4-column geometry contract used by the main grid."""
    inner_width = max(1, int(viewport_width) - int(left_margin) - int(right_margin) - 4)
    columns = inner_width // GRID_TARGET_CARD_WIDTH
    columns = max(GRID_MIN_COLUMNS, min(GRID_MAX_COLUMNS, int(columns)))
    available = max(
        1,
        inner_width - max(0, int(gap)) * (columns - 1),
    )
    return columns, max(1, available // columns)


def _apply_dialog_theme(dialog: QDialog, scroll: QScrollArea, host: QWidget) -> None:
    """Force the standalone change window to use the main application's light UI."""
    dialog.setObjectName("fh6ChangeDialog")
    scroll.setObjectName("fh6ChangeScroll")
    host.setObjectName("fh6ChangeHost")

    dialog.setStyleSheet(
        APP_STYLE
        + f"""
        QDialog#fh6ChangeDialog {{ background:{_DIALOG_BACKGROUND}; }}
        QScrollArea#fh6ChangeScroll {{ background:{_DIALOG_BACKGROUND}; border:0; }}
        QScrollArea#fh6ChangeScroll > QWidget > QWidget {{ background:{_DIALOG_BACKGROUND}; }}
        QWidget#fh6ChangeHost {{ background:{_DIALOG_BACKGROUND}; }}
        """
    )
    scroll.setStyleSheet(f"background:{_DIALOG_BACKGROUND}; border:0;")
    scroll.viewport().setStyleSheet(f"background:{_DIALOG_BACKGROUND};")
    host.setStyleSheet(f"background:{_DIALOG_BACKGROUND};")


class _ViewportResizeController(QObject):
    """Debounce resize events with a timer owned by the dialog viewport."""

    def __init__(self, viewport: QWidget, callback: Callable[[], None]) -> None:
        super().__init__(viewport)
        self._callback = callback
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(callback)
        viewport.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() in {QEvent.Type.Resize, QEvent.Type.Show}:
            self.request(_RESIZE_DEBOUNCE_MS)
        return False

    def request(self, delay_ms: int = _RESIZE_DEBOUNCE_MS) -> None:
        self._timer.start(max(0, int(delay_ms)))

    def request_now(self) -> None:
        self._timer.stop()
        self._callback()


def _open_responsive_change_dialog(window: Any) -> None:
    diff = getattr(window, "_fh6_latest_livery_diff", None)
    if diff is None or getattr(diff, "baseline", False) or getattr(diff, "total", 0) <= 0:
        return

    previous = getattr(window, "_fh6_change_dialog", None)
    if isinstance(previous, QDialog) and previous.isVisible():
        previous.raise_()
        previous.activateWindow()
        return

    dialog = QDialog(window, Qt.WindowType.Window)
    dialog.setWindowTitle(_feature._txt("최근 리버리 변경사항", "Recent livery changes"))
    dialog.setModal(False)
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    dialog.resize(window.size())
    dialog.setMinimumSize(_DIALOG_MIN_SIZE)
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
        ("all", _feature._txt("전체", "All"), diff.total),
        ("added", _feature._txt("추가", "Added"), len(diff.added)),
        ("removed", _feature._txt("삭제", "Removed"), len(diff.removed)),
        ("changed", _feature._txt("변경", "Changed"), len(diff.changed)),
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

    scroll = QScrollArea(dialog)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    host = QWidget()
    host.setMinimumWidth(0)
    grid = QGridLayout(host)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(
        max(0, getattr(window.livery_grid_layout, "horizontalSpacing", lambda: 8)())
    )
    grid.setVerticalSpacing(
        max(8, getattr(window.livery_grid_layout, "verticalSpacing", lambda: 10)())
    )
    grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
    scroll.setWidget(host)
    root.addWidget(scroll, 1)
    _apply_dialog_theme(dialog, scroll, host)

    state = {
        "filter": "all",
        "geometry": None,
        "widgets": [],
    }

    def clear_grid() -> None:
        while grid.count():
            item = grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        state["widgets"] = []

    def visible_changes(filter_name: str):
        changes = [*diff.added, *diff.removed, *diff.changed]
        if filter_name == "all":
            return changes
        return [change for change in changes if change.status == filter_name]

    def render(*, force: bool = False) -> None:
        viewport = scroll.viewport()
        viewport_width = viewport.width() if viewport is not None else 0
        if viewport_width <= 0:
            return

        margins = grid.contentsMargins()
        gap = max(0, grid.horizontalSpacing())
        columns, card_width = _dialog_grid_metrics(
            viewport_width,
            gap,
            left_margin=margins.left(),
            right_margin=margins.right(),
        )
        geometry = (state["filter"], columns, card_width)
        if not force and geometry == state["geometry"]:
            return
        state["geometry"] = geometry

        clear_grid()
        row = 0
        col = 0
        widgets: list[QWidget] = []
        for change in visible_changes(str(state["filter"])):
            if change.status == "changed":
                widget, _status, span = _feature._changed_pair_item(
                    window,
                    change,
                    card_width,
                    max(8, gap),
                )
            else:
                widget, _status, span = _feature._single_change_item(
                    window,
                    change,
                    card_width,
                )

            span = max(1, min(columns, int(span)))
            if col and col + span > columns:
                row += 1
                col = 0
            grid.addWidget(widget, row, col, 1, span)
            widget.show()
            widgets.append(widget)
            col += span
            if col >= columns:
                row += 1
                col = 0

        state["widgets"] = widgets
        for column in range(GRID_MAX_COLUMNS):
            grid.setColumnStretch(column, 1 if column < columns else 0)
        host.setMinimumWidth(0)
        host.updateGeometry()

    def set_filter(filter_name: str) -> None:
        state["filter"] = filter_name
        state["geometry"] = None
        render(force=True)

    for key, button in buttons.items():
        button.clicked.connect(lambda _checked=False, k=key: set_filter(k))

    controller = _ViewportResizeController(scroll.viewport(), lambda: render(force=False))
    dialog._fh6_change_resize_controller = controller
    dialog._fh6_change_render = render
    dialog._fh6_change_scroll = scroll
    dialog._fh6_change_grid = grid

    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    # show() establishes the first real viewport geometry, so render once now.
    # Later native resize/show passes are handled only by the controller-owned
    # QTimer; closing the dialog deletes that timer and cannot leave a callback
    # pointing at an already-destroyed QScrollArea.
    controller.request_now()

