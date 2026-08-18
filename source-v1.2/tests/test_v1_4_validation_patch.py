from __future__ import annotations

import importlib
import io
import unittest

from PIL import Image
import numpy as np

from fh6garage.livery_analysis import LIVERY_SECTION_NAMES
from fh6garage.livery_preview import preview_backend_available
from fh6garage.v1_4_validation_patch import (
    _overlay_validation_warning,
    compare_counts,
    composition_stats,
)


class V14ValidationPatchTests(unittest.TestCase):
    def test_compare_counts_detects_exact_section_mismatch(self) -> None:
        expected = {name: 0 for name in LIVERY_SECTION_NAMES}
        expected["Left"] = 12
        expected["Right"] = 7
        decoded = {name: tuple() for name in LIVERY_SECTION_NAMES}
        decoded["Left"] = tuple({"shape": index} for index in range(12))
        decoded["Right"] = tuple({"shape": index} for index in range(6))

        expected_total, decoded_total, mismatches = compare_counts(expected, decoded)

        self.assertEqual(expected_total, 19)
        self.assertEqual(decoded_total, 18)
        self.assertEqual(mismatches, [("Right", 7, 6)])

    def test_composition_stats_counts_vector_raster_shapes_and_masks(self) -> None:
        decoded = {name: tuple() for name in LIVERY_SECTION_NAMES}
        decoded["Left"] = (
            {"type_word": 101, "mask": False, "is_raster_logo": False},
            {"type_word": 101, "mask": True, "is_raster_logo": False},
            {"type_word": 127, "mask": False, "is_raster_logo": False},
        )
        decoded["Right"] = (
            {"type": 0x100000 + 127, "mask": False, "is_raster_logo": False},
            {"type_word": 0x8123, "mask": False, "is_raster_logo": True},
        )

        self.assertEqual(composition_stats(decoded), (4, 1, 3, 1))

    def test_warning_overlay_preserves_png_dimensions(self) -> None:
        source = Image.new("RGB", (640, 320), (30, 32, 38))
        buffer = io.BytesIO()
        source.save(buffer, format="PNG")

        output = _overlay_validation_warning(buffer.getvalue(), "recorded 10 / decoded 9")

        self.assertTrue(output.startswith(b"\x89PNG"))
        with Image.open(io.BytesIO(output)) as image:
            self.assertEqual(image.size, (640, 320))

    def test_numpy_runtime_dependency_is_available(self) -> None:
        values = np.array([1, 2, 3], dtype=np.float32)
        self.assertEqual(float(values.sum()), 6.0)

    def test_pinned_renderer_can_generate_png_with_native_asset(self) -> None:
        if not preview_backend_available():
            self.skipTest("Pinned KFPS vendor tree is not present in this source checkout")

        renderer = importlib.import_module("json_preview_renderer")
        png = renderer.render_typecode_layers_canvas(
            [
                {
                    "type": 1048677,
                    "type_word": 0x65,
                    "data": [0.0, 0.0, 2.0, 1.0, 0.0, 0.0, 0],
                    "color": [220, 90, 120, 255],
                    "mask": False,
                }
            ],
            width=640,
            height=320,
            strict_assets=True,
        )
        self.assertIsNotNone(png)
        self.assertTrue(png.startswith(b"\x89PNG"))

    def test_strict_renderer_rejects_missing_shape_instead_of_fallback(self) -> None:
        if not preview_backend_available():
            self.skipTest("Pinned KFPS vendor tree is not present in this source checkout")

        renderer = importlib.import_module("json_preview_renderer")
        with self.assertRaises(ValueError):
            renderer.render_typecode_layers_canvas(
                [
                    {
                        "type": 0x100000 + 0x7FFE,
                        "type_word": 0x7FFE,
                        "data": [0.0, 0.0, 2.0, 1.0, 0.0, 0.0, 0],
                        "color": [255, 255, 255, 255],
                        "mask": False,
                    }
                ],
                width=640,
                height=320,
                strict_assets=True,
            )


if __name__ == "__main__":
    unittest.main()
