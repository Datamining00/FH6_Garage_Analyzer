from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QSize, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QColor, QIcon
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGraphicsColorizeEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .backup_export import (
    BackupRepositoryError,
    ExportSummary,
    backup_contains_record,
    backup_records,
    export_records,
    game_contains_backup_entry,
    load_index,
)
from .card_icons import icon as card_icon
from .i18n import get_language, tr
from .models import LiveryRecord
from .v1_3_ui_patch import GRID_MAX_COLUMNS, GRID_MIN_COLUMNS, GRID_TARGET_CARD_WIDTH


_BACKUP_PATH_KEY = "backup_repository_path"
_ACTIVE_COLOR = "#5f39d8"
_INACTIVE_COLOR = "#555a68"


def _txt(ko: str, en: str) -> str:
    return ko if (get_language() or "ko").lower().startswith("ko") else en


def _backup_root(window: Any) -> Path | None:
    raw = ""
    edit = getattr(window, "backup_path_edit", None)
    if isinstance(edit, QLineEdit):
        raw = edit.text().strip()
    if not raw:
        raw = window.settings.value(_BACKUP_PATH_KEY, "", str).strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.is_dir() else None


def _paths_overlap(left: Path, right: Path) -> bool:
    try:
        left = left.resolve()
        right = right.resolve()
    except OSError:
        return False
    return left == right or left in right.parents or right in left.parents


def _backup_path_is_safe(window: Any, root: Path) -> bool:
    result = getattr(window, "result", None)
    metadata = getattr(result, "metadata", None)
    save_root = getattr(metadata, "save_root", None)
    if isinstance(save_root, Path) and _paths_overlap(root, save_root):
        return False
    return True


def _action_style(active: bool) -> str:
    if active:
        return (
            "QToolButton { background:#eee9ff; border:1px solid #8c74ee; "
            "border-radius:8px; padding:0; }"
            "QToolButton:hover { background:#e5deff; border-color:#6e4bf2; }"
        )
    return (
        "QToolButton { background:rgba(255,255,255,238); border:1px solid #dfe1e8; "
        "border-radius:8px; padding:0; }"
        "QToolButton:hover { border-color:#8c74ee; background:#f2edff; }"
    )


def _set_export_state(window: Any, card: Any, record: LiveryRecord) -> None:
    button = getattr(card, "_fh6_export_placeholder_button", None)
    if not isinstance(button, QToolButton):
        return
    root = _backup_root(window)
    exported = False
    if root is not None:
        try:
            exported = backup_contains_record(root, record, hash_if_needed=False)
        except BackupRepositoryError:
            exported = False
    button.setEnabled(True)
    button.setIcon(card_icon("export", _ACTIVE_COLOR if exported else _INACTIVE_COLOR, 20))
    button.setIconSize(QSize(20, 20))
    button.setStyleSheet(_action_style(exported))
    button.setProperty("fh6Exported", exported)
    button.setToolTip(
        _txt("이미 백업됨 · 다시 확인/내보내기", "Already backed up · verify/export again")
        if exported
        else _txt("이 리버리 내보내기", "Export this livery")
    )

    if not bool(button.property("fh6ExportActionInstalled")):
        button.setProperty("fh6ExportActionInstalled", True)
        button.clicked.connect(
            lambda _checked=False, owner=window, item=record: _request_export(owner, [item])
        )


def _refresh_main_export_states(window: Any) -> None:
    resolver = getattr(window, "_record_for_content_key", None)
    if not callable(resolver):
        return
    for card in getattr(window, "_livery_grid_cards", []):
        key = str(card.property("annotationKey") or "")
        record = resolver("livery", key) if key else None
        if isinstance(record, LiveryRecord):
            _set_export_state(window, card, record)


