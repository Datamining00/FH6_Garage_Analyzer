from __future__ import annotations

import io
import unittest

from PIL import Image
import numpy as np

from fh6garage.livery_analysis import LIVERY_SECTION_NAMES
from fh6garage.v1_4_validation_patch import _overlay_validation_warning, compare_counts


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


if __name__ == "__main__":
    unittest.main()
