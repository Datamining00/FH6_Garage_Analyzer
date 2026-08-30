from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPoint, QSize, Qt, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget, QWidgetAction

from . import v1_3_2_dashboard_change_group_patch as _dashboard
from . import v1_3_2_release_layout_patch as _release
from . import v1_3_4_backup_export_patch as _backup_ui
from . import v1_3_4_card_features_patch as _features
from .v1_3_2_filter_alias_quality_patch import _ROW_STYLE
from .card_icons import icon as card_icon


_LOCKED_LIVERY_FILTER_MODE = 15
_RECENT_ADDED_COLOR = "#39e75f"
_RECENT_REMOVED_COLOR = "#ff4d5a"
_RECENT_DUPLICATE_COLOR = "#ffe600"


def _txt(ko: str, en: str) -> str:
    return _backup_ui._txt(ko, en)


def _locked_pref(window: Any, key: str) -> bool:
    if not key:
        return False
    preferences = getattr(window, "local_preferences", None)
    getter = getattr(preferences, "get_bool", None)
    if not callable(getter):
        return False
    return bool(getter(_features._lock_pref_key(key), False))


def _remove_backup_locked_filter(window: Any) -> None:
    action = getattr(window, "backup_locked_filter_action", None)
    if action is None:
        return
    try:
        action.setChecked(False)
        menu = getattr(window, "backup_filter_button", None)
        menu = menu.menu() if menu is not None else None
        if menu is not None:
            menu.removeAction(action)
        action.deleteLater()
    except RuntimeError:
        pass
    window.backup_locked_filter_action = None


def _install_livery_locked_filter(window: Any) -> None:
    button = getattr(window, "livery_check_filter", None)
    actions = getattr(button, "_actions", None)
    menu = button.menu() if button is not None and hasattr(button, "menu") else None
    if not isinstance(actions, dict) or menu is None or _LOCKED_LIVERY_FILTER_MODE in actions:
        return

    row = QPushButton(_txt("잠금된 리버리", "Locked liveries"))
    row.setCheckable(True)
    row.setIcon(card_icon("lock", "#7656e8", 22))
    row.setIconSize(QSize(22, 22))
    row.setToolTip(_txt("잠금이 활성화된 리버리만 표시", "Show only liveries with lock enabled"))
    row.setFixedHeight(36)
    row.setCursor(Qt.CursorShape.PointingHandCursor)
    row.setStyleSheet(_ROW_STYLE)
    row.setProperty("fh6FilterBaseLabel", _txt("잠금된 리버리", "Locked liveries"))
    row.toggled.connect(lambda checked=False, owner=button: owner._row_toggled(_LOCKED_LIVERY_FILTER_MODE, checked))
    action = QWidgetAction(menu)
    action.setDefaultWidget(row)
    menu.addAction(action)
    actions[_LOCKED_LIVERY_FILTER_MODE] = row


def _apply_locked_livery_layout(window: Any) -> None:
    button = getattr(window, "livery_check_filter", None)
    selected = button.selected_modes() if button is not None and hasattr(button, "selected_modes") else set()
    if _LOCKED_LIVERY_FILTER_MODE not in selected:
        return

    visible: list[Any] = []
    for card in getattr(window, "_livery_grid_cards", []) or []:
        try:
            shown = card.isVisible()
        except RuntimeError:
            continue
        if not shown:
            continue
        key = str(card.property("annotationKey") or "")
        locked = bool(card.property("fh6MoveLocked")) or _locked_pref(window, key)
        if locked:
            visible.append(card)
        else:
            unload = getattr(window, "_unload_livery_card_thumbnail", None)
            if callable(unload):
                unload(card)

    host = getattr(window, "livery_grid_host", None)
    layout = getattr(window, "livery_grid_layout", None)
    if host is None or layout is None:
        return
    host.setUpdatesEnabled(False)
    try:
        window._clear_livery_grid_layout()
        window._layout_visible_grid_cards("livery", visible)
        layout.activate()
    finally:
        host.setUpdatesEnabled(True)
    host.update()
    window._sync_livery_grid_card_widths()
    QTimer.singleShot(0, window._sync_livery_grid_card_widths)
    QTimer.singleShot(0, window._refresh_visible_livery_thumbnails)


