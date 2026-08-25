from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .creator_aliases import CreatorAliasStore
from .i18n import get_language, tr
from .models import LiveryRecord, TuningRecord
from .refresh_history import (
    LiveryRefreshChange,
    LiverySnapshotEntry,
    cached_thumbnail_path,
)


def _txt(ko: str, en: str) -> str:
    return ko if get_language() == "ko" else en


def _open_integrated_change_dialog(window: Any) -> None:
    from .change_dialog_responsive import _open_responsive_change_dialog

    _open_responsive_change_dialog(window)


def _creator_display(window: Any, raw_name: str) -> str:
    raw = (raw_name or "").strip()
    if not raw:
        return tr("creator.none")
    return window.creator_aliases.display_name(raw)


def _creator_canonical(window: Any, raw_name: str) -> str:
    raw = (raw_name or "").strip()
    if not raw:
        return ""
    return window.creator_aliases.canonical_name(raw)


def _find_current_livery(window: Any, entry: LiverySnapshotEntry | None) -> LiveryRecord | None:
    if entry is None or window.result is None:
        return None
    records = [record for record in window.result.liveries if record.kind == entry.kind]
    identity = entry.identity.casefold()
    for record in records:
        physical = f"{record.kind}:{record.container_name.casefold()}"
        if physical.casefold() == identity:
            return record

    guid = (entry.guid or "").strip().casefold()
    if guid:
        matches = [
            record for record in records
            if (record.header.guid or "").strip().casefold() == guid
        ]
        if len(matches) == 1:
            return matches[0]

    digest = (entry.content_sha256 or "").strip().casefold()
    if digest:
        matches = [
            record for record in records
            if (record.content_sha256 or "").strip().casefold() == digest
        ]
        if len(matches) == 1:
            return matches[0]
    return None


def _decorate_creator_copy_label(window: Any, card: QWidget, raw_creator: str) -> None:
    display = _creator_display(window, raw_creator)
    prefix = tr("card.creator_label")
    for label in card.findChildren(QLabel):
        if getattr(label, "prefix", None) != prefix:
            continue
        setter = getattr(label, "setCopyValue", None)
        if callable(setter):
            setter(display)
        else:
            label.setText(f"{prefix}: {display}")
        for controller in getattr(card, "_fh6_metadata_elide_controllers", []):
            if getattr(controller, "label", None) is label:
                schedule = getattr(controller, "schedule", None)
                if callable(schedule):
                    schedule()
        break


def _normalize_card_alias_properties(window: Any, content_type: str, card: QWidget) -> None:
    key = str(card.property("annotationKey") or "")
    if not key:
        return
    record = window._record_for_content_key(content_type, key)
    if record is None:
        return

    raw = (record.header.creator or "").strip()
    current_search = str(card.property("searchText") or "")
    last_augmented = getattr(card, "_fh6_alias_last_search", None)
    if last_augmented is None or current_search != last_augmented:
        card._fh6_alias_base_search = current_search
    base_search = str(getattr(card, "_fh6_alias_base_search", current_search))

    if raw:
        group = window.creator_aliases.group_for(raw)
        display = window.creator_aliases.display_name(raw)
        augmented = " ".join(
            piece for piece in (base_search, display, *group.all_names()) if piece
        ).casefold()
        card.setProperty("creatorGroupKey", f"creator:{group.current.casefold()}")
        card.setProperty("creatorGroupLabel", display)
    else:
        augmented = base_search.casefold()
        card.setProperty("creatorGroupKey", "creator:")
        card.setProperty("creatorGroupLabel", tr("creator.none"))

    card.setProperty("searchText", augmented)
    card._fh6_alias_last_search = augmented


