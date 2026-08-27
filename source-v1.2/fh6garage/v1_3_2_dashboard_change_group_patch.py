from __future__ import annotations

from collections import Counter
from typing import Any, Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from . import v1_3_2_alias_manager_change_card_fix as _alias_fix
from . import v1_3_2_change_dialog_folder_patch as _change_dialog
from . import v1_3_2_change_dialog_responsive_ui_fix as _responsive
from . import v1_3_2_memory_state_patch as _memory
from . import v1_3_2_release_layout_patch as _release
from .i18n import get_language, tr
from .refresh_history import LiveryRefreshDiff, LiverySnapshotEntry


_SECTION_ORDER = ("added", "removed", "duplicate")
_SECTION_STYLE = {
    "added": (
        "#e9f7ee",
        "#237a43",
        "#bfe6cc",
    ),
    "removed": (
        "#fff0f1",
        "#b42d3a",
        "#f0c4c8",
    ),
    "duplicate": (
        "#f0ecff",
        "#5f39d8",
        "#d8ceff",
    ),
}


def _txt(ko: str, en: str) -> str:
    return ko if (get_language() or "ko").lower().startswith("ko") else en


def _normalize_page_titles(window: Any) -> None:
    """Remove the redundant large livery/tuning headings above search."""
    saved_page_titles = {
        "저장 리버리",
        "리버리",
        "Saved liveries",
        "Liveries",
        "저장 튜닝",
        "튜닝",
        "Saved tunings",
        "Tuning",
    }
    for label in window.findChildren(QLabel):
        if label.objectName() != "pageTitle":
            continue
        if label.text().strip() in saved_page_titles:
            label.hide()


def _state_usable(window: Any) -> bool:
    checker = getattr(window, "_fh6_memory_state_usable", None)
    if not callable(checker):
        return False
    try:
        return bool(checker())
    except TypeError:
        try:
            return bool(checker(window))
        except (RuntimeError, TypeError, ValueError):
            return False
    except (RuntimeError, ValueError):
        return False


def _record_state(window: Any, record: Any) -> str:
    resolver = getattr(window, "_fh6_memory_livery_state_for_record", None)
    if not callable(resolver):
        return "unknown"
    try:
        return str(resolver(record) or "unknown")
    except TypeError:
        try:
            return str(resolver(window, record) or "unknown")
        except (RuntimeError, TypeError, ValueError):
            return "unknown"
    except (RuntimeError, ValueError):
        return "unknown"


def _update_dashboard_summary(window: Any) -> None:
    """Show applied/total ratios for normal and auction liveries."""
    regular_title = _txt("적용 리버리 / 전체 리버리", "Applied / total liveries")
    auction_title = _txt("적용 경매장 / 전체 경매장", "Applied / total auction")

    livery_card = getattr(window, "card_livery", None)
    auction_card = getattr(window, "card_auction", None)
    if livery_card is not None and hasattr(livery_card, "title"):
        livery_card.title.setText(regular_title)
    if auction_card is not None and hasattr(auction_card, "title"):
        auction_card.title.setText(auction_title)

    result = getattr(window, "result", None)
    if result is None:
        if livery_card is not None and hasattr(livery_card, "value"):
            livery_card.value.setText("— / —")
        if auction_card is not None and hasattr(auction_card, "value"):
            auction_card.value.setText("— / —")
        return

    records = list(getattr(result, "liveries", []) or [])
    regular = [record for record in records if getattr(record, "kind", None) == "Livery"]
    auction = [record for record in records if getattr(record, "kind", None) == "SoulBoundLivery"]

    if _state_usable(window):
        regular_applied = sum(_record_state(window, record) == "applied" for record in regular)
        auction_applied = sum(_record_state(window, record) == "applied" for record in auction)
        regular_value = f"{regular_applied} / {len(regular)}"
        auction_value = f"{auction_applied} / {len(auction)}"
    else:
        regular_value = f"— / {len(regular)}"
        auction_value = f"— / {len(auction)}"

    if livery_card is not None and hasattr(livery_card, "value"):
        livery_card.value.setText(regular_value)
    if auction_card is not None and hasattr(auction_card, "value"):
        auction_card.value.setText(auction_value)


