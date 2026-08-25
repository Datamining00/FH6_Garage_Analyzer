from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .cache_housekeeping import cleanup_stale_temp_files
from .models import LiveryRecord, ScanResult

_SCHEMA = 1
_TRACKED_KINDS = {"Livery", "SoulBoundLivery"}


@dataclass(slots=True)
class LiverySnapshotEntry:
    identity: str
    kind: str
    container_name: str
    guid: str
    car_id: int | None
    name: str
    creator: str
    description: str
    created: str
    decal_count: int | None
    platform_code: int | None
    content_sha256: str
    thumbnail_cache: str

    def change_fingerprint(self) -> tuple[Any, ...]:
        return (
            self.kind,
            self.guid,
            self.car_id,
            self.name,
            self.creator,
            self.description,
            self.created,
            self.decal_count,
            self.platform_code,
            self.content_sha256,
        )


@dataclass(slots=True)
class LiveryRefreshChange:
    status: str
    before: LiverySnapshotEntry | None = None
    after: LiverySnapshotEntry | None = None


@dataclass(slots=True)
class LiveryRefreshDiff:
    baseline: bool
    scope: str
    added: list[LiveryRefreshChange]
    removed: list[LiveryRefreshChange]
    changed: list[LiveryRefreshChange]
    cache_files: int = 0
    cache_bytes: int = 0
    cleanup_removed_files: int = 0
    cleanup_removed_bytes: int = 0

    @property
    def total(self) -> int:
        return len(self.added) + len(self.removed) + len(self.changed)


def default_refresh_history_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    return base / "FH6GarageAnalyzer" / "refresh_history"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_cache_file_size(path: Path) -> int:
    try:
        return max(0, int(path.stat().st_size))
    except OSError:
        return 0


def _cache_thumbnail(source: Path | None, cache_dir: Path) -> str:
    if source is None:
        return ""
    try:
        source = Path(source)
        if not source.is_file():
            return ""
        digest = _sha256_file(source)
        suffix = source.suffix.lower()
        if not suffix or len(suffix) > 10:
            suffix = ".img"
        cache_dir.mkdir(parents=True, exist_ok=True)
        target = cache_dir / f"{digest}{suffix}"
        if not target.is_file():
            fd, temporary_name = tempfile.mkstemp(
                prefix="refresh_thumb_",
                suffix=".tmp",
                dir=str(cache_dir),
            )
            os.close(fd)
            temporary = Path(temporary_name)
            try:
                shutil.copyfile(source, temporary)
                os.replace(temporary, target)
            finally:
                if temporary.exists():
                    try:
                        temporary.unlink()
                    except OSError:
                        pass
        return target.name
    except OSError:
        return ""


def _physical_identity(record: LiveryRecord) -> str:
    return f"{record.kind}:{record.container_name.casefold()}"


def _snapshot_entry(record: LiveryRecord, thumbnails_dir: Path) -> LiverySnapshotEntry:
    header = record.header
    return LiverySnapshotEntry(
        identity=_physical_identity(record),
        kind=record.kind,
        container_name=record.container_name,
        guid=(header.guid or "").strip(),
        car_id=header.car_id,
        name=header.name or "",
        creator=header.creator or "",
        description=header.description or "",
        created=header.created or "",
        decal_count=header.decal_count,
        platform_code=header.platform_code,
        content_sha256=record.content_sha256 or "",
        thumbnail_cache=_cache_thumbnail(record.thumbnail_path, thumbnails_dir),
    )


def _scope_for_result(result: ScanResult) -> str:
    try:
        return str(result.metadata.save_root.expanduser().resolve()).casefold()
    except OSError:
        return str(result.metadata.save_root).casefold()


