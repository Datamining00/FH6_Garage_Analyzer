from __future__ import annotations

import unittest

from fh6garage.preview3d import tire_morph_geometry as geometry


class TireMorphGeometryWireTagTests(unittest.TestCase):
    def test_forzatech_vertex_wire_tag_ids_match_native_ascii_ids(self) -> None:
        # These literals are intentionally independent of the synthetic bundle
        # builder. tire_slick.modelbin contains VLay=0x564C6179 and
        # VerB=0x56657242; ILay follows the same ASCII integer convention.
        self.assertEqual(geometry.VERTEX_BUFFER_TAG, 0x56657242)
        self.assertEqual(geometry.VERTEX_LAYOUT_TAG, 0x564C6179)
        self.assertEqual(geometry.INPUT_LAYOUT_TAG, 0x494C6179)
        self.assertEqual(geometry.INDEX_BUFFER_TAG, 0x496E6442)

    def test_public_geometry_functions_are_reexported_from_corrected_impl(self) -> None:
        self.assertTrue(callable(geometry.bake_modelbin_selector_geometry))
        self.assertTrue(callable(geometry.bake_tire_morph_selectors))
        self.assertTrue(callable(geometry._glb_bytes))


if __name__ == "__main__":
    unittest.main()
