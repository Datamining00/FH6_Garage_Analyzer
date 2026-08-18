from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from fh6garage.livery_preview import (
    _validate_exact_assets_and_filter_noops,
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
    last_raster_resolver = None
    last_strict_assets = None
    last_layer_count = None

    @staticmethod
    def _resolve_vinyl_resource(type_code, layer=None):
        if int(type_code) == 999999:
            return None
        return ("Primitives", max(1, int(type_code) - 1048676))

    @staticmethod
    def _resource_alpha_triangles(family, index):
        if family != "Primitives":
            return None
        alpha = (0, 0, 0) if int(index) == 3 else (255, 255, 255)
        return [([(-1.0, -1.0), (1.0, -1.0), (0.0, 1.0)], alpha)]

    @staticmethod
    def _shape_word_from_shape(layer, type_code):
        return int(type_code) & 0xFFFF

    @staticmethod
    def render_typecode_layers_canvas(
        layers,
        width=2048,
        height=1024,
        raster_resolver=None,
        strict_assets=False,
    ):
        _FakeRenderer.last_raster_resolver = raster_resolver
        _FakeRenderer.last_strict_assets = strict_assets
        _FakeRenderer.last_layer_count = len(layers)
        image = Image.new("RGBA", (64, 32), (0, 0, 0, 0))
        for index, _layer in enumerate(layers):
            for x in range(8 + index * 8, 24 + index * 8):
                for y in range(8, 24):
                    image.putpixel((x, y), (255, 0, 0, 255))
        import io

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()


class _FakeRasterResolver:
    def __call__(self, raster_id):
        if int(raster_id) != 123:
            return None
        return Image.new("RGBA", (8, 8), (255, 255, 255, 255))


class LiveryPreviewTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_livery_preview_cache()
        _FakeRenderer.last_raster_resolver = None
        _FakeRenderer.last_strict_assets = None
        _FakeRenderer.last_layer_count = None

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

    def test_zero_native_opacity_is_a_safe_noop_not_a_missing_asset(self) -> None:
        visible_layer = {
            "type": 1048677,
            "color": [255, 255, 255, 255],
        }
        transparent_native_layer = {
            "type": 1048679,
            "color": [255, 255, 255, 255],
        }
        prepared, invisible_count = _validate_exact_assets_and_filter_noops(
            _FakeRenderer,
            [visible_layer, transparent_native_layer],
            None,
        )
        self.assertEqual(prepared, [visible_layer])
        self.assertEqual(invisible_count, 1)

    def test_missing_native_asset_still_fails_closed(self) -> None:
        with self.assertRaisesRegex(Exception, "native FH6"):
            _validate_exact_assets_and_filter_noops(
                _FakeRenderer,
                [{"type": 999999, "color": [255, 255, 255, 255]}],
                None,
            )

    def test_render_section_requires_native_assets_and_exact_vehicle_projection(self) -> None:
        raster_resolver = _FakeRasterResolver()

        def identity_projection(png_bytes, section, car_id, game_folder=None):
            self.assertEqual(section, "Left")
            self.assertEqual(car_id, 3650)
            return png_bytes

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "C_livery"
            source.write_bytes(b"test")
            with patch(
                "fh6garage.livery_preview._load_backend",
                return_value=(_FakeDecoder, _FakeRenderer),
            ), patch(
                "fh6garage.livery_preview.analyze_livery_file",
                return_value=SimpleNamespace(car_id=3650),
            ), patch(
                "fh6garage.livery_preview.require_fh6_game_folder",
                return_value=Path(temp_dir),
            ), patch(
                "fh6garage.livery_preview.raster_resolver_for_game",
                return_value=raster_resolver,
            ), patch(
                "fh6garage.livery_preview.apply_exact_vehicle_projection",
                side_effect=identity_projection,
            ):
                result = render_livery_section(source, "Left")

        self.assertEqual(result.placement_count, 2)
        self.assertEqual(result.skipped_raster_logos, 0)
        self.assertTrue(result.png_bytes.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertIs(_FakeRenderer.last_raster_resolver, raster_resolver)
        self.assertFalse(_FakeRenderer.last_strict_assets)
        self.assertEqual(_FakeRenderer.last_layer_count, 2)


if __name__ == "__main__":
    unittest.main()