def _confirm_keep_source(window: Any, count: int, *, operation: str) -> bool:
    box = QMessageBox(window)
    if operation == "export":
        box.setWindowTitle(_txt("내보내기", "Export"))
        box.setText(
            _txt(
                f"{count}개 항목을 내보낸 뒤 원본을 삭제하시겠습니까?\n\n"
                "현재 버전에서는 게임 세이브 직접 삭제가 안전 검증 전 비활성화되어 있습니다.",
                f"Delete the source after exporting {count} item(s)?\n\n"
                "Direct deletion from the game save is disabled until save-layout safety is verified.",
            )
        )
    else:
        box.setWindowTitle(_txt("들여오기 준비", "Import preparation"))
        box.setText(
            _txt(
                "들여온 뒤 백업 원본을 삭제하시겠습니까?\n\n"
                "실제 들여오기는 Current/숫자 폴더의 저장 규칙 검증 전 비활성화되어 있으며, "
                "현재는 어떤 원본도 삭제하지 않습니다.",
                "Delete the backup source after importing?\n\n"
                "Actual import is disabled until the Current/numbered-folder save rules are verified, "
                "and no source is deleted in this version.",
            )
        )
    box.setIcon(QMessageBox.Icon.Question)
    keep = box.addButton(_txt("원본 유지", "Keep source"), QMessageBox.ButtonRole.AcceptRole)
    delete = box.addButton(_txt("원본 삭제", "Delete source"), QMessageBox.ButtonRole.DestructiveRole)
    delete.setEnabled(False)
    delete.setToolTip(
        _txt("저장 구조 검증 후 활성화됩니다.", "Available after save-layout verification.")
    )
    cancel = box.addButton(_txt("취소", "Cancel"), QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(keep)
    box.exec()
    return box.clickedButton() is keep and box.clickedButton() is not cancel


class _ExportWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, root: Path, records: list[LiveryRecord]):
        super().__init__()
        self.root = root
        self.records = records

    @Slot()
    def run(self) -> None:
        try:
            self.finished.emit(export_records(self.root, self.records))
        except Exception as exc:  # noqa: BLE001 - worker boundary
            self.failed.emit(f"{type(exc).__name__}: {exc}")


def _ensure_backup_root(window: Any) -> Path | None:
    root = _backup_root(window)
    if root is None:
        _choose_backup_folder(window)
        root = _backup_root(window)
    if root is None:
        return None
    if not _backup_path_is_safe(window, root):
        QMessageBox.warning(
            window,
            _txt("백업 경로 오류", "Invalid backup path"),
            _txt(
                "게임 세이브 폴더 자체 또는 그 상·하위 폴더는 백업 경로로 사용할 수 없습니다.",
                "The game save folder, its parent, or its child folder cannot be used as the backup repository.",
            ),
        )
        return None
    return root


def _request_export(window: Any, records: list[LiveryRecord]) -> None:
    if getattr(window, "_fh6_export_running", False) or not records:
        return
    root = _ensure_backup_root(window)
    if root is None:
        return
    if not _confirm_keep_source(window, len(records), operation="export"):
        return

    window._fh6_export_running = True
    bulk = getattr(window, "livery_export_visible_button", None)
    choose = getattr(window, "backup_choose_button", None)
    if isinstance(bulk, QPushButton):
        bulk.setEnabled(False)
    if isinstance(choose, QPushButton):
        choose.setEnabled(False)
    window._begin_busy(_txt("내보내는 중", "Exporting"))

    thread = QThread(window)
    worker = _ExportWorker(root, list(records))
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(lambda result, owner=window: _export_finished(owner, result))
    worker.failed.connect(lambda message, owner=window: _export_failed(owner, message))
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.finished.connect(lambda owner=window: _clear_export_thread(owner))
    window._fh6_export_thread = thread
    window._fh6_export_worker = worker
    thread.start()


def _clear_export_thread(window: Any) -> None:
    window._fh6_export_thread = None
    window._fh6_export_worker = None


def _finish_export_ui(window: Any) -> None:
    window._fh6_export_running = False
    bulk = getattr(window, "livery_export_visible_button", None)
    choose = getattr(window, "backup_choose_button", None)
    if isinstance(bulk, QPushButton):
        bulk.setEnabled(True)
    if isinstance(choose, QPushButton):
        choose.setEnabled(True)
    window._end_busy()