def _load_snapshot(path: Path) -> tuple[str, list[LiverySnapshotEntry]]:
    if not path.is_file():
        return "", []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return "", []
    if not isinstance(data, dict) or data.get("schema") != _SCHEMA:
        return "", []
    scope = str(data.get("scope") or "")
    raw_entries = data.get("entries")
    if not isinstance(raw_entries, list):
        return scope, []
    entries: list[LiverySnapshotEntry] = []
    for raw in raw_entries:
        if not isinstance(raw, dict):
            continue
        try:
            entries.append(LiverySnapshotEntry(**raw))
        except (TypeError, ValueError):
            continue
    return scope, entries


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f"{path.stem}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            try:
                temporary.unlink()
            except OSError:
                pass


def _save_snapshot(path: Path, scope: str, entries: list[LiverySnapshotEntry]) -> None:
    _atomic_write_json(
        path,
        {"schema": _SCHEMA, "scope": scope, "entries": [asdict(entry) for entry in entries]},
    )


def _unique_key_map(entries: list[LiverySnapshotEntry], field_name: str) -> dict[tuple[str, str], LiverySnapshotEntry]:
    buckets: dict[tuple[str, str], list[LiverySnapshotEntry]] = {}
    for entry in entries:
        value = str(getattr(entry, field_name) or "").strip().casefold()
        if value:
            buckets.setdefault((entry.kind, value), []).append(entry)
    return {key: values[0] for key, values in buckets.items() if len(values) == 1}


def _reconcile_unmatched(old_entries: list[LiverySnapshotEntry], new_entries: list[LiverySnapshotEntry]) -> list[tuple[LiverySnapshotEntry, LiverySnapshotEntry]]:
    pairs: list[tuple[LiverySnapshotEntry, LiverySnapshotEntry]] = []
    old_remaining = list(old_entries)
    new_remaining = list(new_entries)
    for field_name in ("guid", "content_sha256"):
        old_map = _unique_key_map(old_remaining, field_name)
        new_map = _unique_key_map(new_remaining, field_name)
        matched_old: set[int] = set()
        matched_new: set[int] = set()
        for key in sorted(set(old_map) & set(new_map)):
            before = old_map[key]
            after = new_map[key]
            pairs.append((before, after))
            matched_old.add(id(before))
            matched_new.add(id(after))
        old_remaining = [entry for entry in old_remaining if id(entry) not in matched_old]
        new_remaining = [entry for entry in new_remaining if id(entry) not in matched_new]
    return pairs


def diff_livery_snapshots(old_entries: list[LiverySnapshotEntry], new_entries: list[LiverySnapshotEntry]) -> LiveryRefreshDiff:
    old_by_identity = {entry.identity: entry for entry in old_entries}
    new_by_identity = {entry.identity: entry for entry in new_entries}
    added: list[LiveryRefreshChange] = []
    removed: list[LiveryRefreshChange] = []
    changed: list[LiveryRefreshChange] = []

    shared = set(old_by_identity) & set(new_by_identity)
    for identity in sorted(shared):
        before = old_by_identity[identity]
        after = new_by_identity[identity]
        if before.change_fingerprint() != after.change_fingerprint():
            changed.append(LiveryRefreshChange("changed", before=before, after=after))

    old_unmatched = [old_by_identity[key] for key in sorted(set(old_by_identity) - shared)]
    new_unmatched = [new_by_identity[key] for key in sorted(set(new_by_identity) - shared)]
    reconciled = _reconcile_unmatched(old_unmatched, new_unmatched)
    reconciled_old_ids = {id(before) for before, _after in reconciled}
    reconciled_new_ids = {id(after) for _before, after in reconciled}

    for before, after in reconciled:
        if before.change_fingerprint() != after.change_fingerprint() or before.identity != after.identity:
            changed.append(LiveryRefreshChange("changed", before=before, after=after))
    for entry in old_unmatched:
        if id(entry) not in reconciled_old_ids:
            removed.append(LiveryRefreshChange("removed", before=entry))
    for entry in new_unmatched:
        if id(entry) not in reconciled_new_ids:
            added.append(LiveryRefreshChange("added", after=entry))

    return LiveryRefreshDiff(False, "", added, removed, changed)


