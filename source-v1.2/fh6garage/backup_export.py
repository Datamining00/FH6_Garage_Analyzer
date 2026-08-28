from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .local_storage import write_json_atomic
from .models import HeaderInfo, LiveryRecord


SCHEMA = 1
INDEX_NAME = "backup_index.json"
STAGING_NAME = ".staging"

_INVALID_COMPONENT = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_WINDOWS_NAMES = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


class BackupRepositoryError(RuntimeError):
    pass


@dataclass(slots=True)
class ExportSummary:
    exported: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)


def safe_component(value: str, fallback: str) -> str:
    text = _INVALID_COMPONENT.sub("_", (value or "").strip())
    text = text.rstrip(" .")
    if not text:
        text = fallback
    if text.casefold() in _RESERVED_WINDOWS_NAMES:
        text = f"_{text}"
    return text[:120]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()


def content_sha256(record: LiveryRecord) -> str:
    digest = str(record.content_sha256 or "").strip().casefold()
    if digest:
        return digest
    path = record.livery_path
    if path is None or not path.is_file():
        return ""
    return file_sha256(path)


def folder_fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        files = sorted(
            (candidate for candidate in path.rglob("*") if candidate.is_file()),
            key=lambda candidate: candidate.relative_to(path).as_posix().casefold(),
        )
        for candidate in files:
            relative = candidate.relative_to(path).as_posix().encode("utf-8", "surrogatepass")
            digest.update(len(relative).to_bytes(4, "little"))
            digest.update(relative)
            digest.update(b"\0")
            with candidate.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()


def _empty_index() -> dict[str, Any]:
    return {"schema": SCHEMA, "entries": []}


