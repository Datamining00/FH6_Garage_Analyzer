from __future__ import annotations

import io
import unittest

from PIL import Image, ImageDraw

from fh6garage.livery_preview import _checkerboard_preview, _expanded_crop_box


class LiveryPreviewCropTests(unittest.TestCase):
    def test_small_artwork_is_kept_with_minimum_context(self) -> None:
        source = Image.new("RGBA", (2048, 1024), (0, 0, 0, 0))
        draw = ImageDraw.Draw(source)
        draw.rectangle((999, 392, 1051, 427), fill=(255, 180, 200, 255))
        buffer = io.BytesIO()
        source.save(buffer, format="PNG")

        output = _checkerboard_preview(buffer.getvalue())
        with Image.open(io.BytesIO(output)) as image:
            self.assertEqual(image.size, (480, 240))

    def test_full_width_artwork_only_crops_vertical_margin(self) -> None:
        source = Image.new("RGBA", (2048, 1024), (0, 0, 0, 0))
        draw = ImageDraw.Draw(source)
        draw.rectangle((0, 365, 2047, 712), fill=(0, 200, 215, 255))
        buffer = io.BytesIO()
        source.save(buffer, format="PNG")

        output = _checkerboard_preview(buffer.getvalue())
        with Image.open(io.BytesIO(output)) as image:
            self.assertEqual(image.width, 2048)
            self.assertLess(image.height, 1024)
            self.assertGreaterEqual(image.height, 240)

    def test_crop_box_stays_inside_canvas(self) -> None:
        crop = _expanded_crop_box((0, 0, 40, 30), (2048, 1024))
        self.assertEqual(crop[0], 0)
        self.assertEqual(crop[1], 0)
        self.assertEqual(crop[2] - crop[0], 480)
        self.assertEqual(crop[3] - crop[1], 240)


if __name__ == "__main__":
    unittest.main()
