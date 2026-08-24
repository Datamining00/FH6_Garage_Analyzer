from __future__ import annotations

from typing import Any

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QFrame, QLayout, QMainWindow, QWidget

from . import i18n
from .i18n import tr
from .ui import CopyValueLabel


SIDEBAR_WIDTH = 150
SIDEBAR_HORIZONTAL_MARGIN = 12
CONTENT_HORIZONTAL_MARGIN = 12
GRID_HORIZONTAL_SPACING = 8
GRID_SIDE_MARGIN = 0


class _ElidedCopyValueController(QObject):
    """Elide one copyable metadata label and expose the full text only on truncation."""

    _EVENTS = {
        QEvent.Type.Resize,
        QEvent.Type.Show,
        QEvent.Type.FontChange,
        QEvent.Type.StyleChange,
        QEvent.Type.LayoutRequest,
    }

    def __init__(self, label: CopyValueLabel) -> None:
        super().__init__(label)
        self.label = label
        self._pending = False
        self._applying = False
        label.installEventFilter(self)
        self.schedule()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() in self._EVENTS:
            self.schedule()
        return False

    def schedule(self) -> None:
        if self._pending:
            return
        self._pending = True
        QTimer.singleShot(0, self.apply)

    def full_text(self) -> str:
        return f"{self.label.prefix}: {self.label.copy_value}"

    def apply(self) -> None:
        self._pending = False
        if self._applying:
            return
        self._applying = True
        try:
            full = self.full_text()
            available = max(1, self.label.contentsRect().width())
            metrics = QFontMetrics(self.label.font())
            display = metrics.elidedText(
                full,
                Qt.TextElideMode.ElideRight,
                available,
            )
            if self.label.text() != display:
                self.label.setText(display)
            self.label.setToolTip(full if display != full else "")
        finally:
            self._applying = False


def _find_layout_with_widgets(root: QLayout | None, targets: set[QWidget]) -> QLayout | None:
    if root is None:
        return None
    direct = {
        item.widget()
        for index in range(root.count())
        if (item := root.itemAt(index)) is not None and item.widget() is not None
    }
    if targets.issubset(direct):
        return root
    for index in range(root.count()):
        item = root.itemAt(index)
        if item is None:
            continue
        child = item.layout()
        if child is None:
            continue
        found = _find_layout_with_widgets(child, targets)
        if found is not None:
            return found
    return None


def _metadata_labels(card: QWidget) -> tuple[CopyValueLabel | None, CopyValueLabel | None, CopyValueLabel | None]:
    vehicle = None
    title = None
    creator = None
    vehicle_prefix = tr("card.vehicle_label")
    title_prefix = tr("card.title_label")
    creator_prefix = tr("card.creator_label")
    for label in card.findChildren(CopyValueLabel):
        if label.prefix == vehicle_prefix:
            vehicle = label
        elif label.prefix == title_prefix:
            title = label
        elif label.prefix == creator_prefix:
            creator = label
    return vehicle, title, creator


def _configure_card_metadata(card: QWidget) -> None:
    vehicle, title, creator = _metadata_labels(card)
    controllers: list[_ElidedCopyValueController] = []
    for label in (vehicle, title, creator):
        if label is None:
            continue
        controller = _ElidedCopyValueController(label)
        controllers.append(controller)

    # Keep the title and creator in exact equal halves. With zero inter-column
    # spacing the creator label's allocation begins at the card metadata midpoint.
    if title is not None and creator is not None:
        row = _find_layout_with_widgets(card.layout(), {title, creator})
        if row is not None:
            row.setSpacing(0)
            if hasattr(row, "setStretchFactor"):
                row.setStretchFactor(title, 1)
                row.setStretchFactor(creator, 1)

    card._fh6_metadata_elide_controllers = controllers


def _compact_window_chrome(window: QMainWindow) -> None:
    sidebar = window.findChild(QFrame, "sidebar")
    if sidebar is not None:
        sidebar.setFixedWidth(SIDEBAR_WIDTH)
        side_layout = sidebar.layout()
        if side_layout is not None:
            margins = side_layout.contentsMargins()
            side_layout.setContentsMargins(
                SIDEBAR_HORIZONTAL_MARGIN,
                margins.top(),
                SIDEBAR_HORIZONTAL_MARGIN,
                margins.bottom(),
            )

    root = window.centralWidget()
    root_layout = root.layout() if root is not None else None
    if root_layout is not None:
        for index in range(root_layout.count()):
            item = root_layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if widget is None or widget is sidebar:
                continue
            content_layout = widget.layout()
            if content_layout is None:
                continue
            margins = content_layout.contentsMargins()
            content_layout.setContentsMargins(
                CONTENT_HORIZONTAL_MARGIN,
                margins.top(),
                CONTENT_HORIZONTAL_MARGIN,
                margins.bottom(),
            )
            break

    for content_type in ("livery", "tuning"):
        layout = getattr(window, f"{content_type}_grid_layout", None)
        if layout is None:
            continue
        margins = layout.contentsMargins()
        layout.setContentsMargins(
            GRID_SIDE_MARGIN,
            margins.top(),
            GRID_SIDE_MARGIN,
            margins.bottom(),
        )
        layout.setHorizontalSpacing(GRID_HORIZONTAL_SPACING)

    # Recompute widths after native layout negotiation. Existing resize handlers
    # continue to use the new margins/gap after this first forced synchronization.
    def sync_widths() -> None:
        for method_name in (
            "_sync_livery_grid_card_widths",
            "_sync_tuning_grid_card_widths",
        ):
            method = getattr(window, method_name, None)
            if callable(method):
                method()

    QTimer.singleShot(0, sync_widths)


def apply_v1_3_2_compact_card_layout_patch(MainWindow) -> None:
    """Use horizontal space more efficiently and make card metadata predictable."""
    if getattr(MainWindow, "_fh6_v132_compact_card_layout_patched", False):
        return

    # Only the card label changes; table/sort terminology remains untouched.
    translations = getattr(i18n, "_TRANSLATIONS", None)
    if isinstance(translations, dict):
        entry = translations.get("card.creator_label")
        if isinstance(entry, dict):
            entry["ko"] = "제작자"
            entry["en"] = "Creator"

    original_build_ui = MainWindow._build_ui
    original_make_card = MainWindow._make_saved_content_card

    def patched_build_ui(self) -> None:
        original_build_ui(self)
        _compact_window_chrome(self)

    def patched_make_card(self, content_type: str, record: Any, key: str):
        card = original_make_card(self, content_type, record, key)
        _configure_card_metadata(card)
        return card

    MainWindow._build_ui = patched_build_ui
    MainWindow._make_saved_content_card = patched_make_card
    MainWindow._fh6_v132_compact_card_layout_patched = True