def _serialize_change(change: LiveryRefreshChange) -> dict[str, Any]:
    return {
        "status": change.status,
        "before": asdict(change.before) if change.before is not None else None,
        "after": asdict(change.after) if change.after is not None else None,
    }


def _save_latest_diff(path: Path, diff: LiveryRefreshDiff) -> None:
    _atomic_write_json(
        path,
        {
            "schema": _SCHEMA,
            "baseline": diff.baseline,
            "scope": diff.scope,
            "added": [_serialize_change(item) for item in diff.added],
            "removed": [_serialize_change(item) for item in diff.removed],
            "changed": [_serialize_change(item) for item in diff.changed],
        },
    )


def _referenced_thumbnail_names(current_entries: list[LiverySnapshotEntry], diff: LiveryRefreshDiff) -> set[str]:
    keep = {entry.thumbnail_cache for entry in current_entries if entry.thumbnail_cache}
    for change in (*diff.added, *diff.removed, *diff.changed):
        for entry in (change.before, change.after):
            if entry is not None and entry.thumbnail_cache:
                keep.add(entry.thumbnail_cache)
    return keep


def _prune_thumbnail_cache(cache_dir: Path, keep: set[str]) -> None:
    if not cache_dir.is_dir():
        return
    for path in cache_dir.iterdir():
        if (
            not path.is_file()
            or path.name in keep
            or path.suffix.casefold() == ".tmp"
        ):
            continue
        try:
            path.unlink()
        except OSError:
            pass


def process_livery_refresh(
    result: ScanResult,
    history_dir: Path | None = None,
    yield_hook: Callable[[int], None] | None = None,
) -> LiveryRefreshDiff:
    """Compare current liveries with the last snapshot without modifying FH6 files.

    Current thumbnails are copied into a content-addressed LocalAppData cache so
    a livery that disappears on the next scan still has an image for the latest
    refresh diff.  ``yield_hook`` lets the GUI service paint/timer events while
    a large cache is being hashed and updated.
    """
    root = Path(history_dir) if history_dir is not None else default_refresh_history_dir()
    snapshot_path = root / "snapshot.json"
    diff_path = root / "latest_diff.json"
    thumbnails_dir = root / "thumbnails"
    scope = _scope_for_result(result)
    cleanup = cleanup_stale_temp_files(root, recursive=True)

    current_entries: list[LiverySnapshotEntry] = []
    for index, record in enumerate(result.liveries):
        if record.kind not in _TRACKED_KINDS:
            continue
        if yield_hook is not None:
            yield_hook(index)
        current_entries.append(_snapshot_entry(record, thumbnails_dir))

    old_scope, old_entries = _load_snapshot(snapshot_path)
    if not old_entries or old_scope != scope:
        diff = LiveryRefreshDiff(True, scope, [], [], [])
    else:
        diff = diff_livery_snapshots(old_entries, current_entries)
        diff.scope = scope

    _save_snapshot(snapshot_path, scope, current_entries)
    _save_latest_diff(diff_path, diff)
    _prune_thumbnail_cache(thumbnails_dir, _referenced_thumbnail_names(current_entries, diff))
    try:
        cached_files = [path for path in thumbnails_dir.iterdir() if path.is_file()]
    except OSError:
        cached_files = []
    diff.cache_files = len(cached_files)
    diff.cache_bytes = sum(_safe_cache_file_size(path) for path in cached_files)
    diff.cleanup_removed_files = cleanup.removed_files
    diff.cleanup_removed_bytes = cleanup.removed_bytes
    return diff


def cached_thumbnail_path(entry: LiverySnapshotEntry | None, history_dir: Path | None = None) -> Path | None:
    if entry is None or not entry.thumbnail_cache:
        return None
    root = Path(history_dir) if history_dir is not None else default_refresh_history_dir()
    path = root / "thumbnails" / entry.thumbnail_cache
    return path if path.is_file() else None
