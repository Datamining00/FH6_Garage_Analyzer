from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import Any

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QGridLayout, QMessageBox, QToolButton, QWidget

from . import v1_3_4_backup_export_patch as _backup_ui
from . import v1_3_4_backup_import_refinement_patch as _backup_ref
from . import v1_3_4_card_features_patch as _features
from .backup_export import ExportSummary, content_sha256, folder_fingerprint, load_index
from .models import LiveryRecord


_ICON_SLOT_COUNT = 6
_ICON_BUTTON_HEIGHT = 30
_METADATA_CHUNK = 16
_DELETE_STAGING = ".fh6_assistant_delete_staging"


def _normalize_action_spacing(card: Any) -> None:
    grid = getattr(card, "_fh6_action_grid", None)
    if not isinstance(grid, QGridLayout):
        return
    left = [getattr(card, name, None) for name in (
        "_fh6_game_move_button", "_fh6_zoom_button", "_fh6_memo_button",
        "_fh6_info_button", "_fh6_folder_button", "_fh6_export_placeholder_button",
    )]
    right = [getattr(card, name, None) for name in (
        "_fh6_applied_state_button", "_fh6_lock_placeholder_button", "_fh6_hide_button",
        "_fh6_check_box", "_fh6_triangle_box", "_fh6_excluded_box",
    )]
    if not any(isinstance(button, QToolButton) for button in left + right):
        return
    for button in left + right:
        if isinstance(button, QToolButton):
            grid.removeWidget(button)
    grid.setContentsMargins(5, 5, 5, 5)
    grid.setHorizontalSpacing(0)
    grid.setVerticalSpacing(0)
    grid.setColumnStretch(0, 1)
    grid.setColumnStretch(1, 1)
    for row in range(_ICON_SLOT_COUNT * 2 - 1):
        grid.setRowMinimumHeight(row, _ICON_BUTTON_HEIGHT if row % 2 == 0 else 0)
        grid.setRowStretch(row, 0 if row % 2 == 0 else 1)
    for slot, (left_button, right_button) in enumerate(zip(left, right)):
        row = slot * 2
        if isinstance(left_button, QToolButton):
            grid.addWidget(left_button, row, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            left_button.show()
        if isinstance(right_button, QToolButton):
            grid.addWidget(right_button, row, 1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            right_button.show()
    grid.invalidate()


def _set_metadata_collapsed_fast(window: Any, collapsed: bool) -> None:
    collapsed = bool(collapsed)
    preferences = getattr(window, "local_preferences", None)
    setter = getattr(preferences, "set_bool", None)
    if callable(setter):
        setter(_features._METADATA_COLLAPSED_PREF, collapsed)
    window._fh6_v134_metadata_collapsed = collapsed
    cards = _features._registered_metadata_cards(window)
    sender = window.sender() if hasattr(window, "sender") else None
    active_card = sender.parentWidget() if isinstance(sender, QToolButton) else None
    ordered: list[QWidget] = []
    if isinstance(active_card, QWidget) and active_card in cards:
        ordered.append(active_card)
    ordered.extend(card for card in cards if card is not active_card and card.isVisible())
    ordered.extend(card for card in cards if card is not active_card and not card.isVisible())
    generation = int(getattr(window, "_fh6_metadata_toggle_generation", 0) or 0) + 1
    window._fh6_metadata_toggle_generation = generation

    def apply_chunk(start: int = 0) -> None:
        if generation != int(getattr(window, "_fh6_metadata_toggle_generation", 0) or 0):
            return
        end = min(len(ordered), start + _METADATA_CHUNK)
        for card in ordered[start:end]:
            try:
                if bool(card.property("fh6MetadataRightCollapsed")) != collapsed:
                    _features._apply_metadata_state(card, collapsed)
            except RuntimeError:
                continue
        if end < len(ordered):
            QTimer.singleShot(0, lambda next_start=end: apply_chunk(next_start))
    apply_chunk(0)


def _verified_backup_path(root: Path, record: LiveryRecord) -> Path | None:
    try:
        root = root.resolve()
        source = Path(record.container_path).resolve()
        digest = content_sha256(record).casefold()
        source_fingerprint = folder_fingerprint(source)
        if not digest or not source_fingerprint:
            return None
        payload = load_index(root)
        kind = str(record.kind or "").strip().casefold()
        for entry in payload.get("entries", []):
            if not isinstance(entry, dict):
                continue
            if str(entry.get("kind") or "").strip().casefold() != kind:
                continue
            if str(entry.get("content_sha256") or "").strip().casefold() != digest:
                continue
            relative = str(entry.get("relative_path") or "")
            if not relative:
                continue
            backup_path = (root / relative).resolve()
            try:
                backup_path.relative_to(root)
            except ValueError:
                continue
            if not backup_path.is_dir():
                continue
            expected = str(entry.get("folder_fingerprint") or "").strip().casefold()
            if expected != source_fingerprint.casefold():
                continue
            if folder_fingerprint(backup_path).casefold() != source_fingerprint.casefold():
                continue
            return backup_path
    except (OSError, ValueError):
        return None
    return None


def _game_source_targets(window: Any, record: LiveryRecord) -> tuple[list[Path], str]:
    """Resolve Current + active/latest numbered copies and verify all before delete."""
    if str(record.kind or "") != "Livery":
        return [], "only normal Livery sources can be deleted"
    result = getattr(window, "result", None)
    metadata = getattr(result, "metadata", None)
    save_root = getattr(metadata, "save_root", None)
    active_version = str(getattr(metadata, "active_version", "") or "")
    if not isinstance(save_root, Path):
        return [], "save root is unavailable"
    source = Path(record.container_path)
    source_fingerprint = folder_fingerprint(source).casefold() if source.is_dir() else ""
    if not source_fingerprint or not (source / "C_livery").is_file():
        return [], "source fingerprint is unavailable"
    try:
        roots = _backup_ref.resolve_import_targets(save_root, active_version)
    except Exception as exc:  # noqa: BLE001 - safety boundary
        return [], f"save target resolution failed: {type(exc).__name__}: {exc}"

    targets: list[Path] = []
    seen: set[str] = set()
    for containers_root in roots:
        try:
            root = containers_root.resolve()
            destination = (root / record.container_name).resolve()
            destination.relative_to(root)
        except (OSError, ValueError):
            return [], "source path safety check failed"
        key = os.path.normcase(str(destination))
        if key in seen:
            continue
        seen.add(key)
        if not destination.exists():
            continue
        if not destination.is_dir() or not (destination / "C_livery").is_file():
            return [], f"destination conflict: {destination}"
        peer_fingerprint = folder_fingerprint(destination).casefold()
        if not peer_fingerprint or peer_fingerprint != source_fingerprint:
            return [], f"destination content conflict: {destination}"
        targets.append(destination)

    if not targets:
        return [], "no matching game-side source exists"
    try:
        scanned = source.resolve()
    except OSError:
        return [], "scanned source path cannot be resolved"
    if all(os.path.normcase(str(scanned)) != os.path.normcase(str(path)) for path in targets):
        return [], "scanned source is not one of the active save targets"
    return targets, ""


def _park_and_delete_targets(targets: list[Path]) -> tuple[bool, str]:
    """Rename all targets out of the live tree first; roll back if parking fails."""
    parked: list[tuple[Path, Path, Path]] = []
    try:
        for source in targets:
            staging_root = source.parent / _DELETE_STAGING
            staging_root.mkdir(parents=True, exist_ok=True)
            parked_path = staging_root / uuid.uuid4().hex
            os.replace(source, parked_path)
            parked.append((source, parked_path, staging_root))
    except OSError as exc:
        for source, parked_path, _staging_root in reversed(parked):
            try:
                if parked_path.exists() and not source.exists():
                    os.replace(parked_path, source)
            except OSError:
                pass
        return False, f"source parking failed: {type(exc).__name__}: {exc}"

    failures: list[str] = []
    for _source, parked_path, staging_root in parked:
        try:
            shutil.rmtree(parked_path)
        except OSError as exc:
            failures.append(f"{parked_path}: {type(exc).__name__}: {exc}")
        try:
            if staging_root.is_dir() and not any(staging_root.iterdir()):
                staging_root.rmdir()
        except OSError:
            pass
    return not failures, "; ".join(failures)


def _delete_verified_sources(window: Any, records: list[LiveryRecord]) -> tuple[int, list[str]]:
    root = _backup_ui._backup_root(window)
    if root is None:
        return 0, ["backup repository is unavailable"]
    try:
        root = root.resolve()
    except OSError:
        return 0, ["backup repository path cannot be resolved"]
    deleted = 0
    failures: list[str] = []
    for record in records:
        label = record.header.name or record.container_name or "(unnamed)"
        if _verified_backup_path(root, record) is None:
            failures.append(f"{label}: backup fingerprint verification failed")
            continue
        targets, reason = _game_source_targets(window, record)
        if not targets:
            failures.append(f"{label}: {reason}")
            continue
        success, delete_error = _park_and_delete_targets(targets)
        if not success:
            failures.append(f"{label}: {delete_error}")
            continue
        deleted += 1
    return deleted, failures


def _schedule_rescan(window: Any) -> None:
    path_edit = getattr(window, "path_edit", None)
    start_scan = getattr(window, "start_scan", None)
    if path_edit is None or not callable(start_scan):
        return
    raw = str(path_edit.text() or "").strip()
    path = Path(raw) if raw else None
    if path is not None and path.is_dir():
        QTimer.singleShot(0, lambda target=path, scan=start_scan: scan(target))


def apply_v1_3_4_card_polish_export_delete_patch(MainWindow: Any) -> None:
    if getattr(MainWindow, "_fh6_v134_card_polish_export_delete_patched", False):
        return
    original_make_card = MainWindow._make_saved_content_card

    def make_card(self: Any, content_type: str, record: Any, key: str):
        card = original_make_card(self, content_type, record, key)
        _normalize_action_spacing(card)
        return card

    original_backup_configure = _backup_ref._configure_backup_card

    def configure_backup_card(window: Any, card: Any, *args: Any, **kwargs: Any) -> None:
        original_backup_configure(window, card, *args, **kwargs)
        _normalize_action_spacing(card)

    _features._set_metadata_collapsed = _set_metadata_collapsed_fast
    _backup_ref._configure_backup_card = configure_backup_card

    original_request_export = _backup_ui._request_export
    original_export_finished = _backup_ui._export_finished
    original_export_failed = _backup_ui._export_failed

    def request_export(window: Any, records: list[LiveryRecord]) -> None:
        window._fh6_export_source_candidates = list(records)
        window._fh6_export_delete_source_requested = False
        original_request_export(window, records)
        if not bool(getattr(window, "_fh6_export_running", False)):
            window._fh6_export_source_candidates = []
            window._fh6_export_delete_source_requested = False

    def export_finished(window: Any, result: object) -> None:
        records = list(getattr(window, "_fh6_export_source_candidates", []) or [])
        delete_requested = bool(getattr(window, "_fh6_export_delete_source_requested", False))
        deleted = 0
        failures: list[str] = []
        if delete_requested and isinstance(result, ExportSummary):
            deleted, failures = _delete_verified_sources(window, records)
        window._fh6_export_source_candidates = []
        window._fh6_export_delete_source_requested = False
        original_export_finished(window, result)
        if delete_requested:
            if deleted:
                window._show_status(_backup_ui._txt(
                    f"백업 검증 후 게임 원본 {deleted}개를 삭제했습니다.",
                    f"Deleted {deleted} game-side source item(s) after backup verification.",
                ), 7000)
                _schedule_rescan(window)
            if failures:
                QMessageBox.warning(
                    window,
                    _backup_ui._txt("원본 삭제 확인", "Source deletion check"),
                    _backup_ui._txt(
                        "일부 원본은 안전 검증에 실패하여 삭제하지 않았습니다.\n\n",
                        "Some sources were not deleted because safety verification failed.\n\n",
                    ) + "\n".join(failures[:8]),
                )

    def export_failed(window: Any, message: str, *args: Any, **kwargs: Any) -> None:
        window._fh6_export_source_candidates = []
        window._fh6_export_delete_source_requested = False
        original_export_failed(window, message, *args, **kwargs)

    MainWindow._make_saved_content_card = make_card
    _backup_ui._request_export = request_export
    _backup_ui._export_finished = export_finished
    _backup_ui._export_failed = export_failed
    MainWindow._fh6_v134_card_polish_export_delete_patched = True
