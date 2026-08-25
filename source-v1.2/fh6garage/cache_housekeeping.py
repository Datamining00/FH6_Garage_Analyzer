from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class CacheCleanupStats:
    removed_files: int = 0
    removed_bytes: int = 0

    def __add__(self, other: CacheCleanupStats) -> CacheCleanupStats:
        return CacheCleanupStats(
            removed_files=self.removed_files + other.removed_files,
            removed_bytes=self.removed_bytes + other.removed_bytes,
        )

    def as_dict(self) -> dict[str, int]:
        return {
            "cache_cleanup_removed_files": self.removed_files,
            "cache_cleanup_removed_bytes": self.removed_bytes,
        }


def _unlink(path: Path) -> CacheCleanupStats:
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    try:
        path.unlink()
    except OSError:
        return CacheCleanupStats()
    return CacheCleanupStats(1, max(0, int(size)))


def cleanup_stale_temp_files(
    directory: Path,
    *,
    older_than_seconds: float = 24 * 60 * 60,
    recursive: bool = False,
) -> CacheCleanupStats:
    """Remove only old ``*.tmp`` files from one application-owned directory.

    A one-day grace period avoids interfering with a second running instance.
    Errors are deliberately ignored because cache maintenance must never block
    save scanning or application startup.
    """

    root = Path(directory)
    if not root.is_dir():
        return CacheCleanupStats()
    now = time.time()
    pattern = "**/*.tmp" if recursive else "*.tmp"
    result = CacheCleanupStats()
    try:
        candidates = list(root.glob(pattern))
    except OSError:
        return result
    for path in candidates:
        if not path.is_file():
            continue
        try:
            age = now - path.stat().st_mtime
        except OSError:
            continue
        if age >= older_than_seconds:
            result += _unlink(path)
    return result


def prune_scan_cache_namespaces(
    directory: Path,
    *,
    active_path: Path,
    max_namespaces: int = 5,
    max_age_days: int = 30,
) -> CacheCleanupStats:
    """Bound per-save scan-cache JSON files without touching the active cache."""

    root = Path(directory)
    active = Path(active_path)
    if not root.is_dir():
        return CacheCleanupStats()

    now = time.time()
    max_age_seconds = max(1, int(max_age_days)) * 24 * 60 * 60
    try:
        files = [
            item
            for item in root.glob("*.json")
            if item.is_file() and item != active
        ]
    except OSError:
        return CacheCleanupStats()

    result = CacheCleanupStats()
    survivors: list[tuple[float, Path]] = []
    for path in files:
        try:
            modified = float(path.stat().st_mtime)
        except OSError:
            continue
        if now - modified >= max_age_seconds:
            result += _unlink(path)
        else:
            survivors.append((modified, path))

    # The active namespace is one of the retained slots.
    other_slots = max(0, int(max_namespaces) - 1)
    survivors.sort(key=lambda item: item[0], reverse=True)
    for _modified, path in survivors[other_slots:]:
        result += _unlink(path)
    return result
