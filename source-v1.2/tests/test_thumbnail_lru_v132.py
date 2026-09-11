from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication

from fh6garage.thumbnail_cache import ThumbnailPixmapCache


class ThumbnailLruTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def _image(path: Path, width: int, height: int, color: str) -> None:
        pixmap = QPixmap(width, height)
        pixmap.fill(QColor(color))
        if not pixmap.save(str(path), "PNG"):
            raise AssertionError("failed to create test image")

    def test_second_load_is_an_lru_hit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "thumb.png"
            self._image(path, 100, 100, "red")
            cache = ThumbnailPixmapCache(1024 * 1024)

            first = cache.get_or_load(path)
            second = cache.get_or_load(path)

            self.assertFalse(first.isNull())
            self.assertFalse(second.isNull())
            self.assertEqual(cache.stats()["thumbnail_lru_hits"], 1)
            self.assertEqual(cache.stats()["thumbnail_lru_misses"], 1)

    def test_decoded_byte_limit_evicts_oldest_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first_path = Path(tmp) / "first.png"
            second_path = Path(tmp) / "second.png"
            self._image(first_path, 100, 100, "red")
            self._image(second_path, 100, 100, "blue")
            cache = ThumbnailPixmapCache(50_000)

            cache.get_or_load(first_path)
            cache.get_or_load(second_path)

            stats = cache.stats()
            self.assertLessEqual(
                stats["thumbnail_lru_bytes"],
                stats["thumbnail_lru_limit_bytes"],
            )
            self.assertEqual(stats["thumbnail_lru_entries"], 1)
            self.assertEqual(stats["thumbnail_lru_evictions"], 1)

    def test_file_change_invalidates_same_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "thumb.png"
            self._image(path, 100, 100, "red")
            cache = ThumbnailPixmapCache(1024 * 1024)
            first = cache.get_or_load(path)

            self._image(path, 80, 60, "green")
            os.utime(path, None)
            second = cache.get_or_load(path)

            self.assertEqual((first.width(), first.height()), (100, 100))
            self.assertEqual((second.width(), second.height()), (80, 60))
            self.assertEqual(cache.stats()["thumbnail_lru_entries"], 1)
            self.assertEqual(cache.stats()["thumbnail_lru_misses"], 2)

    def test_large_source_is_scaled_before_caching(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "large.png"
            self._image(path, 1600, 800, "black")
            cache = ThumbnailPixmapCache(16 * 1024 * 1024, max_edge=800)

            pixmap = cache.get_or_load(path)

            self.assertEqual((pixmap.width(), pixmap.height()), (800, 400))
            self.assertLessEqual(cache.current_bytes, cache.max_bytes)


if __name__ == "__main__":
    unittest.main()