def _archive_card(window: Any, entry: LiverySnapshotEntry, heading: str) -> QFrame:
    card = QFrame()
    card.setObjectName("panel")
    card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(8)

    badge = QLabel(heading)
    badge.setStyleSheet(
        "background:#f0ecff;color:#5f39d8;border-radius:7px;"
        "padding:4px 8px;font-weight:700;"
    )
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(badge)

    image = QLabel()
    image.setMinimumHeight(220)
    image.setAlignment(Qt.AlignmentFlag.AlignCenter)
    image.setStyleSheet("background:#f1f2f6;border-radius:9px;color:#737787;")
    path = cached_thumbnail_path(entry)
    pixmap = None
    if path is not None:
        try:
            pixmap = window._pixmap_for(path, QSize(560, 260))
        except Exception:
            pixmap = None
    if isinstance(pixmap, QPixmap) and not pixmap.isNull():
        image.setPixmap(pixmap)
    else:
        image.setText(_txt("썸네일 없음", "No thumbnail"))
    layout.addWidget(image)

    vehicle = QLabel(window._car_label(entry.car_id))
    vehicle.setStyleSheet("font-weight:700;font-size:11pt;")
    vehicle.setWordWrap(True)
    layout.addWidget(vehicle)

    title = QLabel(f"{tr('card.title_label')}: {entry.name or '—'}")
    title.setWordWrap(True)
    layout.addWidget(title)

    creator = QLabel(f"{tr('card.creator_label')}: {_creator_display(window, entry.creator)}")
    creator.setWordWrap(True)
    if entry.creator:
        creator.setToolTip(_txt("기록 당시 제작자: ", "Recorded creator: ") + entry.creator)
    layout.addWidget(creator)

    if entry.description:
        description = QLabel(entry.description)
        description.setObjectName("muted")
        description.setWordWrap(True)
        layout.addWidget(description)

    # Historical/deleted cards intentionally contain no action buttons.
    card.setProperty("fh6ArchiveCard", True)
    return card


def _status_style(status: str) -> str:
    return {
        "added": "background:#e9f7ee;color:#237a43;border:1px solid #bfe6cc;",
        "removed": "background:#fff0f1;color:#b42d3a;border:1px solid #f0c4c8;",
        "changed": "background:#fff7e8;color:#8b5b0b;border:1px solid #efd5a5;",
    }.get(status, "background:#f1f2f6;color:#555a68;border:1px solid #dfe1e8;")


def _status_text(status: str) -> str:
    if status == "added":
        return _txt("+ 추가", "+ Added")
    if status == "removed":
        return _txt("− 삭제", "− Removed")
    return _txt("~ 변경", "~ Changed")


def _current_change_card(window: Any, entry: LiverySnapshotEntry) -> QWidget:
    record = _find_current_livery(window, entry)
    if record is None:
        return _archive_card(window, entry, _txt("현재 기록", "Current snapshot"))
    key = window._content_annotation_key("livery", record)
    card = window._make_saved_content_card("livery", record, key)
    _decorate_creator_copy_label(window, card, record.header.creator or "")
    try:
        window._load_livery_card_thumbnail(card)
    except Exception:
        pass
    return card


def _change_wrapper(window: Any, change: LiveryRefreshChange) -> tuple[QFrame, str]:
    status = change.status
    wrapper = QFrame()
    wrapper.setObjectName("changeResultItem")
    wrapper.setStyleSheet(
        "QFrame#changeResultItem { background:#ffffff;border:1px solid #e4e6ed;"
        "border-radius:12px; }"
    )
    outer = QVBoxLayout(wrapper)
    outer.setContentsMargins(10, 10, 10, 10)
    outer.setSpacing(8)

    badge = QLabel(_status_text(status))
    badge.setStyleSheet(
        _status_style(status) + "border-radius:7px;padding:5px 9px;font-weight:700;"
    )
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    outer.addWidget(badge, 0, Qt.AlignmentFlag.AlignLeft)

    if status == "added" and change.after is not None:
        outer.addWidget(_current_change_card(window, change.after))
    elif status == "removed" and change.before is not None:
        outer.addWidget(_archive_card(window, change.before, _txt("삭제 전", "Before removal")))
    elif status == "changed":
        compare = QHBoxLayout()
        compare.setSpacing(10)
        if change.before is not None:
            compare.addWidget(_archive_card(window, change.before, _txt("변경 전", "Before")), 1)
        if change.after is not None:
            compare.addWidget(_current_change_card(window, change.after), 1)
        outer.addLayout(compare)
    return wrapper, status


def _open_change_dialog(window: Any) -> None:
    diff = getattr(window, "_fh6_latest_livery_diff", None)
    if diff is None or getattr(diff, "baseline", False) or getattr(diff, "total", 0) <= 0:
        return

    dialog = QDialog(window)
    dialog.setWindowTitle(_txt("최근 리버리 변경사항", "Recent livery changes"))
    dialog.setModal(True)
    dialog.resize(1180, 820)
    root = QVBoxLayout(dialog)
    root.setContentsMargins(14, 14, 14, 14)
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
    close_button.clicked.connect(dialog.accept)
    controls.addWidget(close_button)
    root.addLayout(controls)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    host = QWidget()
    grid = QGridLayout(host)
    grid.setContentsMargins(2, 2, 2, 2)
    grid.setHorizontalSpacing(10)
    grid.setVerticalSpacing(10)
    grid.setAlignment(Qt.AlignmentFlag.AlignTop)
    scroll.setWidget(host)
    root.addWidget(scroll, 1)

    items: list[tuple[QWidget, str]] = [
        _change_wrapper(window, change)
        for change in [*diff.added, *diff.removed, *diff.changed]
    ]

    def repack(filter_name: str) -> None:
        while grid.count():
            item = grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
        row = 0
        col = 0
        for widget, status in items:
            if filter_name != "all" and status != filter_name:
                continue
            if status == "changed":
                if col:
                    row += 1
                    col = 0
                grid.addWidget(widget, row, 0, 1, 2)
                widget.show()
                row += 1
                continue
            grid.addWidget(widget, row, col)
            widget.show()
            col += 1
            if col >= 2:
                col = 0
                row += 1
        host.adjustSize()

    for key, button in buttons.items():
        button.clicked.connect(lambda _checked=False, k=key: repack(k))
    repack("all")
    dialog.exec()


