from __future__ import annotations

import unittest

from PIL import Image

from fh6garage.livery_preview import LiveryPreviewError
from fh6garage.livery_raster_runtime_patch import _prepare_layers


class _Renderer:
    @staticmethod
    def _shape_mask_flag(layer, data):
        return bool(layer.get("mask"))

    @staticmethod
    def _resolve_vinyl_resource(type_code, layer=None):
        return ("Primitives", 1)

    @staticmethod
    def _resource_alpha_triangles(family, index):
        return [([(-1.0, -1.0), (1.0, -1.0), (0.0, 1.0)], (255, 255, 255))]

    @staticmethod
    def _shape_word_from_shape(layer, type_code):
        return int(type_code) & 0xFFFF


class _Resolver:
    def __init__(self, available=()):
        self.available = {int(value) for value in available}

    def __call__(self, raster_id):
        if int(raster_id) in self.available:
            return Image.new("RGBA", (4, 4), (255, 255, 255, 255))
        return None


class RasterRuntimePatchTests(unittest.TestCase):
    def test_missing_visible_raster_is_removed_before_exact_asset_validation(self) -> None:
        visible_vector = {"type": 1048677, "data": [0, 0, 1, 1, 0, 0, 0], "color": [255, 255, 255, 255]}
        missing_raster = {
            "type": 1048677,
            "data": [0, 0, 1, 1, 0, 0, 0],
            "color": [255, 255, 255, 255],
            "is_raster_logo": True,
            "raster_id": 3005,
        }
        prepared, invisible, missing = _prepare_layers(
            _Renderer,
            [visible_vector, missing_raster],
            _Resolver(),
        )
        self.assertEqual(prepared, [visible_vector])
        self.assertEqual(invisible, 0)
        self.assertEqual(missing, (3005,))

    def test_missing_raster_mask_remains_fatal(self) -> None:
        missing_mask = {
            "type": 1048677,
            "data": [0, 0, 1, 1, 0, 0, 1],
            "color": [255, 255, 255, 255],
            "mask": True,
            "is_raster_logo": True,
            "raster_id": 3005,
        }
        with self.assertRaises(LiveryPreviewError):
            _prepare_layers(_Renderer, [missing_mask], _Resolver())

    def test_available_raster_is_kept(self) -> None:
        layer = {
            "type": 1048677,
            "data": [0, 0, 1, 1, 0, 0, 0],
            "color": [255, 255, 255, 255],
            "is_raster_logo": True,
            "raster_id": 50,
        }
        prepared, invisible, missing = _prepare_layers(
            _Renderer,
            [layer],
            _Resolver((50,)),
        )
        self.assertEqual(prepared, [layer])
        self.assertEqual(invisible, 0)
        self.assertEqual(missing, ())


if __name__ == "__main__":
    unittest.main()