def _recent_change_counts(window: Any) -> tuple[int, int, int]:
    diff = getattr(window, "_fh6_latest_livery_diff", None)
    if diff is None or bool(getattr(diff, "baseline", False)):
        return 0, 0, 0
    try:
        groups = _dashboard._categorized_changes(window, diff)
        return len(groups.get("added", [])), len(groups.get("removed", [])), len(groups.get("duplicate", []))
    except Exception:
        return (
            len(getattr(diff, "added", []) or []),
            len(getattr(diff, "removed", []) or []),
            len(getattr(diff, "changed", []) or []),
        )


def _ensure_recent_number_labels(view: QPushButton) -> tuple[QLabel, QLabel, QLabel]:
    existing = getattr(view, "_fh6_recent_number_labels", None)
    if isinstance(existing, tuple) and len(existing) == 3 and all(isinstance(item, QLabel) for item in existing):
        return existing

    view.setText("")
    layout = view.layout()
    if layout is None:
        layout = QHBoxLayout(view)
    else:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()
    layout.setContentsMargins(10, 0, 10, 0)
    layout.setSpacing(14)

    labels: list[QLabel] = []
    for color in (_RECENT_ADDED_COLOR, _RECENT_REMOVED_COLOR, _RECENT_DUPLICATE_COLOR):
        label = QLabel("0", view)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setMinimumWidth(16)
        label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        label.setStyleSheet(f"color:{color};background:transparent;font-weight:700;")
        layout.addWidget(label, 0, Qt.AlignmentFlag.AlignCenter)
        labels.append(label)
    result = (labels[0], labels[1], labels[2])
    view._fh6_recent_number_labels = result
    return result


def _update_recent_change_banner(window: Any) -> None:
    banner = getattr(window, "refresh_diff_banner", None)
    label = getattr(window, "refresh_diff_banner_label", None)
    view = getattr(window, "refresh_diff_view_button", None)
    if not isinstance(banner, QFrame) or not isinstance(view, QPushButton):
        return
    added, removed, duplicate = _recent_change_counts(window)
    if label is not None:
        label.hide()
    labels = _ensure_recent_number_labels(view)
    labels[0].setText(str(added))
    labels[1].setText(str(removed))
    labels[2].setText(str(duplicate))
    view.setToolTip(
        _txt(
            f"최근 변동 · 추가 {added} · 삭제 {removed} · 중복 {duplicate}\n클릭하여 보기",
            f"Recent changes · Added {added} · Removed {removed} · Duplicate {duplicate}\nClick to view",
        )
    )
    banner.show()


def _recent_display_row(window: Any) -> QHBoxLayout | None:
    pages = getattr(window, "pages", None)
    if pages is None:
        return None
    try:
        page = pages.widget(1)
    except Exception:
        return None
    root = page.layout() if isinstance(page, QWidget) else None
    controls_item = root.itemAt(1) if root is not None and root.count() > 1 else None
    controls = controls_item.layout() if controls_item is not None else None
    display_item = controls.itemAt(1) if controls is not None and controls.count() > 1 else None
    display_row = display_item.layout() if display_item is not None else None
    return display_row if isinstance(display_row, QHBoxLayout) else None


def _sync_recent_change_banner_width(window: Any) -> None:
    banner = getattr(window, "refresh_diff_banner", None)
    export = getattr(window, "livery_export_visible_button", None)
    pages = getattr(window, "pages", None)
    if not isinstance(banner, QFrame) or not isinstance(export, QPushButton) or pages is None:
        return
    try:
        page = pages.widget(1)
    except Exception:
        return
    if not isinstance(page, QWidget) or banner.parentWidget() is not page:
        return

    # Keep the recent-change control's right edge on the same vertical line as
    # the Export button below. The trailing layout stretch absorbs all remaining
    # width, so this fixed width never protrudes into the page margin/scrollbar.
    banner_left = banner.mapTo(page, QPoint(0, 0)).x()
    export_right = export.mapTo(page, QPoint(export.width(), 0)).x()
    target = max(86, export_right - banner_left)
    banner.setFixedWidth(target)


