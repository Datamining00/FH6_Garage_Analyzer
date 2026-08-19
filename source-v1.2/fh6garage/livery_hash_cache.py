from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Callable, Iterable


_SCHEMA = 1
_LOCK = threading.RLock()
_STATE: dict[str, dict] = {}


def _cache_file() -> Path:
    override = os.environ.get("FH6_ASSISTANT_HASH_CACHE")
    if override:
        return Path(override)
    base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    return base / "FH6GarageAnalyzer" / "livery_hash_cache.json"


def cache_key(path: Path | str) -> str:
    try:
        resolved = Path(path).expanduser().resolve()
    except OSError:
        resolved = Path(path).expanduser().absolute()
    return os.path.normcase(str(resolved))


def _signature(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return int(stat.st_size), int(stat.st_mtime_ns)


def _load_state(path: Path) -> dict:
    key = str(path)
    with _LOCK:
        cached = _STATE.get(key)
        if cached is not None:
            return cached
        payload: dict = {"schema": _SCHEMA, "entries": {}}
        if path.is_file():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict) and loaded.get("schema") == _SCHEMA and isinstance(loaded.get("entries"), dict):
                    payload = {"schema": _SCHEMA, "entries": loaded["entries"]}
            except (OSError, UnicodeError, json.JSONDecodeError):
                pass
        _STATE[key] = payload
        return payload


def _save_state(path: Path, payload: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        os.replace(temporary, path)
    except OSError:
        return


def lookup_cached_sha256(path: Path | str) -> str:
    """Return a valid cached digest without reading the file body."""
    source = Path(path)
    signature = _signature(source)
    if signature is None:
        return ""
    cache_path = _cache_file()
    payload = _load_state(cache_path)
    with _LOCK:
        raw_entry = payload.get("entries", {}).get(cache_key(source))
        entry = dict(raw_entry) if isinstance(raw_entry, dict) else None
    if entry is None:
        return ""
    if int(entry.get("size", -1)) != signature[0] or int(entry.get("mtime_ns", -1)) != signature[1]:
        return ""
    digest = str(entry.get("sha256") or "")
    return digest if len(digest) == 64 else ""


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                total += len(chunk)
                digest.update(chunk)
    except OSError:
        return "", total
    return digest.hexdigest(), total


def enrich_sha256(
    paths: Iterable[Path | str],
    *,
    should_stop: Callable[[], bool] | None = None,
) -> tuple[dict[str, str], dict[str, int]]:
    """Resolve cached hashes and compute only stale/missing entries.

    File bodies are hashed outside the cache lock. New entries are merged under
    the lock once per batch, so startup cache lookups remain responsive while a
    background enrichment worker is processing a large garage.
    """
    cache_path = _cache_file()
    payload = _load_state(cache_path)
    with _LOCK:
        entries_snapshot = {
            key: dict(value)
            for key, value in payload.setdefault("entries", {}).items()
            if isinstance(value, dict)
        }

    result: dict[str, str] = {}
    updates: dict[str, dict] = {}
    cache_hits = 0
    computed = 0
    bytes_hashed = 0

    unique_paths: list[Path] = []
    seen: set[str] = set()
    for raw in paths:
        source = Path(raw)
        key = cache_key(source)
        if key in seen:
            continue
        seen.add(key)
        unique_paths.append(source)

    for source in unique_paths:
        if should_stop is not None and should_stop():
            break
        key = cache_key(source)
        before = _signature(source)
        if before is None:
            continue
        existing = entries_snapshot.get(key)
        if isinstance(existing, dict):
            digest = str(existing.get("sha256") or "")
            if (
                len(digest) == 64
                and int(existing.get("size", -1)) == before[0]
                and int(existing.get("mtime_ns", -1)) == before[1]
            ):
                result[key] = digest
                cache_hits += 1
                continue

        digest, read_bytes = _hash_file(source)
        bytes_hashed += read_bytes
        if not digest:
            continue
        after = _signature(source)
        if after is None or after != before:
            # Do not cache a digest for a file that changed while it was read.
            continue
        updates[key] = {
            "size": before[0],
            "mtime_ns": before[1],
            "sha256": digest,
        }
        result[key] = digest
        computed += 1

    if updates:
        with _LOCK:
            live_payload = _load_state(cache_path)
            live_entries = live_payload.setdefault("entries", {})
            live_entries.update(updates)
            _save_state(cache_path, live_payload)

    return result, {
        "paths": len(unique_paths),
        "cache_hits": cache_hits,
        "computed": computed,
        "bytes_hashed": bytes_hashed,
    }


def reset_hash_cache_state_for_tests() -> None:
    with _LOCK:
        _STATE.clear()
