from __future__ import annotations

import io
import unittest
from pathlib import Path

from PIL import Image

from fh6garage.livery_preview_preview2 import (
    DEFAULT_QUALITY,
    QUALITY_DIMENSIONS,
    _cache_key,
    _resize_to_exact_atlas,
    normalize_quality,
)


ROOT = Path(__file__).resolve().parents[1]


class V14Preview2Tests(unittest.TestCase):
    def test_quality_levels_are_distinct_and_balanced_is_default(self) -> None:
        self.assertEqual(DEFAULT_QUALITY, "balanced")
        self.assertEqual(QUALITY_DIMENSIONS["fast"], (2048, 1024))
        self.assertEqual(QUALITY_DIMENSIONS["balanced"], (3072, 1536))
        self.assertEqual(QUALITY_DIMENSIONS["high"], (4096, 2048))
        self.assertEqual(normalize_quality("unknown"), "balanced")

    def test_supersampled_canvas_downsamples_to_exact_projection_size(self) -> None:
        image = Image.new("RGBA", QUALITY_DIMENSIONS["balanced"], (10, 20, 30, 255))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        output = _resize_to_exact_atlas(buffer.getvalue(), "balanced")
        with Image.open(io.BytesIO(output)) as decoded:
            self.assertEqual(decoded.size, (2048, 1024))

    def test_disk_cache_key_is_quality_specific(self) -> None:
        args = ("C:/sample/C_livery", 1234, 5678, "Left", "D:/FH6/Content")
        self.assertNotEqual(
            _cache_key(*args, "fast"),
            _cache_key(*args, "high"),
        )

    def test_preview2_name_does_not_replace_final_release_metadata(self) -> None:
        preview = (ROOT / "version_info_preview2.txt").read_text(encoding="utf-8")
        final = (ROOT / "version_info.txt").read_text(encoding="utf-8")
        spec = (ROOT / "FH6_Assistant_v1.4_preview2.spec").read_text(encoding="utf-8")
        self.assertIn("FH6 Assistant v1.4 Preview 2.exe", preview)
        self.assertIn("name='FH6 Assistant v1.4 Preview 2'", spec)
        self.assertIn("FH6 Assistant v1.4.exe", final)
        self.assertNotIn("Preview 2", final)


if __name__ == "__main__":
    unittest.main()