def _duplicate_content_keys(window: Any) -> set[tuple[str, str]]:
    result = getattr(window, "result", None)
    records = list(getattr(result, "liveries", []) or []) if result is not None else []
    counts = Counter(
        (
            str(getattr(record, "kind", "") or ""),
            str(getattr(record, "content_sha256", "") or "").strip().casefold(),
        )
        for record in records
        if str(getattr(record, "content_sha256", "") or "").strip()
    )
    return {key for key, count in counts.items() if count > 1}


def _entry_is_duplicate(entry: LiverySnapshotEntry | None, duplicate_keys: set[tuple[str, str]]) -> bool:
    if entry is None:
        return False
    digest = (entry.content_sha256 or "").strip().casefold()
    return bool(digest and (entry.kind, digest) in duplicate_keys)


def _dedupe_entries(entries: list[LiverySnapshotEntry]) -> list[LiverySnapshotEntry]:
    result: list[LiverySnapshotEntry] = []
    seen: set[tuple[str, str, str]] = set()
    for entry in entries:
        key = (
            entry.kind,
            (entry.identity or "").casefold(),
            (entry.content_sha256 or "").casefold(),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(entry)
    return result


def _categorized_changes(window: Any, diff: LiveryRefreshDiff) -> dict[str, list[LiverySnapshotEntry]]:
    """Convert refresh history into Add / Remove / Duplicate presentation groups.

    A newly present entry is routed to Duplicate when its current content hash
    occurs more than once in the same livery kind.  Legacy 'changed' pairs are
    unfolded into before=Remove and after=Add/Duplicate so no information is
    discarded while the UI stays on the requested three-category model.
    """
    duplicate_keys = _duplicate_content_keys(window)
    groups: dict[str, list[LiverySnapshotEntry]] = {
        "added": [],
        "removed": [],
        "duplicate": [],
    }

    def add_after(entry: LiverySnapshotEntry | None) -> None:
        if entry is None:
            return
        key = "duplicate" if _entry_is_duplicate(entry, duplicate_keys) else "added"
        groups[key].append(entry)

    for change in list(getattr(diff, "added", []) or []):
        add_after(change.after)
    for change in list(getattr(diff, "removed", []) or []):
        if change.before is not None:
            groups["removed"].append(change.before)
    for change in list(getattr(diff, "changed", []) or []):
        if change.before is not None:
            groups["removed"].append(change.before)
        add_after(change.after)

    return {key: _dedupe_entries(values) for key, values in groups.items()}


def _section_text(key: str, count: int) -> str:
    if key == "added":
        return _txt(f"+ 추가 {count}", f"+ Added {count}")
    if key == "removed":
        return _txt(f"− 제거 {count}", f"− Removed {count}")
    return _txt(f"▣ 중복 {count}", f"▣ Duplicate {count}")


def _section_header(key: str, count: int) -> QLabel:
    background, foreground, border = _SECTION_STYLE[key]
    label = QLabel(_section_text(key, count))
    label.setMinimumHeight(34)
    label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
    label.setStyleSheet(
        f"background:{background};color:{foreground};border:1px solid {border};"
        "border-radius:8px;padding:6px 10px;font-weight:700;"
    )
    return label


def _archive_card(window: Any, entry: LiverySnapshotEntry, card_width: int) -> QWidget:
    card = _change_dialog._archive_card_like_main(
        window,
        entry,
        _txt("삭제 전", "Before removal"),
        card_width,
    )
    return _alias_fix._remove_deleted_heading_and_match_main_frame(card)


def _entry_card(window: Any, key: str, entry: LiverySnapshotEntry, card_width: int) -> QWidget:
    if key == "removed":
        return _archive_card(window, entry, card_width)
    return _change_dialog._current_card_same_size(window, entry, card_width)


def _open_grouped_change_dialog(window: Any) -> None:
    diff = getattr(window, "_fh6_latest_livery_diff", None)
    if diff is None or getattr(diff, "baseline", False):
        return

    groups = _categorized_changes(window, diff)
    if not any(groups.values()):
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
    buttons: dict[str, QPushButton] = {}
    for key in _SECTION_ORDER:
        button = QPushButton(_section_text(key, len(groups[key])))
        button.setObjectName("secondary")
        button.setCheckable(True)
        button.setEnabled(bool(groups[key]))
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
    _responsive._apply_dialog_theme(dialog, scroll, host)

    state: dict[str, Any] = {
        "filter": None,
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

    def render(*, force: bool = False) -> None:
        viewport = scroll.viewport()
        viewport_width = viewport.width() if viewport is not None else 0
        if viewport_width <= 0:
            return

        margins = grid.contentsMargins()
        gap = max(0, grid.horizontalSpacing())
        columns, card_width = _responsive._dialog_grid_metrics(
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
        widgets: list[QWidget] = []
        row = 0
        selected = state["filter"]
        visible_sections = [
            key for key in _SECTION_ORDER
            if groups[key] and (selected is None or selected == key)
        ]

        for section_index, key in enumerate(visible_sections):
            header = _section_header(key, len(groups[key]))
            grid.addWidget(header, row, 0, 1, columns)
            header.show()
            widgets.append(header)
            row += 1

            col = 0
            for entry in groups[key]:
                card = _entry_card(window, key, entry, card_width)
                grid.addWidget(card, row, col)
                card.show()
                widgets.append(card)
                col += 1
                if col >= columns:
                    row += 1
                    col = 0
            if col:
                row += 1
            if section_index < len(visible_sections) - 1:
                row += 1

        state["widgets"] = widgets
        for column in range(_responsive.GRID_MAX_COLUMNS):
            grid.setColumnStretch(column, 1 if column < columns else 0)
        host.setMinimumWidth(0)
        host.updateGeometry()

    def set_filter(key: str, checked: bool) -> None:
        for other_key, button in buttons.items():
            if other_key == key:
                continue
            button.blockSignals(True)
            button.setChecked(False)
            button.blockSignals(False)
        state["filter"] = key if checked else None
        state["geometry"] = None
        render(force=True)

    for key, button in buttons.items():
        button.toggled.connect(lambda checked=False, k=key: set_filter(k, checked))

    controller = _responsive._ViewportResizeController(
        scroll.viewport(),
        lambda: render(force=False),
    )
    dialog._fh6_change_resize_controller = controller
    dialog._fh6_change_render = render
    dialog._fh6_change_scroll = scroll
    dialog._fh6_change_grid = grid
    dialog._fh6_change_groups = groups

    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    controller.request_now()


def _compact_grouped_change_banner(window: Any) -> None:
    banner = getattr(window, "refresh_diff_banner", None)
    view = getattr(window, "refresh_diff_view_button", None)
    diff = getattr(window, "_fh6_latest_livery_diff", None)
    if banner is None or view is None:
        return
    if diff is None or getattr(diff, "baseline", False):
        banner.hide()
        return

    groups = _categorized_changes(window, diff)
    added = len(groups["added"])
    removed = len(groups["removed"])
    duplicate = len(groups["duplicate"])
    if added + removed + duplicate <= 0:
        banner.hide()
        return

    view.setText(f"+{added}  −{removed}  ▣{duplicate}")
    view.setToolTip(
        _txt(
            f"새로고침 변경 · 추가 {added} · 제거 {removed} · 중복 {duplicate}\n클릭하여 보기",
            f"Refresh changes · Added {added} · Removed {removed} · Duplicate {duplicate}\nClick to view",
        )
    )
    banner.show()


def apply_v1_3_2_dashboard_change_group_patch(MainWindow: Any) -> None:
    """Apply final dashboard ratios, clean page titles, and grouped change view."""
    if getattr(MainWindow, "_fh6_v132_dashboard_change_group_patched", False):
        return

    # Existing runtime callbacks resolve these module globals at click/populate
    # time, so replacing them here updates the already-installed UI safely.
    _change_dialog._open_change_dialog_same_as_main = _open_grouped_change_dialog
    _release._compact_change_banner = _compact_grouped_change_banner

    original_memory_icon_refresh: Callable[[Any], None] = _memory._update_all_card_state_icons

    def memory_icon_refresh(window: Any) -> None:
        original_memory_icon_refresh(window)
        _update_dashboard_summary(window)

    _memory._update_all_card_state_icons = memory_icon_refresh

    original_init = MainWindow.__init__
    original_populate_all = MainWindow._populate_all

    def patched_init(self, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        _normalize_page_titles(self)
        _update_dashboard_summary(self)
        _compact_grouped_change_banner(self)

    def patched_populate_all(self) -> None:
        original_populate_all(self)
        _normalize_page_titles(self)
        _update_dashboard_summary(self)
        _compact_grouped_change_banner(self)

    MainWindow.__init__ = patched_init
    MainWindow._populate_all = patched_populate_all
    MainWindow._fh6_update_dashboard_applied_ratios = _update_dashboard_summary
    MainWindow._fh6_v132_dashboard_change_group_patched = True