def _export_finished(window: Any, result: object) -> None:
    _finish_export_ui(window)
    if not isinstance(result, ExportSummary):
        _export_failed(window, _txt("알 수 없는 내보내기 결과", "Unknown export result"), already_finished=True)
        return
    _refresh_main_export_states(window)
    _rebuild_backup_cards(window)
    exported = len(result.exported)
    skipped = len(result.skipped)
    failed = len(result.failed)
    message = _txt(
        f"내보내기 완료 · 신규 {exported} · 중복 건너뜀 {skipped} · 실패 {failed}",
        f"Export complete · new {exported} · duplicates skipped {skipped} · failed {failed}",
    )
    window._show_status(message, 8000)
    if failed:
        details = "\n".join(f"{name}: {error}" for name, error in result.failed[:8])
        QMessageBox.warning(window, _txt("내보내기 완료", "Export complete"), message + "\n\n" + details)
    else:
        QMessageBox.information(window, _txt("내보내기 완료", "Export complete"), message)


def _export_failed(window: Any, message: str, *, already_finished: bool = False) -> None:
    if not already_finished:
        _finish_export_ui(window)
    QMessageBox.warning(window, _txt("내보내기 실패", "Export failed"), message)


def _visible_game_liveries(window: Any) -> list[LiveryRecord]:
    resolver = getattr(window, "_record_for_content_key", None)
    if not callable(resolver):
        return []
    records: list[LiveryRecord] = []
    seen: set[int] = set()
    for card in getattr(window, "_livery_grid_cards", []):
        if not card.isVisible():
            continue
        key = str(card.property("annotationKey") or "")
        record = resolver("livery", key) if key else None
        if isinstance(record, LiveryRecord) and id(record) not in seen:
            seen.add(id(record))
            records.append(record)
    return records


def _export_visible(window: Any) -> None:
    records = _visible_game_liveries(window)
    if not records:
        QMessageBox.information(
            window,
            _txt("내보내기", "Export"),
            _txt("현재 표시된 리버리가 없습니다.", "There are no currently displayed liveries."),
        )
        return
    _request_export(window, records)


def _install_bulk_export_button(window: Any) -> None:
    if isinstance(getattr(window, "livery_export_visible_button", None), QPushButton):
        return
    row = getattr(window, "_saved_content_action_rows", {}).get("livery")
    if row is None:
        return
    button = QPushButton(_txt("내보내기", "Export"))
    button.setObjectName("secondary")
    button.setIcon(card_icon("export", _ACTIVE_COLOR, 20))
    button.setIconSize(QSize(20, 20))
    button.setToolTip(
        _txt("현재 화면에 표시된 모든 리버리 내보내기", "Export every livery currently displayed")
    )
    button.clicked.connect(lambda _checked=False, owner=window: _export_visible(owner))
    row.insertWidget(max(0, row.count() - 1), button)
    window.livery_export_visible_button = button


def _choose_backup_folder(window: Any) -> None:
    current = window.settings.value(_BACKUP_PATH_KEY, "", str).strip()
    start = current if current and Path(current).is_dir() else str(Path.home())
    chosen = QFileDialog.getExistingDirectory(
        window,
        _txt("백업 저장 경로 선택", "Choose backup repository"),
        start,
    )
    if not chosen:
        return
    path = Path(chosen).expanduser().resolve()
    if not _backup_path_is_safe(window, path):
        QMessageBox.warning(
            window,
            _txt("백업 경로 오류", "Invalid backup path"),
            _txt(
                "게임 세이브 폴더 자체 또는 그 상·하위 폴더는 백업 경로로 사용할 수 없습니다.",
                "The game save folder, its parent, or its child folder cannot be used as the backup repository.",
            ),
        )
        return
    window.settings.setValue(_BACKUP_PATH_KEY, str(path))
    window.backup_path_edit.setText(str(path))
    _refresh_main_export_states(window)
    _rebuild_backup_cards(window)


