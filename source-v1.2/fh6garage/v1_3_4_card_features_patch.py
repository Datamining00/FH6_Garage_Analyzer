from __future__ import annotations

import weakref
from typing import Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import v1_3_2_change_dialog_folder_patch as _change_dialog
from . import v1_3_2_change_dialog_responsive_ui_fix as _dialog_responsive
from . import v1_3_2_dashboard_change_group_patch as _dashboard
from . import v1_3_2_responsive_columns_fix as _columns
from . import v1_3_2_responsiveness_sort_patch as _responsive
from .i18n import get_language, tr
from .ui import CopyValueLabel


_DUPLICATE_FILTER_MODE = 9
_METADATA_COLLAPSED_PREF = "card_metadata_right_collapsed"
_LOCK_PREF_PREFIX = "livery_move_locked::"
_METADATA_TOGGLE_WIDTH = 18
_METADATA_TOGGLE_HEIGHT = 48


def _txt(ko: str, en: str) -> str:
    return ko if (get_language() or "ko").lower().startswith("ko") else en


def _find_layout_containing(root: QLayout | None, widget: QWidget) -> QLayout | None:
    if root is None:
        return None
    for index in range(root.count()):
        item = root.itemAt(index)
        if item is None:
            continue
        if item.widget() is widget:
            return root
        child = item.layout()
        if child is None:
            continue
        found = _find_layout_containing(child, widget)
        if found is not None:
            return found
    return None


def _metadata_labels(card: QWidget) -> tuple[CopyValueLabel | None, CopyValueLabel | None, CopyValueLabel | None]:
    vehicle = creator = title = None
    for label in card.findChildren(CopyValueLabel):
        if label.prefix == _txt("차량", "Vehicle"):
            vehicle = label
        elif label.prefix == _txt("제작", "Creator"):
            creator = label
        elif label.prefix == _txt("제목", "Title"):
            title = label
    return vehicle, creator, title


def _metadata_collapsed(window: Any) -> bool:
    preferences = getattr(window, "local_preferences", None)
    getter = getattr(preferences, "get_bool", None)
    if callable(getter):
        return bool(getter(_METADATA_COLLAPSED_PREF, False))
    return bool(getattr(window, "_fh6_v134_metadata_collapsed", False))


