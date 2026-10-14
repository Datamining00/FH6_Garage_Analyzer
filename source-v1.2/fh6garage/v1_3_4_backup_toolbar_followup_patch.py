from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QMessageBox, QPushButton, QToolButton

from . import v1_3_4_backup_export_patch as _backup_ui
from . import v1_3_4_backup_export_performance_ui_patch as _perf
from . import v1_3_4_backup_import_refinement_patch as _ref
from .backup_export import BackupRepositoryError
from .card_icons import icon as card_icon
from .models import LiveryRecord


def _txt(ko: str, en: str) -> str:
    return _backup_ui._txt(ko, en)


def _status_counts(window: Any) -> tuple[int, int, int]:
    """Return total backup, game-only, and game+backup counts.

    The backup page remains repository-centric, but the compact status row also
    reports game-only records so the user can see how much still needs backup.
    """
    all_items = _perf._backup_items(window)
    backup_only = sum(1 for _entry, _record, location in all_items if location == "backup")
    game_only = sum(1 for _entry, _record, location in all_items if location == "game")
    both = sum(1 for _entry, _record, location in all_items if location == "both")
    return backup_only + both, game_only, both


def _status_text(window: Any) -> str:
    total_backup, game_only, both = _status_counts(window)
    return _txt(
        f"전체 백업 {total_backup} \\ 게임 {game_only} \\ 게임+백업 {both}",
        f"Total backup {total_backup} \\ Game {game_only} \\ Game+Backup {both}",
    )


def _rebuild_backup_cards(window: Any) -> None:
    """Repository-only card rebuild with three-way compact counts."""
    if not hasattr(window, "backup_grid_layout"):
        return

    generation = int(getattr(window, "_fh6_backup_build_generation", 0)) + 1
    window._fh6_backup_build_generation = generation
    _backup_ui._clear_backup_grid(window)
    try:
        items = _ref._backup_items(window)
        status = _status_text(window)
    except BackupRepositoryError as exc:
        window.backup_status_label.setText(
            _txt("백업 인덱스를 읽을 수 없습니다.", "Backup index cannot be read.")
        )
        QMessageBox.warning(
            window,
            _txt("백업 인덱스 오류", "Backup index error"),
            str(exc),
        )
        return

    total = len(items)
    factory = getattr(window, "_fh6_backup_original_make_saved_content_card", None)
    if not callable(factory):
        return
    if total == 0:
        window.backup_status_label.setText(status)
        _backup_ui._relayout_backup(window)
        return

    window.backup_status_label.setText(
        _txt(
            f"백업 목록 준비 중 0/{total} · {status}",
            f"Preparing backup list 0/{total} · {status}",
        )
    )

    def build_chunk(start: int = 0) -> None:
        if generation != getattr(window, "_fh6_backup_build_generation", 0):
            return
        end = min(total, start + _perf._CARD_BUILD_CHUNK)
        for index in range(start, end):
            entry, record, location = items[index]
            key = f"backup::{record.kind}::{record.content_sha256 or record.container_name}::{index}"
            card = factory("livery", record, key)
            _ref._configure_backup_card(window, card, record, entry, location)
            card.setProperty("backupRecord", record)
            window._fh6_backup_cards.append(card)

        if end < total:
            window.backup_status_label.setText(
                _txt(
                    f"백업 목록 준비 중 {end}/{total} · {status}",
                    f"Preparing backup list {end}/{total} · {status}",
                )
            )
            QTimer.singleShot(0, lambda next_start=end: build_chunk(next_start))
            return

        window.backup_status_label.setText(status)
        _backup_ui._relayout_backup(window)
        QTimer.singleShot(0, lambda owner=window: _backup_ui._sync_backup_widths(owner))
        QTimer.singleShot(0, lambda owner=window: _backup_ui._refresh_backup_thumbnails(owner))

    QTimer.singleShot(0, build_chunk)


def _set_exclusive_pair(
    window: Any,
    first: QPushButton,
    second: QPushButton,
    attribute: str,
) -> None:
    group = QButtonGroup(window)
    group.setExclusive(True)
    group.addButton(first)
    group.addButton(second)
    first.blockSignals(True)
    second.blockSignals(True)
    first.setChecked(True)
    second.setChecked(False)
    first.blockSignals(False)
    second.blockSignals(False)
    setattr(window, attribute, group)