def _backup_columns(window: Any) -> int:
    scroll = getattr(window, "backup_grid_scroll", None)
    layout = getattr(window, "backup_grid_layout", None)
    if scroll is None or layout is None:
        return GRID_MIN_COLUMNS
    viewport = scroll.viewport()
    if viewport is None or viewport.width() <= 0:
        return GRID_MIN_COLUMNS
    margins = layout.contentsMargins()
    inner = max(1, viewport.width() - margins.left() - margins.right() - 4)
    return max(GRID_MIN_COLUMNS, min(GRID_MAX_COLUMNS, inner // GRID_TARGET_CARD_WIDTH))


def _backup_sort_key(window: Any, item: tuple[Any, ...]) -> tuple[Any, ...]:
    record: LiveryRecord = item[1]
    mode = getattr(window, "_fh6_backup_sort_mode", "default")
    if mode == "brand":
        return window._vehicle_brand_sort_key(record)
    if mode == "creator":
        creator = (record.header.creator or "").strip()
        return (1 if not creator else 0, creator.casefold(), window._car_label(record.car_id).casefold())
    if mode == "download":
        return (-(record.downloaded_at or -1.0),)
    return (str(record.kind).casefold(), str(record.container_name).casefold())


def _game_records(window: Any) -> list[LiveryRecord]:
    result = getattr(window, "result", None)
    if result is None:
        return []
    return [
        record for record in result.liveries
        if isinstance(record, LiveryRecord) and record.kind in {"Livery", "SoulBoundLivery"}
    ]


def _matched_game_records(entry: dict[str, Any], records: list[LiveryRecord]) -> set[int]:
    kind = str(entry.get("kind") or "").casefold()
    container = str(entry.get("original_container_name") or "").casefold()
    digest = str(entry.get("content_sha256") or "").casefold()
    matched: set[int] = set()
    for record in records:
        if str(record.kind or "").casefold() != kind:
            continue
        record_digest = str(record.content_sha256 or "").casefold()
        if container and str(record.container_name or "").casefold() == container:
            matched.add(id(record))
        elif digest and record_digest and digest == record_digest:
            matched.add(id(record))
    return matched


def _location_text(location: str) -> str:
    mapping = {
        "backup": _txt("위치: 백업", "Location: Backup"),
        "game": _txt("위치: 게임", "Location: Game"),
        "both": _txt("위치: 게임 + 백업", "Location: Game + Backup"),
    }
    return mapping.get(location, mapping["backup"])


def _configure_import_button(window: Any, card: Any, location: str) -> None:
    button = getattr(card, "_fh6_export_placeholder_button", None)
    if not isinstance(button, QToolButton):
        return
    game_and_backup = location == "both"
    has_backup = location in {"backup", "both"}
    button.setObjectName("fh6ImportButton")
    button.setIcon(card_icon("import", _ACTIVE_COLOR if game_and_backup else _INACTIVE_COLOR, 20))
    button.setIconSize(QSize(20, 20))
    button.setStyleSheet(_action_style(game_and_backup))
    button.setEnabled(has_backup)
    button.setProperty("fh6Imported", game_and_backup)
    if not has_backup:
        button.setToolTip(_txt("게임에만 존재 · 백업본이 없어 들여올 수 없습니다.", "Game only · no backup copy is available to import."))
    elif game_and_backup:
        button.setToolTip(_txt("이미 게임 + 백업에 존재", "Already present in game + backup"))
    else:
        button.setToolTip(_txt("들여오기 · 현재 실제 복원은 비활성", "Import · actual restore is currently disabled"))
    if has_backup and not bool(button.property("fh6ImportPreviewInstalled")):
        button.setProperty("fh6ImportPreviewInstalled", True)
        button.clicked.connect(
            lambda _checked=False, owner=window: _confirm_keep_source(owner, 1, operation="import")
        )


def _apply_game_only_grayscale(card: Any) -> None:
    image = getattr(card, "_fh6_image_label", None)
    if not isinstance(image, QLabel):
        return
    effect = QGraphicsColorizeEffect(image)
    effect.setColor(QColor("#7f7f7f"))
    effect.setStrength(1.0)
    image.setGraphicsEffect(effect)
    card._fh6_backup_grayscale_effect = effect


def _configure_backup_card(window: Any, card: Any, record: LiveryRecord, location: str) -> None:
    source = card.findChild(QLabel, "fh6AcquisitionPlaceholder")
    if isinstance(source, QLabel):
        source.setText(_location_text(location))
    move = getattr(card, "_fh6_game_move_button", None)
    lock = getattr(card, "_fh6_lock_placeholder_button", None)
    if isinstance(move, QToolButton):
        move.hide()
        move.setEnabled(False)
    if isinstance(lock, QToolButton):
        lock.hide()
        lock.setEnabled(False)
    _configure_import_button(window, card, location)
    if location == "game":
        _apply_game_only_grayscale(card)
    card.setProperty("backupLocation", location)
    card.setProperty(
        "searchText",
        " ".join(
            (
                record.header.name or "",
                record.header.creator or "",
                window._car_label(record.car_id),
                str(record.car_id or ""),
                record.kind or "",
                _location_text(location),
            )
        ).casefold(),
    )
    card.setProperty("vehicleGroupKey", f"id:{record.car_id}" if record.car_id is not None else "unknown")
    card.setProperty("vehicleGroupLabel", window._car_label(record.car_id))
    creator = (record.header.creator or "").strip() or tr("creator.none")
    card.setProperty("creatorGroupKey", f"creator:{creator.casefold()}")
    card.setProperty("creatorGroupLabel", creator)


def _backup_items(window: Any) -> list[tuple[dict[str, Any] | None, LiveryRecord, str]]:
    root = _backup_root(window)
    game = _game_records(window)
    items: list[tuple[dict[str, Any] | None, LiveryRecord, str]] = []
    represented: set[int] = set()
    if root is not None:
        for entry, record in backup_records(root):
            matched = _matched_game_records(entry, game)
            represented.update(matched)
            location = "both" if matched or game_contains_backup_entry(entry, game) else "backup"
            items.append((entry, record, location))
    for record in game:
        if id(record) not in represented:
            items.append((None, record, "game"))
    items.sort(key=lambda item: _backup_sort_key(window, item))
    return items


def _clear_backup_grid(window: Any) -> None:
    layout = getattr(window, "backup_grid_layout", None)
    if layout is not None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
    for card in getattr(window, "_fh6_backup_cards", []):
        card.deleteLater()
    window._fh6_backup_cards = []
    for header in getattr(window, "_fh6_backup_headers", {}).values():
        header.hide()


def _rebuild_backup_cards(window: Any) -> None:
    if not hasattr(window, "backup_grid_layout"):
        return
    _clear_backup_grid(window)
    root = _backup_root(window)
    if root is not None:
        try:
            load_index(root)
        except BackupRepositoryError as exc:
            window.backup_status_label.setText(_txt("백업 인덱스를 읽을 수 없습니다.", "Backup index cannot be read."))
            QMessageBox.warning(window, _txt("백업 인덱스 오류", "Backup index error"), str(exc))
            return
    try:
        items = _backup_items(window)
    except BackupRepositoryError as exc:
        window.backup_status_label.setText(_txt("백업 인덱스를 읽을 수 없습니다.", "Backup index cannot be read."))
        QMessageBox.warning(window, _txt("백업 인덱스 오류", "Backup index error"), str(exc))
        return

    factory = getattr(window, "_fh6_backup_original_make_saved_content_card", None)
    if not callable(factory):
        return
    for index, (_entry, record, location) in enumerate(items):
        key = f"backup::{record.kind}::{record.content_sha256 or record.container_name}::{index}"
        card = factory("livery", record, key)
        _configure_backup_card(window, card, record, location)
        card.setProperty("backupRecord", record)
        window._fh6_backup_cards.append(card)

    backup_only = sum(1 for card in window._fh6_backup_cards if card.property("backupLocation") == "backup")
    game_only = sum(1 for card in window._fh6_backup_cards if card.property("backupLocation") == "game")
    both = sum(1 for card in window._fh6_backup_cards if card.property("backupLocation") == "both")
    window.backup_status_label.setText(
        _txt(
            f"백업 {backup_only} · 게임 {game_only} · 게임 + 백업 {both}",
            f"Backup {backup_only} · Game {game_only} · Game + Backup {both}",
        )
    )
    _relayout_backup(window)


def _backup_filter_allows(window: Any, card: Any) -> bool:
    mode = getattr(window, "_fh6_backup_location_filter", "all")
    location = str(card.property("backupLocation") or "")
    return mode == "all" or location == mode


def _group_header(window: Any, key: str, text: str) -> QLabel:
    headers = window._fh6_backup_headers
    header = headers.get(key)
    if header is None:
        header = QLabel()
        header.setObjectName("vehicleGroupHeader")
        header.setMinimumHeight(38)
        header.setStyleSheet(
            "QLabel#vehicleGroupHeader { background:#eee9ff; color:#3e2a95; "
            "border:1px solid #d9d0ff; border-radius:8px; padding:9px 12px; "
            "font-size:11pt; font-weight:700; }"
        )
        headers[key] = header
    header.setText(text)
    return header


def _relayout_backup(window: Any) -> None:
    layout = window.backup_grid_layout
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.hide()
    for header in window._fh6_backup_headers.values():
        header.hide()

    needle = window.backup_search.text().strip().casefold()
    cards = [
        card for card in window._fh6_backup_cards
        if (not needle or needle in str(card.property("searchText") or "")) and _backup_filter_allows(window, card)
    ]
    columns = _backup_columns(window)
    for column in range(GRID_MAX_COLUMNS):
        layout.setColumnStretch(column, 1 if column < columns else 0)

    mode = getattr(window, "_fh6_backup_group_mode", "none")
    if mode == "none":
        for index, card in enumerate(cards):
            layout.addWidget(card, index // columns, index % columns)
            card.show()
    else:
        prop = "creatorGroupKey" if mode == "creator" else "vehicleGroupKey"
        label_prop = "creatorGroupLabel" if mode == "creator" else "vehicleGroupLabel"
        grouped: dict[str, list[Any]] = {}
        labels: dict[str, str] = {}
        for card in cards:
            key = str(card.property(prop) or "unknown")
            grouped.setdefault(key, []).append(card)
            labels.setdefault(key, str(card.property(label_prop) or "—"))
        row = 0
        for key, group_cards in grouped.items():
            label = labels[key]
            title = (
                _txt(f"{label} · 리버리 {len(group_cards)}개", f"{label} · {len(group_cards)} liveries")
            )
            header = _group_header(window, f"{mode}:{key}", title)
            layout.addWidget(header, row, 0, 1, columns)
            header.show()
            row += 1
            for index, card in enumerate(group_cards):
                layout.addWidget(card, row + index // columns, index % columns)
                card.show()
            row += (len(group_cards) + columns - 1) // columns
    layout.activate()
    _sync_backup_widths(window)
    QTimer.singleShot(0, lambda owner=window: _refresh_backup_thumbnails(owner))


def _sync_backup_widths(window: Any) -> None:
    scroll = getattr(window, "backup_grid_scroll", None)
    layout = getattr(window, "backup_grid_layout", None)
    if scroll is None or layout is None:
        return
    viewport = scroll.viewport()
    if viewport is None or viewport.width() <= 0:
        return
    columns = _backup_columns(window)
    margins = layout.contentsMargins()
    gap = max(0, layout.horizontalSpacing())
    available = viewport.width() - margins.left() - margins.right() - gap * (columns - 1) - 4
    width = max(1, available // columns)
    for card in getattr(window, "_fh6_backup_cards", []):
        card.setMinimumWidth(0)
        card.setMaximumWidth(width)
        card.setFixedWidth(width)
    window.backup_grid_host.setMinimumWidth(0)
    window.backup_grid_host.updateGeometry()


def _refresh_backup_thumbnails(window: Any) -> None:
    scroll = getattr(window, "backup_grid_scroll", None)
    if scroll is None:
        return
    viewport = scroll.viewport()
    visible = viewport.rect().adjusted(0, -260, 0, 260)
    loader = getattr(window, "_load_livery_card_thumbnail", None)
    unloader = getattr(window, "_unload_livery_card_thumbnail", None)
    for card in getattr(window, "_fh6_backup_cards", []):
        if not card.isVisible():
            if callable(unloader):
                unloader(card)
            continue
        top_left = card.mapTo(viewport, QPoint(0, 0))
        if QRect(top_left, card.size()).intersects(visible):
            if callable(loader):
                loader(card)
        elif callable(unloader):
            unloader(card)


class _BackupResizeController(QObject):
    def __init__(self, window: Any, viewport: QWidget):
        super().__init__(viewport)
        self.window = window
        viewport.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Resize:
            QTimer.singleShot(0, lambda owner=self.window: _relayout_backup(owner))
        return False


def _set_backup_sort(window: Any, mode: str) -> None:
    window._fh6_backup_sort_mode = mode
    for key, button in window.backup_sort_buttons.items():
        button.setChecked(key == mode)
    _rebuild_backup_cards(window)


def _set_backup_group(window: Any, mode: str, enabled: bool) -> None:
    if not enabled:
        if getattr(window, "_fh6_backup_group_mode", "none") == mode:
            window._fh6_backup_group_mode = "none"
    else:
        window._fh6_backup_group_mode = mode
        other = window.backup_creator_group_button if mode == "vehicle" else window.backup_vehicle_group_button
        other.blockSignals(True)
        other.setChecked(False)
        other.blockSignals(False)
    _relayout_backup(window)


def _set_backup_location_filter(window: Any, mode: str) -> None:
    window._fh6_backup_location_filter = mode
    for key, action in window._fh6_backup_filter_actions.items():
        action.setChecked(key == mode)
    _relayout_backup(window)


def _backup_page(window: Any) -> QWidget:
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addLayout(window._page_header(_txt("백업", "Backup"), ""))

    path_row = QHBoxLayout()
    path_edit = QLineEdit()
    path_edit.setReadOnly(True)
    path_edit.setPlaceholderText(_txt("외부 백업 저장 경로를 지정하세요", "Choose an external backup repository"))
    saved = window.settings.value(_BACKUP_PATH_KEY, "", str).strip()
    if saved and Path(saved).is_dir():
        path_edit.setText(saved)
    choose = QPushButton(_txt("저장 경로 선택", "Choose folder"))
    choose.setObjectName("primary")
    choose.clicked.connect(lambda _checked=False, owner=window: _choose_backup_folder(owner))
    path_row.addWidget(path_edit, 1)
    path_row.addWidget(choose)
    layout.addLayout(path_row)
    window.backup_path_edit = path_edit
    window.backup_choose_button = choose

    search_row = QHBoxLayout()
    search = QLineEdit()
    search.setPlaceholderText(tr("content.search_placeholder"))
    search.textChanged.connect(lambda _text, owner=window: _relayout_backup(owner))
    filter_button = QToolButton()
    filter_button.setText(tr("common.filter"))
    filter_button.setObjectName("secondaryFilterButton")
    filter_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    menu = QMenu(filter_button)
    actions: dict[str, QAction] = {}
    for mode, label in (
        ("all", _txt("전체 위치", "All locations")),
        ("game", _txt("게임만", "Game only")),
        ("backup", _txt("백업만", "Backup only")),
        ("both", _txt("게임 + 백업", "Game + Backup")),
    ):
        action = QAction(label, menu)
        action.setCheckable(True)
        action.setChecked(mode == "all")
        action.triggered.connect(lambda _checked=False, m=mode, owner=window: _set_backup_location_filter(owner, m))
        menu.addAction(action)
        actions[mode] = action
    filter_button.setMenu(menu)
    search_row.addWidget(search, 1)
    search_row.addWidget(filter_button)
    layout.addLayout(search_row)
    window.backup_search = search
    window.backup_filter_button = filter_button
    window._fh6_backup_filter_actions = actions

    action_row = QHBoxLayout()
    action_row.setSpacing(7)
    sort_label = QLabel(tr("content.sort_label"))
    sort_label.setObjectName("muted")
    action_row.addWidget(sort_label)
    sort_buttons: dict[str, QPushButton] = {}
    for mode, label in (
        ("default", tr("content.sort_default")),
        ("brand", tr("content.sort_brand")),
        ("creator", tr("content.sort_creator")),
        ("download", tr("content.sort_download")),
    ):
        button = QPushButton(label)
        button.setObjectName("secondary")
        button.setCheckable(True)
        button.setChecked(mode == "default")
        button.clicked.connect(lambda _checked=False, m=mode, owner=window: _set_backup_sort(owner, m))
        action_row.addWidget(button)
        sort_buttons[mode] = button
    separator = QLabel("││")
    separator.setStyleSheet("color:#b1a8c9;font-weight:700;padding:0 2px;")
    action_row.addWidget(separator)
    vehicle_group = QPushButton(tr("content.group_vehicle"))
    vehicle_group.setObjectName("secondary")
    vehicle_group.setCheckable(True)
    creator_group = QPushButton(tr("content.group_creator"))
    creator_group.setObjectName("secondary")
    creator_group.setCheckable(True)
    vehicle_group.toggled.connect(lambda enabled, owner=window: _set_backup_group(owner, "vehicle", enabled))
    creator_group.toggled.connect(lambda enabled, owner=window: _set_backup_group(owner, "creator", enabled))
    action_row.addWidget(vehicle_group)
    action_row.addWidget(creator_group)
    action_row.addStretch(1)
    layout.addLayout(action_row)
    window.backup_sort_buttons = sort_buttons
    window.backup_vehicle_group_button = vehicle_group
    window.backup_creator_group_button = creator_group

    status = QLabel("")
    status.setObjectName("muted")
    layout.addWidget(status)
    window.backup_status_label = status

    scroll = QScrollArea()
    scroll.setObjectName("backupGridScroll")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
    scroll.setStyleSheet("QScrollArea#backupGridScroll { background:#f7f8fb; border:0; }")
    viewport = scroll.viewport()
    viewport.setStyleSheet("background:#f7f8fb;")
    host = QWidget()
    host.setObjectName("backupGridHost")
    host.setMinimumWidth(0)
    host.setStyleSheet("QWidget#backupGridHost { background:#f7f8fb; }")
    grid = QGridLayout(host)
    grid.setContentsMargins(2, 2, 2, 2)
    grid.setHorizontalSpacing(14)
    grid.setVerticalSpacing(14)
    grid.setAlignment(Qt.AlignmentFlag.AlignTop)
    scroll.setWidget(host)
    scroll.verticalScrollBar().valueChanged.connect(lambda _value, owner=window: _refresh_backup_thumbnails(owner))
    scroll.verticalScrollBar().rangeChanged.connect(lambda *_args, owner=window: _sync_backup_widths(owner))
    layout.addWidget(scroll, 1)
    window.backup_grid_scroll = scroll
    window.backup_grid_host = host
    window.backup_grid_layout = grid
    window._fh6_backup_resize_controller = _BackupResizeController(window, viewport)
    return page


def _open_backup_page(window: Any) -> None:
    window.pages.setCurrentWidget(window.backup_page)
    _relayout_backup(window)
    for delay in (0, 40, 120):
        QTimer.singleShot(delay, lambda owner=window: _refresh_backup_thumbnails(owner))


def _install_backup_navigation(window: Any) -> None:
    page = _backup_page(window)
    window.backup_page = page
    window.pages.addWidget(page)
    sidebar = window.findChild(QFrame, "sidebar")
    if sidebar is None or sidebar.layout() is None:
        return
    button = QPushButton(_txt("백업", "Backup"), sidebar)
    button.setObjectName("nav")
    button.setCheckable(True)
    button.clicked.connect(lambda _checked=False, owner=window: _open_backup_page(owner))
    window.nav_group.addButton(button)
    window.nav_buttons.append(button)
    layout = sidebar.layout()
    memory = getattr(window, "memory_nav_button", None)
    if isinstance(memory, QPushButton):
        index = layout.indexOf(memory)
        layout.insertWidget(index if index >= 0 else 1 + len(window.nav_buttons), button)
    else:
        layout.insertWidget(1 + len(window.nav_buttons) - 1, button)
    window.backup_nav_button = button
    _rebuild_backup_cards(window)


def apply_v1_3_4_backup_export_patch(MainWindow: Any) -> None:
    if getattr(MainWindow, "_fh6_v134_backup_export_patched", False):
        return

    original_init = MainWindow.__init__
    original_make_card = MainWindow._make_saved_content_card
    original_populate_all = MainWindow._populate_all

    def patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        self._fh6_export_running = False
        self._fh6_export_thread = None
        self._fh6_export_worker = None
        self._fh6_backup_cards = []
        self._fh6_backup_headers = {}
        self._fh6_backup_sort_mode = "default"
        self._fh6_backup_group_mode = "none"
        self._fh6_backup_location_filter = "all"
        original_init(self, *args, **kwargs)
        _install_bulk_export_button(self)
        _install_backup_navigation(self)
        _refresh_main_export_states(self)

    def make_card(self: Any, content_type: str, record: Any, key: str):
        card = original_make_card(self, content_type, record, key)
        if content_type == "livery" and isinstance(record, LiveryRecord) and not bool(card.property("fh6ArchiveCard")):
            _set_export_state(self, card, record)
        return card

    def populate_all(self: Any) -> None:
        original_populate_all(self)
        _refresh_main_export_states(self)
        _rebuild_backup_cards(self)

    MainWindow._fh6_backup_original_make_saved_content_card = original_make_card
    MainWindow.__init__ = patched_init
    MainWindow._make_saved_content_card = make_card
    MainWindow._populate_all = populate_all
    MainWindow._fh6_v134_backup_export_patched = True
