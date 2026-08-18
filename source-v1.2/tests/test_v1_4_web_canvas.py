from __future__ import annotations

import unittest

from fh6garage.web_canvas_preview import _WEB_HTML, _canvas_matrix, _path_from_alpha_triangles


class _StubRenderer:
    @staticmethod
    def _transform_resource_polygon(points, data):
        return [(10.0 + 2.0 * x + 3.0 * y, 20.0 - 4.0 * x + 5.0 * y) for x, y in points]


class WebCanvasContractTests(unittest.TestCase):
    def test_matrix_is_derived_from_reference_transform(self):
        matrix = _canvas_matrix(_StubRenderer(), [0, 0, 1, 1], 2.0)
        self.assertEqual(matrix, [4.0, 8.0, 6.0, -10.0, 2068.0, 984.0])

    def test_native_triangles_become_one_browser_path(self):
        path = _path_from_alpha_triangles([
            ([(0, 0), (1, 0), (0, 1)], (255, 255, 255)),
            ([(1, 0), (1, 1), (0, 1)], (255, 255, 255)),
        ])
        self.assertEqual(path.count("M "), 2)
        self.assertEqual(path.count(" Z"), 2)

    def test_browser_contract_uses_canvas_antialias_and_ordered_mask_cutout(self):
        self.assertIn("new Path2D", _WEB_HTML)
        self.assertIn("imageSmoothingQuality = 'high'", _WEB_HTML)
        self.assertIn("'destination-out'", _WEB_HTML)
        self.assertIn("canvas.toBlob", _WEB_HTML)


if __name__ == "__main__":
    unittest.main()