def _selected_source_kind(window: Any) -> str:
    auction = getattr(window, "backup_auction_toggle", None)
    return "SoulBoundLivery" if isinstance(auction, QPushButton) and auction.isChecked() else "Livery"


def _game_only_export_records(window: Any) -> list[LiveryRecord]:
    wanted_kind = _selected_source_kind(window)
    needle = str(getattr(getattr(window, "backup_search", None), "text", lambda: "")() or "").strip().casefold()
    records: list[LiveryRecord] = []
    for _entry, record, location in _perf._backup_items(window):
        if location != "game" or record.kind != wanted_kind:
            continue
        if needle:
            haystack = " ".join(
                (
                    record.header.name or "",
                    record.header.creator or "",
                    window._car_label(record.car_id),
                    str(record.car_id or ""),
                    record.header.description or "",
                    record.kind or "",
                )
            ).casefold()
            if needle not in haystack:
                continue
        records.append(record)
    return records


def _export_game_only(window: Any) -> None:
    records = _game_only_export_records(window)
    if not records:
        QMessageBox.information(
            window,
            _txt("내보내기", "Export"),
            _txt(
                "현재 선택한 리버리 종류에서 백업이 필요한 게임 항목이 없습니다.",
                "There are no game-only items to back up for the selected livery source.",
            ),
        )
        return
    _backup_ui._request_export(window, records)


def _install_backup_export_button(window: Any) -> None:
    if isinstance(getattr(window, "backup_export_button", None), QPushButton):
        return
    creator = getattr(window, "backup_creator_group_button", None)
    page = getattr(window, "backup_page", None)
    root = page.layout() if page is not None else None
    if not isinstance(creator, QPushButton) or root is None:
        return
    row = _ref._layout_with_widget(root, creator)
    if not isinstance(row, QHBoxLayout):
        return

    button = QPushButton(_txt("내보내기", "Export"))
    button.setObjectName("secondary")
    button.setIcon(card_icon("export", _backup_ui._ACTIVE_COLOR, 20))
    button.setIconSize(QSize(20, 20))
    button.setToolTip(
        _txt(
            "현재 선택한 리버리 종류의 게임 전용 항목을 백업으로 내보내기",
            "Export game-only items for the selected livery source to backup",
        )
    )
    button.clicked.connect(lambda _checked=False, owner=window: _export_game_only(owner))

    index = row.indexOf(creator)
    row.insertWidget(index + 1 if index >= 0 else row.count(), button)
    window.backup_export_button = button

    source = getattr(window, "livery_export_visible_button", None)
    if isinstance(source, QPushButton):
        button.setFont(source.font())
        button.setStyleSheet(source.styleSheet())
        button.setSizePolicy(source.sizePolicy())
        button.setMinimumHeight(source.minimumSizeHint().height())


def _configure_exclusive_filters(window: Any) -> None:
    livery = getattr(window, "backup_livery_toggle", None)
    auction = getattr(window, "backup_auction_toggle", None)
    backup = getattr(window, "backup_only_toggle", None)
    both = getattr(window, "backup_both_toggle", None)
    if isinstance(livery, QPushButton) and isinstance(auction, QPushButton):
        _set_exclusive_pair(window, livery, auction, "_fh6_backup_source_group")
    if isinstance(backup, QPushButton) and isinstance(both, QPushButton):
        _set_exclusive_pair(window, backup, both, "_fh6_backup_location_group")
        _ref._set_backup_location_filter(window, "backup")
    _backup_ui._relayout_backup(window)


def apply_v1_3_4_backup_toolbar_followup_patch(MainWindow: Any) -> None:
    if getattr(MainWindow, "_fh6_v134_backup_toolbar_followup_patched", False):
        return

    # Any export/import completion routed through the earlier backup module must
    # rebuild using the final repository-only card view and status contract.
    _ref._rebuild_backup_cards = _rebuild_backup_cards
    _backup_ui._rebuild_backup_cards = _rebuild_backup_cards

    original_init = MainWindow.__init__

    def patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        _configure_exclusive_filters(self)
        _install_backup_export_button(self)
        _rebuild_backup_cards(self)

    MainWindow.__init__ = patched_init
    MainWindow._fh6_v134_backup_toolbar_followup_patched = True
