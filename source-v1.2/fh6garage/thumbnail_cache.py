from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap


@dataclass(slots=True)
class _PixmapEntry:
    pixmap: QPixmap
    cost_bytes: int


def _path_identity(path: Any) -> tuple[str, int, int] | None:
    if path is None:
        return None
    try:
        candidate = Path(path)
        stat = candidate.stat()
    except (OSError, TypeError, ValueError):
        return None
    if not candidate.is_file():
        return None
    return (
        str(candidate).casefold(),
        int(stat.st_size),
        int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))),
    )


def _pixmap_cost(pixmap: QPixmap) -> int:
    if pixmap.isNull():
        return 0
    depth = max(1, int(pixmap.depth()))
    return max(1, int(pixmap.width()) * int(pixmap.height()) * depth // 8)


class ThumbnailPixmapCache:
    """A GUI-thread, decoded-byte-bounded LRU for saved-content thumbnails."""

    def __init__(self, max_bytes: int, *, max_edge: int = 1280) -> None:
        self.max_bytes = max(1, int(max_bytes))
        self.max_edge = max(64, int(max_edge))
        self._entries: OrderedDict[tuple[str, int, int], _PixmapEntry] = OrderedDict()
        self._key_by_path: dict[str, tuple[str, int, int]] = {}
        self.current_bytes = 0
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    def _remove_key(self, key: tuple[str, int, int]) -> None:
        entry = self._entries.pop(key, None)
        if entry is None:
            return
        self.current_bytes = max(0, self.current_bytes - entry.cost_bytes)
        if self._key_by_path.get(key[0]) == key:
            self._key_by_path.pop(key[0], None)

    def get(self, path: Any) -> QPixmap | None:
        key = _path_identity(path)
        if key is None:
            self.misses += 1
            return None

        previous = self._key_by_path.get(key[0])
        if previous is not None and previous != key:
            self._remove_key(previous)

        entry = self._entries.pop(key, None)
        if entry is None:
            self.misses += 1
            return None
        self._entries[key] = entry
        self.hits += 1
        # QPixmap is implicitly shared; this does not eagerly duplicate pixels.
        return QPixmap(entry.pixmap)

    def put(self, path: Any, pixmap: QPixmap) -> None:
        key = _path_identity(path)
        if key is None or pixmap.isNull():
            return

        previous = self._key_by_path.get(key[0])
        if previous is not None:
            self._remove_key(previous)

        stored = QPixmap(pixmap)
        cost = _pixmap_cost(stored)
        if cost <= 0 or cost > self.max_bytes:
            return

        self._entries[key] = _PixmapEntry(stored, cost)
        self._key_by_path[key[0]] = key
        self.current_bytes += cost
        while self.current_bytes > self.max_bytes and self._entries:
            oldest_key, oldest = self._entries.popitem(last=False)
            self.current_bytes = max(0, self.current_bytes - oldest.cost_bytes)
            if self._key_by_path.get(oldest_key[0]) == oldest_key:
                self._key_by_path.pop(oldest_key[0], None)
            self.evictions += 1

    def get_or_load(self, path: Any) -> QPixmap:
        cached = self.get(path)
        if cached is not None:
            return cached

        identity = _path_identity(path)
        if identity is None:
            return QPixmap()
        pixmap = QPixmap(str(Path(path)))
        if pixmap.isNull():
            return QPixmap()
        if max(pixmap.width(), pixmap.height()) > self.max_edge:
            pixmap = pixmap.scaled(
                self.max_edge,
                self.max_edge,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        self.put(path, pixmap)
        return pixmap

    def clear(self) -> None:
        self._entries.clear()
        self._key_by_path.clear()
        self.current_bytes = 0

    def stats(self) -> dict[str, int]:
        return {
            "thumbnail_lru_entries": len(self._entries),
            "thumbnail_lru_bytes": self.current_bytes,
            "thumbnail_lru_limit_bytes": self.max_bytes,
            "thumbnail_lru_hits": self.hits,
            "thumbnail_lru_misses": self.misses,
            "thumbnail_lru_evictions": self.evictions,
        }
