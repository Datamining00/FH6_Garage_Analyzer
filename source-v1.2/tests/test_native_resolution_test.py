from __future__ import annotations

import io
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from fh6garage.livery_preview_native_resolution_test import (
    _checkerboard_native_resolution,
    _projection_native_resolution,
    normalize_quality,
    quality_scale,
)


class NativeResolutionSettingsTests(unittest.TestCase):
    def test_quality_mapping_uses_retained_output_scales(self) -> None:
        self.assertEqual(quality_scale("fast"), 1)
        self.assertEqual(quality_scale("balanced"), 2)
        self.assertEqual(quality_scale("high"), 4)
        self.assertEqual(normalize_quality("unknown"), "high")

    def test_checkerboard_keeps_native_resolution(self) -> None:
        image = Image.new("RGBA", (800, 400), (255, 255, 255, 255))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        output = _checkerboard_native_resolution(buffer.getvalue(), 4)
        with Image.open(io.BytesIO(output)) as result:
            self.assertEqual(result.size, (800, 400))


class _FakeRenderContract:
    ATLAS_SIZE = (8, 4)

    @staticmethod
    def _projection_pixel_bounds(_projection):
        return (1, 1, 7, 3)

    @staticmethod
    def _atlas_to_local_affine(_slot, _width, _height, _xorigin, _yorigin):
        return (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)

    @staticmethod
    def _masked_atlas_layer(artwork, mask, _slot, _projection):
        from PIL import ImageChops

        result = artwork.copy()
        result.putalpha(ImageChops.multiply(result.getchannel("A"), mask.convert("L")))
        return result


class NativeResolutionProjectionTests(unittest.TestCase):
    def _png(self, size):
        image = Image.new("RGBA", size, (255, 0, 0, 255))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    @mock.patch("fh6garage.livery_preview_native_resolution_test._projection_record")
    def test_four_x_projection_crop_is_not_downsampled(self, projection_record) -> None:
        base_mask = Image.new("L", (8, 4), 255)
        projection_record.return_value = (
            _FakeRenderContract,
            "left",
            base_mask,
            {"xorigin": 0.0, "yorigin": 0.0},
            "hash",
        )
        output = _projection_native_resolution(
            self._png((32, 16)),
            "Left",
            3650,
            game_folder=Path("."),
            scale=4,
        )
        with Image.open(io.BytesIO(output)) as result:
            # Base crop is 6x2; retained 4x density must therefore be 24x8.
            self.assertEqual(result.size, (24, 8))


if __name__ == "__main__":
    unittest.main()
