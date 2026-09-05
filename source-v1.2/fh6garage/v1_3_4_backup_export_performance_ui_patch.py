from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Iterable

from PySide6.QtCore import QSize, QTimer
from PySide6.QtWidgets import QLineEdit, QPushButton, QStyle, QToolButton

from . import v1_3_4_backup_export_patch as _backup_ui
from .backup_export import (
    BackupRepositoryError,
    ExportSummary,
    INDEX_NAME,
    STAGING_NAME,
    _entry_for,
    _entry_identity,
    _external_preview,
    _unique_destination,
    backup_records,
    content_sha256,
    folder_fingerprint,
    load_index,
    safe_component,
    save_index,
)
from .card_icons import icon as card_icon
from .models import LiveryRecord
from .v1_3_2_filter_alias_quality_patch import _FILTER_BUTTON_STYLE


_ACTIVE_COLOR = _backup_ui._ACTIVE_COLOR
_INACTIVE_COLOR = _backup_ui._INACTIVE_COLOR
_CARD_BUILD_CHUNK = 12
_EXPORT_STATE_CHUNK = 64


def _txt(ko: str, en: str) -> str:
    return _backup_ui._txt(ko, en)


def _valid_index_presence(root: Path) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    payload = load_index(root)
    containers: set[tuple[str, str]] = set()
    identities: set[tuple[str, str]] = set()
    for entry in payload.get("entries", []):
        if not isinstance(entry, dict):
            continue
        relative = str(entry.get("relative_path") or "")
        if not relative or not (root / relative).is_dir():
            continue
        kind = str(entry.get("kind") or "").strip().casefold()
        container = str(entry.get("original_container_name") or "").strip().casefold()
        digest = str(entry.get("content_sha256") or "").strip().casefold()
        if kind and container:
            containers.add((kind, container))
        if kind and digest:
            identities.add((kind, digest))
    return containers, identities


def _presence_snapshot(
    window: Any,
    *,
    force: bool = False,
) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    root = _backup_ui._backup_root(window)
    if root is None:
        window._fh6_backup_presence_cache = ("", set(), set())
        return set(), set()

    root_key = str(root.resolve())
    cached = getattr(window, "_fh6_backup_presence_cache", None)
    if (
        not force
        and isinstance(cached, tuple)
        and len(cached) == 3
        and cached[0] == root_key
    ):
        return cached[1], cached[2]

    try:
        containers, identities = _valid_index_presence(root)
    except BackupRepositoryError:
        containers, identities = set(), set()
    window._fh6_backup_presence_cache = (root_key, containers, identities)
    return containers, identities


def _record_backed_up(
    record: LiveryRecord,
    containers: set[tuple[str, str]],
    identities: set[tuple[str, str]],
) -> bool:
    kind = str(record.kind or "").strip().casefold()
    container = str(record.container_name or "").strip().casefold()
    if kind and container and (kind, container) in containers:
        return True
    digest = str(record.content_sha256 or "").strip().casefold()
    return bool(kind and digest and (kind, digest) in identities)


def _paint_export_state(window: Any, card: Any, record: LiveryRecord, exported: bool) -> None:
    button = getattr(card, "_fh6_export_placeholder_button", None)
    if not isinstance(button, QToolButton):
        return
    button.setEnabled(True)
    button.setIcon(card_icon("export", _ACTIVE_COLOR if exported else _INACTIVE_COLOR, 20))
    button.setIconSize(QSize(20, 20))
    button.setStyleSheet(_backup_ui._action_style(exported))
    button.setProperty("fh6Exported", exported)
    button.setToolTip(
        _txt("이미 백업됨 · 다시 확인/내보내기", "Already backed up · verify/export again")
        if exported
        else _txt("이 리버리 내보내기", "Export this livery")
    )
    if not bool(button.property("fh6ExportActionInstalled")):
        button.setProperty("fh6ExportActionInstalled", True)
        button.clicked.connect(
            lambda _checked=False, owner=window, item=record: _backup_ui._request_export(owner, [item])
        )


def _set_export_state(window: Any, card: Any, record: LiveryRecord) -> None:
    # Never hash SoulBound payloads merely to paint a button.  Exact original
    # container identity is enough for an existing backup, while any missing
    # digest is calculated only when the user actually exports the item.
    containers, identities = _presence_snapshot(window)
    _paint_export_state(
        window,
        card,
        record,
        _record_backed_up(record, containers, identities),
    )