def _move_recent_change_banner_to_display_row(window: Any) -> None:
    banner = getattr(window, "refresh_diff_banner", None)
    pages = getattr(window, "pages", None)
    display_row = _recent_display_row(window)
    if not isinstance(banner, QFrame) or pages is None or display_row is None:
        return
    try:
        page = pages.widget(1)
    except Exception:
        return

    old_parent = banner.parentWidget()
    old_layout = old_parent.layout() if isinstance(old_parent, QWidget) else None
    if old_layout is not None:
        old_layout.removeWidget(banner)
    display_row.removeWidget(banner)

    banner.setParent(page)
    banner.setObjectName("refreshDiffBanner")
    banner.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
    banner.setMinimumWidth(86)
    banner.setStyleSheet("QFrame#refreshDiffBanner { background:transparent; border:0; }")

    inner = banner.layout()
    view = getattr(window, "refresh_diff_view_button", None)
    if inner is not None:
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(0)
        for index in range(inner.count()):
            inner.setStretch(index, 0)
        if isinstance(view, QPushButton):
            view_index = inner.indexOf(view)
            if view_index >= 0:
                inner.setStretch(view_index, 1)

    if isinstance(view, QPushButton):
        # Reuse the application's normal secondary-button visuals rather than a
        # standalone purple banner so this control belongs to the surrounding UI.
        view.setObjectName("secondary")
        view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        view.setMinimumWidth(86)
        view.setStyleSheet("")
        _ensure_recent_number_labels(view)

    # Insert immediately before the row's trailing stretch. Do not consume that
    # stretch: it is what keeps the right boundary aligned with the action row.
    insert_at = display_row.count()
    if display_row.count():
        tail = display_row.itemAt(display_row.count() - 1)
        if tail is not None and tail.widget() is None and tail.layout() is None:
            insert_at = display_row.count() - 1
    display_row.insertWidget(insert_at, banner, 0, Qt.AlignmentFlag.AlignVCenter)
    _update_recent_change_banner(window)
    QTimer.singleShot(0, lambda owner=window: _sync_recent_change_banner_width(owner))
    QTimer.singleShot(50, lambda owner=window: _sync_recent_change_banner_width(owner))


def apply_v1_4_ui_completion_patch(MainWindow: Any) -> None:
    if getattr(MainWindow, "_fh6_v14_ui_completion_patched", False):
        return

    original_init = MainWindow.__init__
    original_relayout = MainWindow._relayout_livery_grid
    original_set_lock = _features._set_livery_lock
    original_populate_all = MainWindow._populate_all

    def patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        _remove_backup_locked_filter(self)
        _install_livery_locked_filter(self)
        _move_recent_change_banner_to_display_row(self)

    def relayout(self: Any, *args: Any, **kwargs: Any):
        result = original_relayout(self, *args, **kwargs)
        _apply_locked_livery_layout(self)
        QTimer.singleShot(0, lambda owner=self: _sync_recent_change_banner_width(owner))
        return result

    def set_lock(window: Any, card: Any, key: str, locked: bool, *, persist: bool) -> None:
        original_set_lock(window, card, key, locked, persist=persist)
        button = getattr(window, "livery_check_filter", None)
        selected = button.selected_modes() if button is not None and hasattr(button, "selected_modes") else set()
        if persist and _LOCKED_LIVERY_FILTER_MODE in selected:
            search = getattr(window, "livery_search", None)
            text = search.text() if search is not None else ""
            QTimer.singleShot(0, lambda owner=window, query=text: owner._relayout_livery_grid(query))

    def populate_all(self: Any) -> None:
        original_populate_all(self)
        _update_recent_change_banner(self)
        QTimer.singleShot(0, lambda owner=self: _sync_recent_change_banner_width(owner))

    _release._compact_change_banner = _update_recent_change_banner
    _dashboard._compact_grouped_change_banner = _update_recent_change_banner
    _features._set_livery_lock = set_lock
    MainWindow.__init__ = patched_init
    MainWindow._relayout_livery_grid = relayout
    MainWindow._populate_all = populate_all
    MainWindow._fh6_v14_ui_completion_patched = True
