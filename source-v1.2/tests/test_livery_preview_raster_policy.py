from __future__ import annotations

import unittest

from PySide6.QtGui import QImage

from fh6garage.livery_preview import LiveryPreviewError
from fh6garage.livery_preview_raster_policy import (
    filter_missing_visible_rasters,
    preflight_raster_layers_fail_soft,
)
from fh6garage.livery_preview_ui_state import (
    SECTION_DISPLAY_ROTATION_DEGREES,
    rotate_section_image,
)


class _Renderer:
    @staticmethod
    def _shape_mask_flag(layer, data):
        return bool(layer.get("mask"))


class _Resolver:
    def __init__(self, available=()):
        self.available = set(int(v) for v in available)

    def __call__(self, raster_id):
        return object() if int(raster_id) in self.available else None

    def missing_description(self, raster_id):
        return f"missing {int(raster_id)}"


class RasterPolicyTests(unittest.TestCase):
    def test_missing_visible_raster_is_skipped_not_fatal(self) -> None:
        layers = [
            {"is_raster_logo": True, "raster_id": 3005, "data": [0, 0, 1, 1], "mask": False},
            {"type": 123, "data": [0, 0, 1, 1], "color": [255, 255, 255, 255]},
        ]
        resolver = _Resolver()
        preflight_raster_layers_fail_soft(_Renderer(), layers, resolver)
        kept, missing = filter_missing_visible_rasters(_Renderer(), layers, resolver)
        self.assertEqual(missing, (3005,))
        self.assertEqual(len(kept), 1)
        self.assertFalse(kept[0].get("is_raster_logo", False))

    def test_missing_raster_mask_still_fails_closed(self) -> None:
        layers = [
            {"is_raster_logo": True, "raster_id": 3005, "data": [0, 0, 1, 1], "mask": True},
        ]
        with self.assertRaises(LiveryPreviewError):
            preflight_raster_layers_fail_soft(_Renderer(), layers, _Resolver())

    def test_available_raster_is_preserved(self) -> None:
        layers = [
            {"is_raster_logo": True, "raster_id": 3005, "data": [0, 0, 1, 1], "mask": False},
        ]
        kept, missing = filter_missing_visible_rasters(_Renderer(), layers, _Resolver({3005}))
        self.assertEqual(missing, ())
        self.assertEqual(kept, layers)


class DisplayRotationTests(unittest.TestCase):
    def test_spoiler_rotates_left_ninety_degrees(self) -> None:
        self.assertEqual(SECTION_DISPLAY_ROTATION_DEGREES["Spoiler"], -90)
        source = QImage(7, 3, QImage.Format.Format_ARGB32)
        rotated = rotate_section_image(source, "Spoiler")
        self.assertEqual((rotated.width(), rotated.height()), (3, 7))


if __name__ == "__main__":
    unittest.main()