def _refresh_main_export_states(window: Any) -> None:
    resolver = getattr(window, "_record_for_content_key", None)
    if not callable(resolver):
        return
    containers, identities = _presence_snapshot(window, force=True)
    cards = list(getattr(window, "_livery_grid_cards", []) or [])
    generation = int(getattr(window, "_fh6_export_state_generation", 0)) + 1
    window._fh6_export_state_generation = generation

    def apply_chunk(start: int = 0) -> None:
        if generation != getattr(window, "_fh6_export_state_generation", 0):
            return
        end = min(len(cards), start + _EXPORT_STATE_CHUNK)
        for card in cards[start:end]:
            key = str(card.property("annotationKey") or "")
            record = resolver("livery", key) if key else None
            if isinstance(record, LiveryRecord):
                _paint_export_state(
                    window,
                    card,
                    record,
                    _record_backed_up(record, containers, identities),
                )
        if end < len(cards):
            QTimer.singleShot(0, lambda next_start=end: apply_chunk(next_start))

    apply_chunk(0)


def _fast_export_records(root: Path, records: Iterable[LiveryRecord]) -> ExportSummary:
    """Export with one verified copy pass and no redundant post-rename reread.

    Staging and final directories live under the same backup root.  After the
    staging copy is fingerprint-verified, os.replace() only renames that verified
    directory on the same filesystem; re-hashing every final file a third time
    adds latency without adding copy-integrity information.
    """
    root = root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    payload = load_index(root)
    entries = [entry for entry in payload.get("entries", []) if isinstance(entry, dict)]
    payload["entries"] = entries
    existing = {
        _entry_identity(entry)
        for entry in entries
        if _entry_identity(entry)[0] and _entry_identity(entry)[1]
    }
    summary = ExportSummary()
    staging_root = root / STAGING_NAME
    staging_root.mkdir(parents=True, exist_ok=True)

    for record in records:
        label = record.container_name or "(unnamed)"
        source = Path(record.container_path)
        try:
            if not source.is_dir():
                raise BackupRepositoryError("source container is missing")
            digest = content_sha256(record)
            if not digest:
                raise BackupRepositoryError("C_livery SHA-256 is unavailable")
            identity = (str(record.kind or "").strip().casefold(), digest.casefold())
            if identity in existing:
                summary.skipped.append(
                    {
                        "container_name": record.container_name,
                        "kind": record.kind,
                        "content_sha256": digest,
                    }
                )
                continue

            source_fingerprint = folder_fingerprint(source)
            if not source_fingerprint:
                raise BackupRepositoryError("source folder fingerprint failed")

            category = safe_component(record.kind or "Livery", "Livery")
            creator = safe_component(record.header.creator or "", "(제작자 없음)")
            parent = root / category / creator
            parent.mkdir(parents=True, exist_ok=True)
            final_path = _unique_destination(parent, record.container_name, digest)

            stage = staging_root / uuid.uuid4().hex
            try:
                shutil.copytree(source, stage)
                staged_fingerprint = folder_fingerprint(stage)
                if staged_fingerprint != source_fingerprint:
                    raise BackupRepositoryError("staging fingerprint mismatch")
                os.replace(stage, final_path)
            finally:
                if stage.exists():
                    shutil.rmtree(stage, ignore_errors=True)

            if not final_path.is_dir():
                raise BackupRepositoryError("final publish failed")

            preview_relative = _external_preview(root, final_path, record, digest)
            entry = _entry_for(
                root,
                final_path,
                record,
                digest,
                source_fingerprint,
                preview_relative,
            )
            entries.append(entry)
            try:
                save_index(root, payload)
            except Exception:
                entries.pop()
                shutil.rmtree(final_path, ignore_errors=True)
                if preview_relative:
                    try:
                        (root / preview_relative).unlink(missing_ok=True)
                    except OSError:
                        pass
                raise
            existing.add(identity)
            summary.exported.append(entry)
        except Exception as exc:  # noqa: BLE001 - isolate one failed batch item
            summary.failed.append((label, f"{type(exc).__name__}: {exc}"))

    try:
        if staging_root.is_dir() and not any(staging_root.iterdir()):
            staging_root.rmdir()
    except OSError:
        pass
    return summary


