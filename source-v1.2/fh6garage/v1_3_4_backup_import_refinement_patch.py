from __future__ import annotations

import os
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from PySide6.QtCore import QObject, QSize, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QPushButton, QStyle, QToolButton

from . import v1_3_4_backup_export_patch as _backup_ui
from . import v1_3_4_backup_export_performance_ui_patch as _perf
from .backup_export import (
    BackupRepositoryError,
    ExportSummary,
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


_IMPORT_STAGING = ".fh6_assistant_import_staging"
_BACKUP_TRASH = ".fh6_assistant_trash"
_SUPPORTED_KINDS = {"Livery", "SoulBoundLivery"}


@dataclass(slots=True)
class ImportSummary:
    published: list[str] = field(default_factory=list)
    already_present: list[str] = field(default_factory=list)
    source_deleted: bool = False


def _txt(ko: str, en: str) -> str:
    return _backup_ui._txt(ko, en)


def _under(root: Path, relative: str) -> Path:
    root = root.expanduser().resolve()
    candidate = (root / relative).resolve()
    if candidate != root and root not in candidate.parents:
        raise BackupRepositoryError("path escapes the expected root")
    return candidate


def _container_name(entry: dict[str, Any]) -> str:
    name = str(entry.get("original_container_name") or "").strip()
    if not name or Path(name).name != name or "/" in name or "\\" in name:
        raise BackupRepositoryError("invalid backup container name")
    return name


def _valid_backup_entries(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
    payload = load_index(root)
    entries: list[dict[str, Any]] = []
    changed = False
    for raw in payload.get("entries", []):
        if not isinstance(raw, dict):
            changed = True
            continue
        relative = str(raw.get("relative_path") or "").strip()
        if not relative:
            changed = True
            continue
        try:
            path = _under(root, relative)
        except BackupRepositoryError:
            changed = True
            continue
        if not path.is_dir():
            # A stale index row must never block a later re-backup.
            changed = True
            continue
        entries.append(raw)
    payload["entries"] = entries
    return payload, entries, changed


def _safe_export_records(root: Path, records: Iterable[LiveryRecord]) -> ExportSummary:
    """Verified batch export with stale-index pruning and one atomic index commit."""
    root = root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    payload, entries, index_changed = _valid_backup_entries(root)
    existing = {
        _entry_identity(entry)
        for entry in entries
        if _entry_identity(entry)[0] and _entry_identity(entry)[1]
    }
    summary = ExportSummary()
    staging_root = root / STAGING_NAME
    staging_root.mkdir(parents=True, exist_ok=True)
    published: list[tuple[Path, str]] = []

    for record in records:
        label = record.container_name or "(unnamed)"
        source = Path(record.container_path)
        try:
            if record.kind not in _SUPPORTED_KINDS:
                raise BackupRepositoryError("unsupported content kind")
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
            existing.add(identity)
            published.append((final_path, preview_relative))
            summary.exported.append(entry)
        except Exception as exc:  # noqa: BLE001 - isolate one failed batch item
            summary.failed.append((label, f"{type(exc).__name__}: {exc}"))

    # Commit the growing JSON index once for the whole batch. If that commit
    # fails, roll back every newly published backup so index and disk agree.
    if published or index_changed:
        try:
            save_index(root, payload)
        except Exception as exc:
            for final_path, preview_relative in reversed(published):
                shutil.rmtree(final_path, ignore_errors=True)
                if preview_relative:
                    try:
                        _under(root, preview_relative).unlink(missing_ok=True)
                    except (OSError, BackupRepositoryError):
                        pass
            failed_entries = list(summary.exported)
            summary.exported.clear()
            for entry in failed_entries:
                summary.failed.append(
                    (
                        str(entry.get("original_container_name") or "(unnamed)"),
                        f"{type(exc).__name__}: {exc}",
                    )
                )

    try:
        if staging_root.is_dir() and not any(staging_root.iterdir()):
            staging_root.rmdir()
    except OSError:
        pass
    return summary


def _numeric_containers_roots(save_root: Path) -> list[Path]:
    try:
        versions = [
            child
            for child in save_root.iterdir()
            if child.is_dir()
            and child.name.isdigit()
            and (child / "ContainersRoot").is_dir()
        ]
    except OSError as exc:
        raise BackupRepositoryError(f"save version scan failed: {exc}") from exc
    versions.sort(key=lambda path: int(path.name), reverse=True)
    return [version / "ContainersRoot" for version in versions]


def resolve_import_targets(save_root: Path, active_version: str) -> tuple[Path, Path]:
    """Return current + active/latest numbered ContainersRoot directories."""
    save_root = save_root.expanduser().resolve()
    current = save_root / "current" / "ContainersRoot"
    if not current.is_dir():
        raise BackupRepositoryError("current/ContainersRoot is missing")

    numeric: Path | None = None
    active = str(active_version or "").strip()
    if active.isdigit():
        candidate = save_root / active / "ContainersRoot"
        if candidate.is_dir():
            numeric = candidate
    if numeric is None:
        versions = _numeric_containers_roots(save_root)
        if versions:
            numeric = versions[0]
    if numeric is None:
        raise BackupRepositoryError("numbered ContainersRoot is missing")
    return current, numeric


def _verified_backup_source(root: Path, entry: dict[str, Any]) -> tuple[Path, str, str]:
    relative = str(entry.get("relative_path") or "").strip()
    if not relative:
        raise BackupRepositoryError("backup relative path is missing")
    source = _under(root, relative)
    if not source.is_dir():
        raise BackupRepositoryError("backup source directory is missing")
    expected = str(entry.get("folder_fingerprint") or "").strip().casefold()
    if not expected:
        raise BackupRepositoryError("backup fingerprint is missing")
    actual = folder_fingerprint(source).casefold()
    if not actual or actual != expected:
        raise BackupRepositoryError("backup source integrity check failed")
    return source, expected, _container_name(entry)


def _cleanup_empty_staging(root: Path) -> None:
    try:
        if root.is_dir() and not any(root.iterdir()):
            root.rmdir()
    except OSError:
        pass


def _delete_backup_source(root: Path, entry: dict[str, Any], source: Path) -> None:
    """Remove one backup only after moving it aside and committing the index."""
    payload = load_index(root)
    relative = str(entry.get("relative_path") or "").strip()
    original_entries = [item for item in payload.get("entries", []) if isinstance(item, dict)]
    remaining = [
        item
        for item in original_entries
        if str(item.get("relative_path") or "").strip() != relative
    ]
    if len(remaining) == len(original_entries):
        raise BackupRepositoryError("backup index entry is missing")

    trash_root = root / _BACKUP_TRASH
    trash_root.mkdir(parents=True, exist_ok=True)
    parked = trash_root / uuid.uuid4().hex
    os.replace(source, parked)
    payload["entries"] = remaining
    try:
        save_index(root, payload)
    except Exception:
        if parked.exists() and not source.exists():
            os.replace(parked, source)
        raise

    shutil.rmtree(parked, ignore_errors=True)
    preview_relative = str(entry.get("preview_relative") or "").strip()
    if preview_relative:
        try:
            _under(root, preview_relative).unlink(missing_ok=True)
        except (OSError, BackupRepositoryError):
            pass
    _cleanup_empty_staging(trash_root)


def import_backup_entry(
    backup_root: Path,
    entry: dict[str, Any],
    save_root: Path,
    active_version: str,
    *,
    delete_source: bool = False,
) -> ImportSummary:
    """Restore one verified backup to both current and numbered save trees."""
    backup_root = backup_root.expanduser().resolve()
    source, expected_fingerprint, container_name = _verified_backup_source(backup_root, entry)
    kind = str(entry.get("kind") or "").strip()
    if kind not in _SUPPORTED_KINDS:
        raise BackupRepositoryError("unsupported backup content kind")

    current, numbered = resolve_import_targets(save_root, active_version)
    logical_targets = [current, numbered]
    targets: list[Path] = []
    seen_roots: set[str] = set()
    for root in logical_targets:
        key = os.path.normcase(str(root.resolve()))
        if key not in seen_roots:
            seen_roots.add(key)
            targets.append(root)

    summary = ImportSummary()
    missing: list[tuple[Path, Path]] = []
    for target_root in targets:
        destination = target_root / container_name
        if destination.exists():
            if not destination.is_dir():
                raise BackupRepositoryError(f"destination conflict: {destination}")
            existing_fingerprint = folder_fingerprint(destination).casefold()
            if not existing_fingerprint or existing_fingerprint != expected_fingerprint:
                raise BackupRepositoryError(f"destination content conflict: {destination}")
            summary.already_present.append(str(destination))
        else:
            missing.append((target_root, destination))

    staged: list[tuple[Path, Path, Path]] = []
    try:
        for target_root, destination in missing:
            staging_root = target_root / _IMPORT_STAGING
            staging_root.mkdir(parents=True, exist_ok=True)
            stage = staging_root / uuid.uuid4().hex
            shutil.copytree(source, stage)
            if folder_fingerprint(stage).casefold() != expected_fingerprint:
                raise BackupRepositoryError(f"import staging fingerprint mismatch: {target_root}")
            staged.append((stage, destination, staging_root))

        published_now: list[Path] = []
        try:
            for stage, destination, _staging_root in staged:
                if destination.exists():
                    raise BackupRepositoryError(f"destination appeared during import: {destination}")
                os.replace(stage, destination)
                published_now.append(destination)
                summary.published.append(str(destination))
        except Exception:
            for destination in reversed(published_now):
                shutil.rmtree(destination, ignore_errors=True)
            raise
    finally:
        for stage, _destination, staging_root in staged:
            if stage.exists():
                shutil.rmtree(stage, ignore_errors=True)
            _cleanup_empty_staging(staging_root)

    if delete_source:
        _delete_backup_source(backup_root, entry, source)
        summary.source_deleted = True
    return summary


def _entry_is_in_game(
    entry: dict[str, Any],
    by_container: dict[tuple[str, str], list[LiveryRecord]],
    by_digest: dict[tuple[str, str], list[LiveryRecord]],
) -> bool:
    kind = str(entry.get("kind") or "").strip().casefold()
    container = str(entry.get("original_container_name") or "").strip().casefold()
    digest = str(entry.get("content_sha256") or "").strip().casefold()
    if digest and by_digest.get((kind, digest)):
        return True

    candidates = by_container.get((kind, container), []) if kind and container else []
    if not candidates:
        return False
    known_digests = {
        str(candidate.content_sha256 or "").strip().casefold()
        for candidate in candidates
        if str(candidate.content_sha256 or "").strip()
    }
    if digest and known_digests:
        return digest in known_digests
    # SoulBound deliberately has no startup hash; exact container identity is
    # the low-I/O fallback until the user actually imports/exports that item.
    return True


def _backup_items(window: Any) -> list[tuple[dict[str, Any], LiveryRecord, str]]:
    """Backup page contains only records that physically exist in the repository."""
    root = _backup_ui._backup_root(window)
    if root is None:
        return []
    _game, by_container, by_digest = _perf._game_index(window)
    items: list[tuple[dict[str, Any], LiveryRecord, str]] = []
    for entry, record in backup_records(root):
        location = "both" if _entry_is_in_game(entry, by_container, by_digest) else "backup"
        items.append((entry, record, location))
    items.sort(key=lambda item: _backup_ui._backup_sort_key(window, item))
    return items


def _status_counts(items: list[tuple[dict[str, Any], LiveryRecord, str]]) -> tuple[int, int]:
    backup_only = sum(1 for _entry, _record, location in items if location == "backup")
    both = sum(1 for _entry, _record, location in items if location == "both")
    return backup_only, both


def _final_status(counts: tuple[int, int]) -> str:
    backup_only, both = counts
    return _txt(
        f"백업만 {backup_only} · 게임 + 백업 {both} · 전체 백업 {backup_only + both}",
        f"Backup only {backup_only} · Game + Backup {both} · Total backup {backup_only + both}",
    )


def _import_button(window: Any, card: Any, record: LiveryRecord, entry: dict[str, Any], location: str) -> None:
    button = getattr(card, "_fh6_export_placeholder_button", None)
    if not isinstance(button, QToolButton):
        return
    both = location == "both"
    try:
        button.clicked.disconnect()
    except (RuntimeError, TypeError):
        pass
    button.setObjectName("fh6ImportButton")
    button.setEnabled(True)
    button.setIcon(card_icon("import", _backup_ui._ACTIVE_COLOR if both else _backup_ui._INACTIVE_COLOR, 20))
    button.setIconSize(QSize(20, 20))
    button.setStyleSheet(_backup_ui._action_style(both))
    button.setProperty("fh6Imported", both)
    button.setToolTip(
        _txt("이미 게임 + 백업에 존재 · 다시 검증/들여오기", "Already in game + backup · verify/import again")
        if both
        else _txt("게임으로 들여오기", "Import into game")
    )
    button.setAccessibleName(_txt("들여오기", "Import"))
    button.clicked.connect(
        lambda _checked=False, owner=window, item=record, index_entry=dict(entry):
        _request_import(owner, item, index_entry)
    )


def _configure_backup_card(
    window: Any,
    card: Any,
    record: LiveryRecord,
    entry: dict[str, Any],
    location: str,
) -> None:
    _perf._configure_backup_card(window, card, record, location)
    source = card.findChild(_backup_ui.QLabel, "fh6AcquisitionPlaceholder")
    if source is not None:
        source.setText(_backup_ui._location_text(location))
    _import_button(window, card, record, entry, location)
    card.setProperty("backupLocation", location)
    card.setProperty("backupKind", record.kind)
    card._fh6_backup_entry = dict(entry)


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
        window.backup_status_label.setText(_final_status(counts))
        _backup_ui._relayout_backup(window)
        return

    window.backup_status_label.setText(
        _txt(
            f"백업 목록 준비 중 0/{total} · {_final_status(counts)}",
            f"Preparing backup list 0/{total} · {_final_status(counts)}",
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
            _configure_backup_card(window, card, record, entry, location)
            card.setProperty("backupRecord", record)
            window._fh6_backup_cards.append(card)

        if end < total:
            window.backup_status_label.setText(
                _txt(
                    f"백업 목록 준비 중 {end}/{total} · {_final_status(counts)}",
                    f"Preparing backup list {end}/{total} · {_final_status(counts)}",
                )
            )
            QTimer.singleShot(0, lambda next_start=end: build_chunk(next_start))
            return

        window.backup_status_label.setText(_final_status(counts))
        _backup_ui._relayout_backup(window)
        QTimer.singleShot(0, lambda owner=window: _backup_ui._sync_backup_widths(owner))
        QTimer.singleShot(0, lambda owner=window: _backup_ui._refresh_backup_thumbnails(owner))

    QTimer.singleShot(0, build_chunk)


def _backup_filter_allows(window: Any, card: Any) -> bool:
    mode = getattr(window, "_fh6_backup_location_filter", "all")
    location = str(card.property("backupLocation") or "")
    if mode != "all" and location != mode:
        return False

    kind = str(card.property("backupKind") or "")
    show_livery = bool(getattr(window, "backup_livery_toggle", None) is None or window.backup_livery_toggle.isChecked())
    show_auction = bool(getattr(window, "backup_auction_toggle", None) is None or window.backup_auction_toggle.isChecked())
    if kind == "Livery" and not show_livery:
        return False
    if kind == "SoulBoundLivery" and not show_auction:
        return False
    return True


def _set_location_button_checks(window: Any, mode: str) -> None:
    backup = getattr(window, "backup_only_toggle", None)
    both = getattr(window, "backup_both_toggle", None)
    if not isinstance(backup, QPushButton) or not isinstance(both, QPushButton):
        return
    backup.blockSignals(True)
    both.blockSignals(True)
    backup.setChecked(mode in {"all", "backup"})
    both.setChecked(mode in {"all", "both"})
    backup.blockSignals(False)
    both.blockSignals(False)


def _repolish_filter(window: Any) -> None:
    button = getattr(window, "backup_filter_button", None)
    if not isinstance(button, QToolButton):
        return
    button.setProperty("fh6FilterActive", getattr(window, "_fh6_backup_location_filter", "all") != "all")
    button.setStyleSheet(_perf._FILTER_BUTTON_STYLE)
    style = button.style()
    if isinstance(style, QStyle):
        style.unpolish(button)
        style.polish(button)
    button.update()


def _set_backup_location_filter(window: Any, mode: str) -> None:
    if mode not in {"all", "backup", "both"}:
        mode = "all"
    window._fh6_backup_location_filter = mode
    for key, action in getattr(window, "_fh6_backup_filter_actions", {}).items():
        action.setChecked(key == mode)
    _set_location_button_checks(window, mode)
    _repolish_filter(window)
    _backup_ui._relayout_backup(window)


def _location_toggle_changed(window: Any, changed: QPushButton) -> None:
    backup = window.backup_only_toggle
    both = window.backup_both_toggle
    if not backup.isChecked() and not both.isChecked():
        changed.blockSignals(True)
        changed.setChecked(True)
        changed.blockSignals(False)
    mode = "all" if backup.isChecked() and both.isChecked() else "backup" if backup.isChecked() else "both"
    _set_backup_location_filter(window, mode)


def _source_toggle_changed(window: Any, changed: QPushButton) -> None:
    livery = window.backup_livery_toggle
    auction = window.backup_auction_toggle
    if not livery.isChecked() and not auction.isChecked():
        changed.blockSignals(True)
        changed.setChecked(True)
        changed.blockSignals(False)
    _backup_ui._relayout_backup(window)


def _layout_with_widget(root_layout: Any, target: Any):
    if root_layout is None:
        return None
    for index in range(root_layout.count()):
        item = root_layout.itemAt(index)
        layout = item.layout() if item is not None else None
        if layout is None:
            continue
        for child_index in range(layout.count()):
            child = layout.itemAt(child_index)
            if child is not None and child.widget() is target:
                return layout
    return None


def _install_backup_display_row(window: Any) -> None:
    if isinstance(getattr(window, "backup_livery_toggle", None), QPushButton):
        return
    page = getattr(window, "backup_page", None)
    root = page.layout() if page is not None else None
    if root is None:
        return

    row = QHBoxLayout()
    row.setSpacing(7)
    label = QLabel(_txt("표시:", "Show:"))
    label.setObjectName("muted")
    row.addWidget(label)

    livery = QPushButton(_txt("내 디자인 리버리", "My Designs liveries"))
    auction = QPushButton(_txt("경매장 리버리", "Auction liveries"))
    for button in (livery, auction):
        button.setObjectName("secondary")
        button.setCheckable(True)
        button.setChecked(True)
        row.addWidget(button)

    separator = QLabel("││")
    separator.setObjectName("backupLocationSeparator")
    separator.setAlignment(Qt.AlignmentFlag.AlignCenter)
    separator.setStyleSheet("color:#b1a8c9;font-weight:700;padding:0 2px;")
    row.addWidget(separator)

    backup_only = QPushButton(_txt("백업만", "Backup only"))
    both = QPushButton(_txt("게임 + 백업", "Game + Backup"))
    for button in (backup_only, both):
        button.setObjectName("secondary")
        button.setCheckable(True)
        button.setChecked(True)
        row.addWidget(button)
    row.addStretch(1)

    window.backup_livery_toggle = livery
    window.backup_auction_toggle = auction
    window.backup_only_toggle = backup_only
    window.backup_both_toggle = both

    livery.toggled.connect(lambda _checked=False, owner=window, target=livery: _source_toggle_changed(owner, target))
    auction.toggled.connect(lambda _checked=False, owner=window, target=auction: _source_toggle_changed(owner, target))
    backup_only.toggled.connect(lambda _checked=False, owner=window, target=backup_only: _location_toggle_changed(owner, target))
    both.toggled.connect(lambda _checked=False, owner=window, target=both: _location_toggle_changed(owner, target))

    action_layout = None
    first_sort = next(iter(getattr(window, "backup_sort_buttons", {}).values()), None)
    if first_sort is not None:
        action_layout = _layout_with_widget(root, first_sort)
    insert_index = 3
    if action_layout is not None:
        for index in range(root.count()):
            item = root.itemAt(index)
            if item is not None and item.layout() is action_layout:
                insert_index = index
                break
    root.insertLayout(insert_index, row)
    window._fh6_backup_display_row = row

    # Backup page no longer has a game-only state. Keep the menu as an alternate
    # location filter for the two states that can actually appear here.
    actions = getattr(window, "_fh6_backup_filter_actions", {})
    menu = getattr(window, "backup_filter_button", None)
    menu = menu.menu() if isinstance(menu, QToolButton) else None
    game_action = actions.pop("game", None)
    if game_action is not None and menu is not None:
        menu.removeAction(game_action)
        game_action.deleteLater()
    if "all" in actions:
        actions["all"].setText(_txt("전체 백업", "All backups"))
    if "backup" in actions:
        actions["backup"].setText(_txt("백업만", "Backup only"))
    if "both" in actions:
        actions["both"].setText(_txt("게임 + 백업", "Game + Backup"))

    _set_backup_location_filter(window, "all")


def _sync_backup_design(window: Any) -> None:
    _perf._sync_backup_toolbar(window)
    path_edit = getattr(window, "backup_path_edit", None)
    choose = getattr(window, "backup_choose_button", None)
    if path_edit is not None:
        path_edit.setMinimumHeight(36)
    if isinstance(choose, QPushButton):
        choose.setMinimumHeight(36)

    for name in ("backup_livery_toggle", "backup_auction_toggle", "backup_only_toggle", "backup_both_toggle"):
        button = getattr(window, name, None)
        if isinstance(button, QPushButton):
            source = getattr(window, "livery_my_designs_toggle", None)
            if isinstance(source, QPushButton):
                button.setFont(source.font())
                button.setSizePolicy(source.sizePolicy())
                button.setMinimumHeight(source.minimumSizeHint().height())


class _ImportWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        backup_root: Path,
        entry: dict[str, Any],
        save_root: Path,
        active_version: str,
        delete_source: bool,
    ) -> None:
        super().__init__()
        self.backup_root = backup_root
        self.entry = dict(entry)
        self.save_root = save_root
        self.active_version = active_version
        self.delete_source = delete_source

    @Slot()
    def run(self) -> None:
        try:
            result = import_backup_entry(
                self.backup_root,
                self.entry,
                self.save_root,
                self.active_version,
                delete_source=self.delete_source,
            )
        except Exception as exc:  # noqa: BLE001 - worker boundary
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.finished.emit(result)


class _ImportUiBridge(QObject):
    def __init__(self, window: Any) -> None:
        super().__init__(window)
        self.window = window

    @Slot(object)
    def finished(self, result: object) -> None:
        _import_finished(self.window, result)

    @Slot(str)
    def failed(self, message: str) -> None:
        _import_failed(self.window, message)

    @Slot()
    def thread_finished(self) -> None:
        self.window._fh6_import_thread = None
        self.window._fh6_import_worker = None
        self.window._fh6_import_bridge = None


def _import_context(window: Any) -> tuple[Path, str]:
    result = getattr(window, "result", None)
    metadata = getattr(result, "metadata", None)
    save_root = getattr(metadata, "save_root", None)
    active_version = str(getattr(metadata, "active_version", "") or "")
    if not isinstance(save_root, Path):
        raise BackupRepositoryError("scan the FH6 save before importing")
    return save_root, active_version


def _confirm_import_policy(window: Any, record: LiveryRecord, save_root: Path, active_version: str) -> str:
    current, numbered = resolve_import_targets(save_root, active_version)
    box = QMessageBox(window)
    box.setWindowTitle(_txt("들여오기", "Import"))
    box.setIcon(QMessageBox.Icon.Question)
    box.setText(
        _txt(
            "백업 리버리를 다음 두 저장 위치에 복원합니다.\n\n"
            f"- {current}\n- {numbered}\n\n"
            "복원이 성공한 뒤 외부 백업 원본을 삭제하시겠습니까?\n"
            "FH6가 저장 중일 때는 들여오기를 실행하지 않는 것을 권장합니다.",
            "The backup livery will be restored to both save locations.\n\n"
            f"- {current}\n- {numbered}\n\n"
            "Delete the external backup source after a successful restore?\n"
            "Avoid importing while FH6 is actively saving.",
        )
    )
    keep = box.addButton(_txt("원본 유지", "Keep source"), QMessageBox.ButtonRole.AcceptRole)
    delete = box.addButton(_txt("원본 삭제", "Delete source"), QMessageBox.ButtonRole.DestructiveRole)
    cancel = box.addButton(_txt("취소", "Cancel"), QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(keep)
    box.exec()
    clicked = box.clickedButton()
    if clicked is delete:
        return "delete"
    if clicked is keep:
        return "keep"
    if clicked is cancel:
        return "cancel"
    return "cancel"


def _request_import(window: Any, record: LiveryRecord, entry: dict[str, Any]) -> None:
    if getattr(window, "_fh6_import_running", False) or getattr(window, "_fh6_export_running", False):
        return
    scan_thread = getattr(window, "_scan_thread", None)
    if scan_thread is not None and scan_thread.isRunning():
        window._show_status(_txt("스캔이 끝난 뒤 들여오기를 실행하세요.", "Wait for the scan to finish before importing."), 5000)
        return
    backup_root = _backup_ui._backup_root(window)
    if backup_root is None:
        return
    try:
        save_root, active_version = _import_context(window)
        policy = _confirm_import_policy(window, record, save_root, active_version)
    except BackupRepositoryError as exc:
        QMessageBox.warning(window, _txt("들여오기 준비 실패", "Import preparation failed"), str(exc))
        return
    if policy == "cancel":
        return

    window._fh6_import_running = True
    choose = getattr(window, "backup_choose_button", None)
    if isinstance(choose, QPushButton):
        choose.setEnabled(False)
    window._begin_busy(_txt("들여오는 중", "Importing"))

    thread = QThread(window)
    worker = _ImportWorker(
        backup_root,
        entry,
        save_root,
        active_version,
        policy == "delete",
    )
    bridge = _ImportUiBridge(window)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(bridge.finished)
    worker.failed.connect(bridge.failed)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(bridge.thread_finished)
    thread.finished.connect(thread.deleteLater)
    window._fh6_import_thread = thread
    window._fh6_import_worker = worker
    window._fh6_import_bridge = bridge
    thread.start()


def _finish_import_ui(window: Any) -> None:
    window._fh6_import_running = False
    choose = getattr(window, "backup_choose_button", None)
    if isinstance(choose, QPushButton):
        choose.setEnabled(True)
    window._end_busy()


def _import_finished(window: Any, result: object) -> None:
    _finish_import_ui(window)
    if not isinstance(result, ImportSummary):
        _import_failed(window, _txt("알 수 없는 들여오기 결과", "Unknown import result"), already_finished=True)
        return
    window._fh6_backup_presence_cache = ("", set(), set())
    if result.source_deleted:
        _rebuild_backup_cards(window)
    message = _txt(
        f"들여오기 완료 · 새 복원 {len(result.published)}곳 · 이미 동일 {len(result.already_present)}곳"
        + (" · 백업 원본 삭제" if result.source_deleted else ""),
        f"Import complete · restored {len(result.published)} target(s) · already identical {len(result.already_present)}"
        + (" · backup source deleted" if result.source_deleted else ""),
    )
    window._show_status(message, 8000)
    QMessageBox.information(window, _txt("들여오기 완료", "Import complete"), message)

    # Re-scan current after both save trees have been committed so the livery
    # page and backup location state are rebuilt from disk rather than guessed.
    path_edit = getattr(window, "path_edit", None)
    if path_edit is not None and path_edit.text().strip():
        window.refresh_scan()


def _import_failed(window: Any, message: str, *, already_finished: bool = False) -> None:
    if not already_finished:
        _finish_import_ui(window)
    QMessageBox.warning(window, _txt("들여오기 실패", "Import failed"), message)


def apply_v1_3_4_backup_import_refinement_patch(MainWindow: Any) -> None:
    if getattr(MainWindow, "_fh6_v134_backup_import_refinement_patched", False):
        return

    # Replace the external-copy backend after the earlier performance layer.
    # This retains verified staging while pruning stale index rows and committing
    # the JSON index once per batch.
    _backup_ui.export_records = _safe_export_records

    # Backup view is repository-centric: game-only records are intentionally not
    # constructed at all, eliminating hundreds of irrelevant gray cards.
    _backup_ui._backup_items = _backup_items
    _backup_ui._rebuild_backup_cards = _rebuild_backup_cards
    _backup_ui._backup_filter_allows = _backup_filter_allows
    _backup_ui._set_backup_location_filter = _set_backup_location_filter

    original_init = MainWindow.__init__

    def patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        self._fh6_import_running = False
        self._fh6_import_thread = None
        self._fh6_import_worker = None
        self._fh6_import_bridge = None
        original_init(self, *args, **kwargs)
        _install_backup_display_row(self)
        _sync_backup_design(self)
        _rebuild_backup_cards(self)

    MainWindow.__init__ = patched_init
    MainWindow._fh6_v134_backup_import_refinement_patched = True
