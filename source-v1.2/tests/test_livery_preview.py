from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from fh6garage.livery_preview import (
    clear_livery_preview_cache,
    decode_livery_preview,
    render_livery_section,
)


class _FakeDecoder:
    LIVERY_SECTION_NAMES = (
        "Front",
        "Back",
        "Top",
        "Left",
        "Right",
        "Spoiler",
        "FrontWindshield",
        "BackWindshield",
        "TopWindow",
        "LeftWindow",
        "RightWindow",
    )

    @staticmethod
    def decode_forza_source(path, allow_locked=False, game=None):
        return SimpleNamespace(
            layers=[
                {
                    "source_section": "Left",
                    "type": 1048677,
                    "data": [0, 0, 1, 1, 0, 0, 0],
                    "color": [255, 0, 0, 255],
                },
                {
                    "source_section": "Left",
                    "type": 1048678,
                    "data": [100, 50, 1, 1, 0, 0, 0],
                    "color": [0, 255, 0, 255],
                    "is_raster_logo": True,
                    "raster_id": 123,
                },
                {
                    "source_section": "Top",
                    "type": 1048677,
                    "data": [0, 0, 1, 1, 0, 0, 0],
                    "color": [0, 0, 255, 255],
                },
            ],
            report={"warnings": ["sample warning"]},
        )


class _FakeRenderer:
    @staticmethod
    def render_typecode_layers_canvas(layers, width=2048, height=1024, strict_assets=False):
        image = Image.new("RGBA", (64, 32), (0, 0, 0, 0))
        for index, layer in enumerate(layers):
            if layer.get("is_raster_logo"):
                continue
            for x in range(8 + index * 8, 24 + index * 8):
                for y in range(8, 24):
                    image.putpixel((x, y), (255, 0, 0, 255))
        import io

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()


class LiveryPreviewTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_livery_preview_cache()

    def test_decode_groups_layers_by_section(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "C_livery"
            source.write_bytes(b"test")
            with patch(
                "fh6garage.livery_preview._load_backend",
                return_value=(_FakeDecoder, _FakeRenderer),
            ):
                decoded = decode_livery_preview(source)
        self.assertEqual(decoded.total_layers, 3)
        self.assertEqual(len(decoded.sections["Left"]), 2)
        self.assertEqual(len(decoded.sections["Top"]), 1)
        self.assertEqual(decoded.raster_logo_count, 1)
        self.assertIn("sample warning", decoded.warnings)

    def test_render_section_returns_visible_png_and_raster_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "C_livery"
            source.write_bytes(b"test")
            with patch(
                "fh6garage.livery_preview._load_backend",
                return_value=(_FakeDecoder, _FakeRenderer),
            ):
                result = render_livery_section(source, "Left")

        self.assertEqual(result.placement_count, 2)
        self.assertEqual(result.skipped_raster_logos, 1)
        self.assertTrue(result.png_bytes.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertTrue(any("래스터 로고 1개" in warning for warning in result.warnings))


if __name__ == "__main__":
    unittest.main()