def _game_index(window: Any) -> tuple[
    list[LiveryRecord],
    dict[tuple[str, str], list[LiveryRecord]],
    dict[tuple[str, str], list[LiveryRecord]],
]:
    game = _backup_ui._game_records(window)
    by_container: dict[tuple[str, str], list[LiveryRecord]] = {}
    by_digest: dict[tuple[str, str], list[LiveryRecord]] = {}
    for record in game:
        kind = str(record.kind or "").strip().casefold()
        container = str(record.container_name or "").strip().casefold()
        digest = str(record.content_sha256 or "").strip().casefold()
        if kind and container:
            by_container.setdefault((kind, container), []).append(record)
        if kind and digest:
            by_digest.setdefault((kind, digest), []).append(record)
    return game, by_container, by_digest


def _backup_items(window: Any) -> list[tuple[dict[str, Any] | None, LiveryRecord, str]]:
    root = _backup_ui._backup_root(window)
    game, by_container, by_digest = _game_index(window)
    items: list[tuple[dict[str, Any] | None, LiveryRecord, str]] = []
    represented: set[int] = set()

    if root is not None:
        for entry, record in backup_records(root):
            kind = str(entry.get("kind") or "").strip().casefold()
            container = str(entry.get("original_container_name") or "").strip().casefold()
            digest = str(entry.get("content_sha256") or "").strip().casefold()
            matched: dict[int, LiveryRecord] = {}
            for candidate in by_container.get((kind, container), []):
                matched[id(candidate)] = candidate
            if digest:
                for candidate in by_digest.get((kind, digest), []):
                    matched[id(candidate)] = candidate
            represented.update(matched)
            items.append((entry, record, "both" if matched else "backup"))

    for record in game:
        if id(record) not in represented:
            items.append((None, record, "game"))
    items.sort(key=lambda item: _backup_ui._backup_sort_key(window, item))
    return items


def _configure_backup_action_button(
    window: Any,
    card: Any,
    record: LiveryRecord,
    location: str,
) -> None:
    button = getattr(card, "_fh6_export_placeholder_button", None)
    if not isinstance(button, QToolButton):
        return

    if location == "game":
        button.setObjectName("fh6BackupButton")
        button.setEnabled(True)
        button.setIcon(card_icon("export", _INACTIVE_COLOR, 20))
        button.setStyleSheet(_backup_ui._action_style(False))
        button.setToolTip(_txt("백업하기", "Back up"))
        button.setAccessibleName(_txt("백업하기", "Back up"))
        if not bool(button.property("fh6BackupActionInstalled")):
            button.setProperty("fh6BackupActionInstalled", True)
            button.clicked.connect(
                lambda _checked=False, owner=window, item=record: _backup_ui._request_export(owner, [item])
            )
        return

    both = location == "both"
    button.setObjectName("fh6ImportButton")
    button.setEnabled(True)
    button.setIcon(card_icon("import", _ACTIVE_COLOR if both else _INACTIVE_COLOR, 20))
    button.setStyleSheet(_backup_ui._action_style(both))
    button.setProperty("fh6Imported", both)
    button.setToolTip(
        _txt("이미 게임 + 백업에 존재", "Already present in game + backup")
        if both
        else _txt("들여오기 · 현재 실제 복원은 비활성", "Import · actual restore is currently disabled")
    )
    button.setAccessibleName(_txt("들여오기", "Import"))
    if not bool(button.property("fh6ImportPreviewInstalled")):
        button.setProperty("fh6ImportPreviewInstalled", True)
        button.clicked.connect(
            lambda _checked=False, owner=window: _backup_ui._confirm_keep_source(owner, 1, operation="import")
        )