def load_index(root: Path) -> dict[str, Any]:
    path = root / INDEX_NAME
    if not path.is_file():
        return _empty_index()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BackupRepositoryError(f"backup index read failed: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        raise BackupRepositoryError("unsupported or invalid backup index")
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise BackupRepositoryError("invalid backup index entries")
    return payload


def save_index(root: Path, payload: dict[str, Any]) -> None:
    if not write_json_atomic(root / INDEX_NAME, payload):
        raise BackupRepositoryError("backup index write failed")


def _entry_identity(entry: dict[str, Any]) -> tuple[str, str]:
    return (
        str(entry.get("kind") or "").strip().casefold(),
        str(entry.get("content_sha256") or "").strip().casefold(),
    )


def _record_identity(record: LiveryRecord, *, hash_if_needed: bool) -> tuple[str, str]:
    digest = str(record.content_sha256 or "").strip().casefold()
    if not digest and hash_if_needed:
        digest = content_sha256(record)
    return (str(record.kind or "").strip().casefold(), digest)


def backup_contains_record(
    root: Path,
    record: LiveryRecord,
    *,
    index: dict[str, Any] | None = None,
    hash_if_needed: bool = False,
) -> bool:
    if not root.is_dir():
        return False
    payload = index if index is not None else load_index(root)
    entries = [entry for entry in payload.get("entries", []) if isinstance(entry, dict)]
    kind = str(record.kind or "").strip().casefold()
    container = str(record.container_name or "").strip().casefold()
    for entry in entries:
        if (
            str(entry.get("kind") or "").strip().casefold() == kind
            and str(entry.get("original_container_name") or "").strip().casefold() == container
        ):
            relative = str(entry.get("relative_path") or "")
            if relative and (root / relative).is_dir():
                return True

    identity = _record_identity(record, hash_if_needed=hash_if_needed)
    if not identity[1]:
        return False
    for entry in entries:
        if _entry_identity(entry) == identity:
            relative = str(entry.get("relative_path") or "")
            if relative and (root / relative).is_dir():
                return True
    return False


def _unique_destination(parent: Path, container_name: str, digest: str) -> Path:
    candidate = parent / safe_component(container_name, f"item_{digest[:8]}")
    if not candidate.exists():
        return candidate
    suffix = digest[:8] or uuid.uuid4().hex[:8]
    candidate = parent / f"{safe_component(container_name, 'item')}__{suffix}"
    index = 2
    while candidate.exists():
        candidate = parent / f"{safe_component(container_name, 'item')}__{suffix}_{index}"
        index += 1
    return candidate


def _thumbnail_relative(record: LiveryRecord) -> str:
    path = record.thumbnail_path
    if path is None:
        return ""
    try:
        return path.relative_to(record.container_path).as_posix()
    except (ValueError, OSError):
        return ""


def _entry_for(
    root: Path,
    final_path: Path,
    record: LiveryRecord,
    digest: str,
    fingerprint: str,
) -> dict[str, Any]:
    header = record.header
    return {
        "kind": record.kind,
        "content_sha256": digest,
        "folder_fingerprint": fingerprint,
        "relative_path": final_path.relative_to(root).as_posix(),
        "original_container_name": record.container_name,
        "creator": header.creator or "",
        "name": header.name or "",
        "description": header.description or "",
        "created": header.created or "",
        "car_id": header.car_id,
        "guid": header.guid or "",
        "thumbnail_relative": _thumbnail_relative(record),
        "downloaded_at": record.downloaded_at,
        "backup_time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def export_records(root: Path, records: Iterable[LiveryRecord]) -> ExportSummary:
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
                    {"container_name": record.container_name, "kind": record.kind, "content_sha256": digest}
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
                if folder_fingerprint(stage) != source_fingerprint:
                    raise BackupRepositoryError("staging fingerprint mismatch")
                os.replace(stage, final_path)
            finally:
                if stage.exists():
                    shutil.rmtree(stage, ignore_errors=True)

            if folder_fingerprint(final_path) != source_fingerprint:
                shutil.rmtree(final_path, ignore_errors=True)
                raise BackupRepositoryError("final fingerprint mismatch")

            entry = _entry_for(root, final_path, record, digest, source_fingerprint)
            entries.append(entry)
            try:
                save_index(root, payload)
            except Exception:
                entries.pop()
                shutil.rmtree(final_path, ignore_errors=True)
                raise
            existing.add(identity)
            summary.exported.append(entry)
        except Exception as exc:  # noqa: BLE001 - batch export isolates per-item failures
            summary.failed.append((label, f"{type(exc).__name__}: {exc}"))

    try:
        if staging_root.is_dir() and not any(staging_root.iterdir()):
            staging_root.rmdir()
    except OSError:
        pass
    return summary


def backup_records(root: Path) -> list[tuple[dict[str, Any], LiveryRecord]]:
    root = root.expanduser().resolve()
    if not root.is_dir():
        return []
    payload = load_index(root)
    result: list[tuple[dict[str, Any], LiveryRecord]] = []
    for entry in payload.get("entries", []):
        if not isinstance(entry, dict):
            continue
        relative = str(entry.get("relative_path") or "")
        if not relative:
            continue
        container_path = root / relative
        if not container_path.is_dir():
            continue
        thumbnail_relative = str(entry.get("thumbnail_relative") or "")
        thumbnail_path = container_path / thumbnail_relative if thumbnail_relative else None
        if thumbnail_path is not None and not thumbnail_path.is_file():
            thumbnail_path = None
        livery_path = container_path / "C_livery"
        if not livery_path.is_file():
            livery_path = None
        car_id = entry.get("car_id")
        try:
            car_id = int(car_id) if car_id is not None else None
        except (TypeError, ValueError):
            car_id = None
        header = HeaderInfo(
            name=str(entry.get("name") or ""),
            description=str(entry.get("description") or ""),
            creator=str(entry.get("creator") or ""),
            created=str(entry.get("created") or ""),
            car_id=car_id,
            guid=str(entry.get("guid") or ""),
        )
        record = LiveryRecord(
            container_name=str(entry.get("original_container_name") or container_path.name),
            container_path=container_path,
            kind=str(entry.get("kind") or "Livery"),
            header=header,
            thumbnail_path=thumbnail_path,
            livery_path=livery_path,
            downloaded_at=entry.get("downloaded_at") if isinstance(entry.get("downloaded_at"), (int, float)) else None,
            content_sha256=str(entry.get("content_sha256") or ""),
        )
        result.append((entry, record))
    return result


def game_contains_backup_entry(entry: dict[str, Any], records: Iterable[LiveryRecord]) -> bool:
    kind = str(entry.get("kind") or "").strip().casefold()
    container = str(entry.get("original_container_name") or "").strip().casefold()
    digest = str(entry.get("content_sha256") or "").strip().casefold()
    for record in records:
        if str(record.kind or "").strip().casefold() != kind:
            continue
        if container and str(record.container_name or "").strip().casefold() == container:
            return True
        record_digest = str(record.content_sha256 or "").strip().casefold()
        if digest and record_digest and record_digest == digest:
            return True
    return False
