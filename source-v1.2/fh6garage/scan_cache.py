from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from .cache_housekeeping import (
    CacheCleanupStats,
    cleanup_stale_temp_files,
    prune_scan_cache_namespaces,
)
from .models import HeaderInfo
from .performance_metrics import app_data_dir

_CACHE_SCHEMA = 1
# Bump this whenever parse_forza_header semantics change, even if the on-disk
# cache layout itself is unchanged. This prevents stale parsed metadata from
# surviving an application/parser upgrade.
_HEADER_PARSER_REVISION = 3


def _fingerprint(path: Path) -> tuple[int, int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return (
        int(stat.st_size),
        int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))),
        int(getattr(stat, "st_ctime_ns", int(stat.st_ctime * 1_000_000_000))),
    )


def _header_to_dict(header: HeaderInfo) -> dict[str, Any]:
    return {
        "version": header.version,
        "name": header.name,
        "description": header.description,
        "creator": header.creator,
        "created": header.created,
        "car_id": header.car_id,
        "guid": header.guid,
        "decal_count": header.decal_count,
        "platform_code": header.platform_code,
        "asset_guid": header.asset_guid,
        "type_value": header.type_value,
    }


def _header_from_dict(value: dict[str, Any]) -> HeaderInfo:
    return HeaderInfo(
        version=int(value.get("version", 0) or 0),
        name=str(value.get("name", "") or ""),
        description=str(value.get("description", "") or ""),
        creator=str(value.get("creator", "") or ""),
        created=str(value.get("created", "") or ""),
        car_id=(int(value["car_id"]) if value.get("car_id") is not None else None),
        guid=str(value.get("guid", "") or ""),
        decal_count=(
            int(value["decal_count"]) if value.get("decal_count") is not None else None
        ),
        platform_code=(
            int(value["platform_code"]) if value.get("platform_code") is not None else None
        ),
        asset_guid=str(value.get("asset_guid", "") or ""),
        type_value=(
            int(value["type_value"]) if value.get("type_value") is not None else None
        ),
    )


class FileAnalysisCache:
    """Persistent parsed-header/SHA cache keyed by strong filesystem fingerprint.

    The cache lives in LocalAppData and never writes to FH6 save content. The
    `(size, mtime_ns, ctime_ns)` fingerprint makes normal save replacement or
    editing invalidate the cached value automatically.
    """

    def __init__(self, save_root: Path, *, base_dir: Path | None = None) -> None:
        root_text = str(Path(save_root)).casefold().encode("utf-8", errors="surrogatepass")
        namespace = hashlib.sha256(root_text).hexdigest()[:20]
        directory = base_dir or (app_data_dir() / "scan_cache")
        self.path = directory / f"{namespace}.json"
        self._lock = threading.RLock()
        self._entries: dict[str, dict[str, Any]] = {}
        self.header_hits = 0
        self.header_misses = 0
        self.hash_hits = 0
        self.hash_misses = 0
        self.cleanup_stats = CacheCleanupStats()
        self._load()

    @staticmethod
    def _key(kind: str, path: Path) -> str:
        return f"{kind}:{str(path).casefold()}"

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return
        if (
            not isinstance(raw, dict)
            or raw.get("schema") != _CACHE_SCHEMA
            or raw.get("header_parser_revision") != _HEADER_PARSER_REVISION
        ):
            return
        entries = raw.get("entries")
        if isinstance(entries, dict):
            self._entries = {
                str(key): value
                for key, value in entries.items()
                if isinstance(value, dict)
            }

    def get_header(self, path: Path, kind: str) -> HeaderInfo | None:
        fp = _fingerprint(path)
        key = self._key(f"header:{kind}", path)
        with self._lock:
            entry = self._entries.get(key)
            if (
                fp is not None
                and isinstance(entry, dict)
                and tuple(entry.get("fingerprint", ())) == fp
                and isinstance(entry.get("value"), dict)
            ):
                try:
                    header = _header_from_dict(entry["value"])
                except (TypeError, ValueError, KeyError):
                    header = None
                if header is not None:
                    self.header_hits += 1
                    return header
            self.header_misses += 1
            return None

    def put_header(self, path: Path, kind: str, header: HeaderInfo) -> None:
        fp = _fingerprint(path)
        if fp is None:
            return
        key = self._key(f"header:{kind}", path)
        with self._lock:
            self._entries[key] = {
                "fingerprint": list(fp),
                "value": _header_to_dict(header),
            }

    def get_sha256(self, path: Path) -> str | None:
        fp = _fingerprint(path)
        key = self._key("sha256", path)
        with self._lock:
            entry = self._entries.get(key)
            if (
                fp is not None
                and isinstance(entry, dict)
                and tuple(entry.get("fingerprint", ())) == fp
                and isinstance(entry.get("value"), str)
                and len(entry["value"]) == 64
            ):
                self.hash_hits += 1
                return str(entry["value"])
            self.hash_misses += 1
            return None

    def put_sha256(self, path: Path, digest: str) -> None:
        fp = _fingerprint(path)
        if fp is None or len(digest) != 64:
            return
        key = self._key("sha256", path)
        with self._lock:
            self._entries[key] = {
                "fingerprint": list(fp),
                "value": digest,
            }

    def prune_to_paths(self, active_paths: set[Path]) -> None:
        active = {str(path).casefold() for path in active_paths}

        def entry_path(key: str) -> str:
            if key.startswith("header:"):
                parts = key.split(":", 2)
                return parts[2] if len(parts) == 3 else ""
            if key.startswith("sha256:"):
                return key[len("sha256:"):]
            return ""

        with self._lock:
            stale = [key for key in self._entries if entry_path(key) not in active]
            for key in stale:
                self._entries.pop(key, None)

    def save(self) -> None:
        temporary: Path | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "schema": _CACHE_SCHEMA,
                "header_parser_revision": _HEADER_PARSER_REVISION,
                "entries": self._entries,
            }
            fd, temporary_name = tempfile.mkstemp(
                prefix=f"{self.path.stem}.",
                suffix=".tmp",
                dir=str(self.path.parent),
            )
            os.close(fd)
            temporary = Path(temporary_name)
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )
            os.replace(temporary, self.path)
        except (OSError, TypeError, ValueError):
            return
        finally:
            if temporary is not None and temporary.exists():
                try:
                    temporary.unlink()
                except OSError:
                    pass
        self.cleanup_stats += cleanup_stale_temp_files(self.path.parent)
        self.cleanup_stats += prune_scan_cache_namespaces(
            self.path.parent,
            active_path=self.path,
        )

    def stats(self) -> dict[str, int]:
        result = {
            "header_cache_hits": self.header_hits,
            "header_cache_misses": self.header_misses,
            "hash_cache_hits": self.hash_hits,
            "hash_cache_misses": self.hash_misses,
            "scan_cache_entries": len(self._entries),
        }
        result.update(self.cleanup_stats.as_dict())
        try:
            result["scan_cache_bytes"] = int(self.path.stat().st_size)
        except OSError:
            result["scan_cache_bytes"] = 0
        return result