def _observed_creator_names(window: Any) -> list[str]:
    names: dict[str, str] = {}
    result = getattr(window, "result", None)
    if result is not None:
        for record in [*result.liveries, *result.tunings]:
            name = (record.header.creator or "").strip()
            if name:
                names.setdefault(name.casefold(), name)
    for group in window.creator_aliases.groups:
        for name in group.all_names():
            if name:
                names.setdefault(name.casefold(), name)
    return sorted(names.values(), key=str.casefold)


def _refresh_alias_views(window: Any) -> None:
    reset_cards = getattr(window, "_fh6_v132_reset_ui_card_cache", None)
    if callable(reset_cards):
        reset_cards()
    if getattr(window, "result", None) is None:
        return
    window._populate_creator_table()
    window._populate_livery_table()
    window._populate_tuning_table()
    window._filter_dashboard_table(window.car_search.text())
    if window.dashboard_content_stack.currentIndex() == 1:
        window._update_selected_creator()


def _open_alias_dialog(window: Any) -> None:
    # Kept as the stable call site while the dialog implementation is separated
    # from the release patch layer.
    from .creator_alias_dialog import open_creator_alias_dialog

    open_creator_alias_dialog(window)


def initialize_creator_alias_ui(window: Any) -> None:
    sidebar = window.findChild(QFrame, "sidebar")
    if sidebar is not None and sidebar.layout() is not None:
        button = QPushButton(_txt("제작자 이름 관리", "Creator aliases"), sidebar)
        button.setObjectName("creatorAliasManagerButton")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setStyleSheet(
            "QPushButton { color:#c7c9d4;background:transparent;border:0;"
            "padding:8px 10px;text-align:left;border-radius:8px; }"
            "QPushButton:hover { background:#242632;color:white; }"
        )
        button.clicked.connect(lambda: _open_alias_dialog(window))
        sidebar.layout().insertWidget(1 + len(getattr(window, "nav_buttons", [])), button)
        window.creator_alias_button = button

    banner = QFrame()
    banner.setObjectName("refreshDiffBanner")
    banner.setStyleSheet(
        "QFrame#refreshDiffBanner { background:#eee9ff;border:1px solid #d8ceff;"
        "border-radius:9px; }"
    )
    row = QHBoxLayout(banner)
    row.setContentsMargins(11, 7, 8, 7)
    label = QLabel()
    label.setStyleSheet("color:#4f35aa;font-weight:700;")
    view = QPushButton(_txt("보기", "View"))
    view.setObjectName("secondary")
    view.clicked.connect(lambda: _open_integrated_change_dialog(window))
    row.addWidget(label)
    row.addStretch(1)
    row.addWidget(view)
    banner.hide()
    window.refresh_diff_banner = banner
    window.refresh_diff_banner_label = label
    window.refresh_diff_view_button = view

    central = window.centralWidget()
    root_layout = central.layout() if central is not None else None
    if root_layout is not None and root_layout.count() >= 2:
        content = root_layout.itemAt(1).widget()
        content_layout = content.layout() if content is not None else None
        if content_layout is not None:
            content_layout.insertWidget(1, banner)


def update_change_banner(window: Any) -> None:
    banner = getattr(window, "refresh_diff_banner", None)
    label = getattr(window, "refresh_diff_banner_label", None)
    if banner is None or label is None:
        return
    diff = getattr(window, "_fh6_latest_livery_diff", None)
    if diff is None or diff.baseline or diff.total <= 0:
        banner.hide()
        return
    label.setText(
        _txt(
            f"새로고침 변경 · 추가 {len(diff.added)} · 삭제 {len(diff.removed)} · 변경 {len(diff.changed)}",
            f"Refresh changes · Added {len(diff.added)} · Removed {len(diff.removed)} · Changed {len(diff.changed)}",
        )
    )
    banner.show()