def _apply_metadata_state(card: QWidget, collapsed: bool) -> None:
    grid = getattr(card, "_fh6_v134_metadata_grid", None)
    vehicle = getattr(card, "_fh6_v134_metadata_vehicle", None)
    creator = getattr(card, "_fh6_v134_metadata_creator", None)
    source = getattr(card, "_fh6_v134_metadata_source", None)
    title = getattr(card, "_fh6_v134_metadata_title", None)
    toggle = getattr(card, "_fh6_v134_metadata_toggle", None)
    if not isinstance(grid, QGridLayout):
        return
    if not all(isinstance(widget, QWidget) for widget in (vehicle, creator, source, title, toggle)):
        return

    for widget in (vehicle, creator, source, title, toggle):
        grid.removeWidget(widget)

    grid.setHorizontalSpacing(2)
    grid.setVerticalSpacing(0)
    grid.setColumnStretch(0, 1)
    grid.setColumnStretch(1, 0)
    grid.setColumnStretch(2, 0 if collapsed else 1)
    grid.setRowMinimumHeight(0, 24)
    grid.setRowMinimumHeight(1, 24)

    if collapsed:
        source.hide()
        title.hide()
        grid.addWidget(vehicle, 0, 0, 1, 2)
        grid.addWidget(creator, 1, 0, 1, 2)
        grid.addWidget(toggle, 0, 2, 2, 1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        toggle.setText("‹")
        toggle.setToolTip(_txt("출처와 제목 표시", "Show source and title"))
    else:
        source.show()
        title.show()
        grid.addWidget(vehicle, 0, 0)
        grid.addWidget(creator, 1, 0)
        grid.addWidget(toggle, 0, 1, 2, 1, Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(source, 0, 2)
        grid.addWidget(title, 1, 2)
        toggle.setText("›")
        toggle.setToolTip(_txt("출처와 제목 숨기기", "Hide source and title"))

    vehicle.show()
    creator.show()
    toggle.show()
    card.setProperty("fh6MetadataRightCollapsed", collapsed)
    grid.invalidate()
    grid.activate()


def _registered_metadata_cards(window: Any) -> list[QWidget]:
    refs = list(getattr(window, "_fh6_v134_metadata_card_refs", []) or [])
    alive: list[weakref.ReferenceType[QWidget]] = []
    cards: list[QWidget] = []
    for ref in refs:
        try:
            card = ref()
        except TypeError:
            card = None
        if card is None:
            continue
        try:
            card.objectName()
        except RuntimeError:
            continue
        alive.append(ref)
        cards.append(card)
    window._fh6_v134_metadata_card_refs = alive
    return cards


def _set_metadata_collapsed(window: Any, collapsed: bool) -> None:
    collapsed = bool(collapsed)
    preferences = getattr(window, "local_preferences", None)
    setter = getattr(preferences, "set_bool", None)
    if callable(setter):
        setter(_METADATA_COLLAPSED_PREF, collapsed)
    window._fh6_v134_metadata_collapsed = collapsed
    for card in _registered_metadata_cards(window):
        _apply_metadata_state(card, collapsed)


def _install_metadata_toggle(window: Any, card: QWidget) -> None:
    source = card.findChild(QLabel, "fh6AcquisitionPlaceholder")
    vehicle, creator, title = _metadata_labels(card)
    if source is None or vehicle is None or creator is None or title is None:
        return
    layout = _find_layout_containing(card.layout(), source)
    if not isinstance(layout, QGridLayout):
        return

    toggle = card.findChild(QToolButton, "fh6MetadataToggleButton")
    if toggle is None:
        toggle = QToolButton(card)
        toggle.setObjectName("fh6MetadataToggleButton")
        toggle.setFixedSize(_METADATA_TOGGLE_WIDTH, _METADATA_TOGGLE_HEIGHT)
        toggle.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        toggle.setStyleSheet(
            "QToolButton { background:#f4f5f8; color:#5f39d8; border:1px solid #d8dbe5; "
            "border-radius:5px; padding:0; font-size:13pt; font-weight:700; }"
            "QToolButton:hover { background:#eee9ff; border-color:#8c74ee; color:#5335c7; }"
            "QToolButton:pressed { background:#e3dcff; }"
        )
        toggle.clicked.connect(
            lambda _checked=False, owner=window: _set_metadata_collapsed(
                owner, not _metadata_collapsed(owner)
            )
        )

    card._fh6_v134_metadata_grid = layout
    card._fh6_v134_metadata_vehicle = vehicle
    card._fh6_v134_metadata_creator = creator
    card._fh6_v134_metadata_source = source
    card._fh6_v134_metadata_title = title
    card._fh6_v134_metadata_toggle = toggle

    refs = getattr(window, "_fh6_v134_metadata_card_refs", None)
    if not isinstance(refs, list):
        refs = []
        window._fh6_v134_metadata_card_refs = refs
    if not any(ref() is card for ref in refs if callable(ref)):
        refs.append(weakref.ref(card))

    _apply_metadata_state(card, _metadata_collapsed(window))


def _lock_pref_key(key: str) -> str:
    return f"{_LOCK_PREF_PREFIX}{key}"


def _set_livery_lock(window: Any, card: QWidget, key: str, locked: bool, *, persist: bool) -> None:
    lock = getattr(card, "_fh6_lock_placeholder_button", None)
    move = getattr(card, "_fh6_game_move_button", None)
    if not isinstance(lock, QToolButton) or not isinstance(move, QToolButton):
        return

    locked = bool(locked)
    if persist and key:
        preferences = getattr(window, "local_preferences", None)
        setter = getattr(preferences, "set_bool", None)
        if callable(setter):
            setter(_lock_pref_key(key), locked)

    if move.property("fh6UnlockedTooltip") is None:
        move.setProperty("fh6UnlockedTooltip", move.toolTip())
    move.setEnabled(not locked)
    if locked:
        move.setToolTip(
            _txt(
                "잠금됨: FH6 Assistant의 삭제용 인게임 이동이 비활성화되었습니다.",
                "Locked: FH6 Assistant in-game movement for deletion is disabled.",
            )
        )
        lock.setToolTip(
            _txt(
                "잠금됨 · Assistant의 인게임 이동만 차단합니다. 게임에서 직접 이동하거나 삭제하는 것은 차단하지 않습니다.",
                "Locked · Only Assistant in-game movement is blocked. Direct movement or deletion in the game is not blocked.",
            )
        )
    else:
        move.setToolTip(str(move.property("fh6UnlockedTooltip") or ""))
        lock.setToolTip(
            _txt(
                "잠그면 이 카드의 삭제용 인게임 이동만 비활성화합니다.",
                "Lock to disable only this card's Assistant in-game movement for deletion.",
            )
        )
    card.setProperty("fh6MoveLocked", locked)


def _install_livery_lock(window: Any, card: QWidget, key: str) -> None:
    lock = getattr(card, "_fh6_lock_placeholder_button", None)
    move = getattr(card, "_fh6_game_move_button", None)
    if not isinstance(lock, QToolButton) or not isinstance(move, QToolButton):
        return

    preferences = getattr(window, "local_preferences", None)
    getter = getattr(preferences, "get_bool", None)
    locked = bool(getter(_lock_pref_key(key), False)) if callable(getter) and key else False

    if not bool(lock.property("fh6FunctionalLockInstalled")):
        lock.setProperty("fh6FunctionalLockInstalled", True)
        lock.toggled.connect(
            lambda active=False, owner=window, target=card, item_key=key: _set_livery_lock(
                owner, target, item_key, active, persist=True
            )
        )

    # Restore persisted state without emitting the user-action signal. The
    # existing QIcon already contains separate checked/unchecked PNG pixmaps, so
    # the visual state follows setChecked() without any synthetic toggle.
    lock.blockSignals(True)
    lock.setChecked(locked)
    lock.blockSignals(False)
    _set_livery_lock(window, card, key, locked, persist=False)


def _duplicate_filter_active(window: Any) -> bool:
    button = getattr(window, "livery_check_filter", None)
    selected = getattr(button, "selected_modes", None)
    if not callable(selected):
        return False
    try:
        return _DUPLICATE_FILTER_MODE in set(selected())
    except (TypeError, RuntimeError):
        return False


def _duplicate_card_groups(window: Any, cards: list[QFrame]) -> list[tuple[str, list[QFrame]]]:
    groups: dict[str, list[QFrame]] = {}
    for card in cards:
        key = str(card.property("annotationKey") or "")
        record = None
        resolver = getattr(window, "_record_for_content_key", None)
        if key and callable(resolver):
            try:
                record = resolver("livery", key)
            except (RuntimeError, TypeError, ValueError):
                record = None
        kind = str(getattr(record, "kind", "") or "")
        digest = str(getattr(record, "content_sha256", "") or "").strip().casefold()
        group_key = f"{kind}:{digest}" if digest else f"unknown:{key}"
        groups.setdefault(group_key, []).append(card)
    return list(groups.items())


def _layout_duplicate_groups(window: Any, cards: list[QFrame]) -> None:
    layout = window.livery_grid_layout
    filtered: list[QFrame] = []
    for index, card in enumerate(cards):
        if _responsive._livery_visibility_allowed(window, card):
            filtered.append(card)
        _responsive._yield_busy_events(window, force=(index == 0))

    columns = _columns._current_grid_columns(window, "livery")
    window._fh6_livery_grid_columns = columns
    for column in range(_columns.GRID_MAX_COLUMNS):
        layout.setColumnStretch(column, 1 if column < columns else 0)

    headers = window._livery_group_headers
    row = 0
    item_index = 0
    for group_key, group_cards in _duplicate_card_groups(window, filtered):
        cache_key = f"duplicate::{group_key}"
        header = headers.get(cache_key)
        if header is None:
            header = QLabel()
            header.setObjectName("duplicateGroupHeader")
            header.setMinimumHeight(36)
            header.setStyleSheet(
                "QLabel#duplicateGroupHeader { background:#f0ecff; color:#4f32b4; "
                "border:1px solid #d8ceff; border-radius:8px; padding:8px 11px; "
                "font-size:10.5pt; font-weight:700; }"
            )
            headers[cache_key] = header
        header.setText(
            _txt(
                f"동일 리버리 · {len(group_cards)}개",
                f"Same livery · {len(group_cards)}",
            )
        )
        layout.addWidget(header, row, 0, 1, columns)
        header.show()
        row += 1
        _responsive._yield_busy_events(window, force=(item_index == 0))
        item_index += 1

        for index, card in enumerate(group_cards):
            layout.addWidget(card, row + index // columns, index % columns)
            card.show()
            _responsive._yield_busy_events(window)
            item_index += 1
        row += (len(group_cards) + columns - 1) // columns


def _recent_duplicate_groups(entries: list[Any]) -> list[tuple[str, list[Any]]]:
    grouped: dict[str, list[Any]] = {}
    for entry in entries:
        kind = str(getattr(entry, "kind", "") or "")
        digest = str(getattr(entry, "content_sha256", "") or "").strip().casefold()
        identity = str(getattr(entry, "identity", "") or "").strip().casefold()
        key = f"{kind}:{digest}" if digest else f"{kind}:identity:{identity}"
        grouped.setdefault(key, []).append(entry)
    return list(grouped.items())


def _duplicate_subheader(count: int) -> QLabel:
    label = QLabel(_txt(f"동일 리버리 · {count}개", f"Same livery · {count}"))
    label.setMinimumHeight(30)
    label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
    label.setStyleSheet(
        "background:#faf8ff;color:#5f39d8;border:1px solid #e3dcff;"
        "border-radius:7px;padding:5px 9px;font-weight:700;"
    )
    return label


def _open_grouped_change_dialog(window: Any) -> None:
    diff = getattr(window, "_fh6_latest_livery_diff", None)
    if diff is None or getattr(diff, "baseline", False):
        return

    groups = _dashboard._categorized_changes(window, diff)
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
    for key in _dashboard._SECTION_ORDER:
        button = QPushButton(_dashboard._section_text(key, len(groups[key])))
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
    _dialog_responsive._apply_dialog_theme(dialog, scroll, host)

    state: dict[str, Any] = {"filter": None, "geometry": None, "widgets": []}

    def clear_grid() -> None:
        while grid.count():
            item = grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        state["widgets"] = []

    def add_cards(entries: list[Any], key: str, card_width: int, columns: int, row: int, widgets: list[QWidget]) -> int:
        col = 0
        for entry in entries:
            card = _dashboard._entry_card(window, key, entry, card_width)
            grid.addWidget(card, row, col)
            card.show()
            widgets.append(card)
            col += 1
            if col >= columns:
                row += 1
                col = 0
        if col:
            row += 1
        return row

    def render(*, force: bool = False) -> None:
        viewport = scroll.viewport()
        viewport_width = viewport.width() if viewport is not None else 0
        if viewport_width <= 0:
            return

        margins = grid.contentsMargins()
        gap = max(0, grid.horizontalSpacing())
        columns, card_width = _dialog_responsive._dialog_grid_metrics(
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
            key
            for key in _dashboard._SECTION_ORDER
            if groups[key] and (selected is None or selected == key)
        ]

        for section_index, key in enumerate(visible_sections):
            header = _dashboard._section_header(key, len(groups[key]))
            grid.addWidget(header, row, 0, 1, columns)
            header.show()
            widgets.append(header)
            row += 1

            if key == "duplicate":
                duplicate_groups = _recent_duplicate_groups(groups[key])
                for subgroup_index, (_group_key, entries) in enumerate(duplicate_groups):
                    subheader = _duplicate_subheader(len(entries))
                    grid.addWidget(subheader, row, 0, 1, columns)
                    subheader.show()
                    widgets.append(subheader)
                    row += 1
                    row = add_cards(entries, key, card_width, columns, row, widgets)
                    if subgroup_index < len(duplicate_groups) - 1:
                        row += 1
            else:
                row = add_cards(groups[key], key, card_width, columns, row, widgets)

            if section_index < len(visible_sections) - 1:
                row += 1

        state["widgets"] = widgets
        for column in range(_dialog_responsive.GRID_MAX_COLUMNS):
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

    controller = _dialog_responsive._ViewportResizeController(
        scroll.viewport(), lambda: render(force=False)
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


def apply_v1_3_4_card_features_patch(MainWindow: Any) -> None:
    if getattr(MainWindow, "_fh6_v134_card_features_patched", False):
        return

    original_make_card = MainWindow._make_saved_content_card
    original_layout = _responsive._responsive_layout_visible_grid_cards

    def make_card(self: Any, content_type: str, record: Any, key: str):
        card = original_make_card(self, content_type, record, key)
        _install_metadata_toggle(self, card)
        if content_type == "livery" and not bool(card.property("fh6ArchiveCard")):
            _install_livery_lock(self, card, key)
        return card

    def layout_visible(self: Any, content_type: str, cards: list[QFrame]) -> None:
        if content_type == "livery" and _duplicate_filter_active(self):
            _layout_duplicate_groups(self, cards)
            return
        original_layout(self, content_type, cards)

    MainWindow._make_saved_content_card = make_card
    MainWindow._layout_visible_grid_cards = layout_visible
    _responsive._responsive_layout_visible_grid_cards = layout_visible
    _change_dialog._open_change_dialog_same_as_main = _open_grouped_change_dialog
    MainWindow._fh6_v134_card_features_patched = True