def _configure_backup_card(window: Any, card: Any, record: LiveryRecord, location: str) -> None:
    source = card.findChild(_backup_ui.QLabel, "fh6AcquisitionPlaceholder")
    if source is not None:
        source.setText(_backup_ui._location_text(location))
    move = getattr(card, "_fh6_game_move_button", None)
    lock = getattr(card, "_fh6_lock_placeholder_button", None)
    if isinstance(move, QToolButton):
        move.hide()
        move.setEnabled(False)
    if isinstance(lock, QToolButton):
        lock.hide()
        lock.setEnabled(False)
    _configure_backup_action_button(window, card, record, location)
    if location == "game":
        _backup_ui._apply_game_only_grayscale(card)
    card.setProperty("backupLocation", location)
    card.setProperty(
        "searchText",
        " ".join(
            (
                record.header.name or "",
                record.header.creator or "",
                window._car_label(record.car_id),
                str(record.car_id or ""),
                record.header.description or "",
                record.kind or "",
                _backup_ui._location_text(location),
            )
        ).casefold(),
    )
    card.setProperty("vehicleGroupKey", f"id:{record.car_id}" if record.car_id is not None else "unknown")
    card.setProperty("vehicleGroupLabel", window._car_label(record.car_id))
    creator = (record.header.creator or "").strip() or _backup_ui.tr("creator.none")
    card.setProperty("creatorGroupKey", f"creator:{creator.casefold()}")
    card.setProperty("creatorGroupLabel", creator)


def _status_counts(items: list[tuple[dict[str, Any] | None, LiveryRecord, str]]) -> tuple[int, int, int]:
    backup_only = sum(1 for _entry, _record, location in items if location == "backup")
    game_only = sum(1 for _entry, _record, location in items if location == "game")
    both = sum(1 for _entry, _record, location in items if location == "both")
    return backup_only, game_only, both


def _final_status(window: Any, counts: tuple[int, int, int]) -> str:
    backup_only, game_only, both = counts
    return _txt(
        f"백업 {backup_only} · 게임 {game_only} · 게임 + 백업 {both}",
        f"Backup {backup_only} · Game {game_only} · Game + Backup {both}",
    )


def _rebuild_backup_cards(window: Any) -> None:
    if not hasattr(window, "backup_grid_layout"):
        return

    generation = int(getattr(window, "_fh6_backup_build_generation", 0)) + 1
    window._fh6_backup_build_generation = generation
    _backup_ui._clear_backup_grid(window)

    try:
        items = _backup_items(window)
    except BackupRepositoryError as exc:
        window.backup_status_label.setText(
            _txt("백업 인덱스를 읽을 수 없습니다.", "Backup index cannot be read.")
        )
        _backup_ui.QMessageBox.warning(
            window,
            _txt("백업 인덱스 오류", "Backup index error"),
            str(exc),
        )
        return

    counts = _status_counts(items)
    total = len(items)
    factory = getattr(window, "_fh6_backup_original_make_saved_content_card", None)
    if not callable(factory):
        return

    if total == 0:
        window.backup_status_label.setText(_final_status(window, counts))
        _backup_ui._relayout_backup(window)
        return

    window.backup_status_label.setText(
        _txt(
            f"백업 목록 준비 중 0/{total} · {_final_status(window, counts)}",
            f"Preparing backup list 0/{total} · {_final_status(window, counts)}",
        )
    )

    def build_chunk(start: int = 0) -> None:
        if generation != getattr(window, "_fh6_backup_build_generation", 0):
            return
        end = min(total, start + _CARD_BUILD_CHUNK)
        for index in range(start, end):
            _entry, record, location = items[index]
            key = f"backup::{record.kind}::{record.content_sha256 or record.container_name}::{index}"
            card = factory("livery", record, key)
            _configure_backup_card(window, card, record, location)
            card.setProperty("backupRecord", record)
            window._fh6_backup_cards.append(card)

        if end < total:
            window.backup_status_label.setText(
                _txt(
                    f"백업 목록 준비 중 {end}/{total} · {_final_status(window, counts)}",
                    f"Preparing backup list {end}/{total} · {_final_status(window, counts)}",
                )
            )
            QTimer.singleShot(0, lambda next_start=end: build_chunk(next_start))
            return

        window.backup_status_label.setText(_final_status(window, counts))
        _backup_ui._relayout_backup(window)
        QTimer.singleShot(0, lambda owner=window: _backup_ui._sync_backup_widths(owner))
        QTimer.singleShot(0, lambda owner=window: _backup_ui._refresh_backup_thumbnails(owner))

    QTimer.singleShot(0, build_chunk)


def _set_backup_location_filter(window: Any, mode: str) -> None:
    window._fh6_backup_location_filter = mode
    for key, action in window._fh6_backup_filter_actions.items():
        action.setChecked(key == mode)
    button = getattr(window, "backup_filter_button", None)
    if isinstance(button, QToolButton):
        button.setProperty("fh6FilterActive", mode != "all")
        button.setStyleSheet(_FILTER_BUTTON_STYLE)
        style = button.style()
        if isinstance(style, QStyle):
            style.unpolish(button)
            style.polish(button)
        button.update()
    _backup_ui._relayout_backup(window)


def _sync_backup_toolbar(window: Any) -> None:
    search = getattr(window, "backup_search", None)
    livery_search = getattr(window, "livery_search", None)
    if isinstance(search, QLineEdit) and isinstance(livery_search, QLineEdit):
        search.setFont(livery_search.font())
        search.setStyleSheet(livery_search.styleSheet())
        search.setSizePolicy(livery_search.sizePolicy())
        search.setMinimumHeight(livery_search.minimumSizeHint().height())
        # Match the livery tab's debounced search behavior as well as its look.
        try:
            search.textChanged.disconnect()
        except (RuntimeError, TypeError):
            pass
        window._connect_debounced_search(
            search,
            lambda _text, owner=window: _backup_ui._relayout_backup(owner),
        )

    backup_filter = getattr(window, "backup_filter_button", None)
    livery_filter = getattr(window, "livery_check_filter", None)
    if isinstance(backup_filter, QToolButton) and isinstance(livery_filter, QToolButton):
        backup_filter.setFont(livery_filter.font())
        backup_filter.setToolButtonStyle(livery_filter.toolButtonStyle())
        backup_filter.setSizePolicy(livery_filter.sizePolicy())
        backup_filter.setMinimumHeight(livery_filter.minimumSizeHint().height())
        backup_filter.setProperty(
            "fh6FilterActive",
            getattr(window, "_fh6_backup_location_filter", "all") != "all",
        )
        backup_filter.setStyleSheet(_FILTER_BUTTON_STYLE)

    for mode, button in getattr(window, "backup_sort_buttons", {}).items():
        source = getattr(window, "livery_sort_buttons", {}).get(mode)
        if isinstance(button, QPushButton) and isinstance(source, QPushButton):
            button.setFont(source.font())
            button.setStyleSheet(source.styleSheet())
            button.setSizePolicy(source.sizePolicy())
            button.setMinimumHeight(source.minimumSizeHint().height())

    for target_name, source_name in (
        ("backup_vehicle_group_button", "livery_group_button"),
        ("backup_creator_group_button", "livery_creator_group_button"),
    ):
        target = getattr(window, target_name, None)
        source = getattr(window, source_name, None)
        if isinstance(target, QPushButton) and isinstance(source, QPushButton):
            target.setFont(source.font())
            target.setStyleSheet(source.styleSheet())
            target.setSizePolicy(source.sizePolicy())
            target.setMinimumHeight(source.minimumSizeHint().height())


def apply_v1_3_4_backup_export_performance_ui_patch(MainWindow: Any) -> None:
    if getattr(MainWindow, "_fh6_v134_backup_export_performance_ui_patched", False):
        return

    # Replace runtime lookups used by the already-installed backup layer.  No
    # second backup page or competing card owner is created.
    _backup_ui.export_records = _fast_export_records
    _backup_ui._set_export_state = _set_export_state
    _backup_ui._refresh_main_export_states = _refresh_main_export_states
    _backup_ui._backup_items = _backup_items
    _backup_ui._configure_backup_card = _configure_backup_card
    _backup_ui._rebuild_backup_cards = _rebuild_backup_cards
    _backup_ui._set_backup_location_filter = _set_backup_location_filter

    original_init = MainWindow.__init__

    def patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        self._fh6_backup_presence_cache = ("", set(), set())
        self._fh6_backup_build_generation = 0
        self._fh6_export_state_generation = 0
        original_init(self, *args, **kwargs)
        _sync_backup_toolbar(self)

    MainWindow.__init__ = patched_init
    MainWindow._fh6_v134_backup_export_performance_ui_patched = True
