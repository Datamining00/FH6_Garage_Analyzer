from __future__ import annotations

import unittest
from pathlib import Path

from fh6garage import livery_simple_layer_native_debug_v3 as v3


class SimpleLayerNativeDebugV3Tests(unittest.TestCase):
    def test_body_relative_source_offset_resolves_actual_shape_record(self):
        gyvl = 11
        body_base = gyvl + 0x15
        relative = 37
        payload = bytearray(b"\x7f" * 200)
        payload[gyvl : gyvl + 4] = b"gyvl"
        absolute = body_base + relative
        payload[absolute : absolute + 4] = b"\x02\x00\x01\x00"

        location = v3._locate_source_record_in_payload(bytes(payload), relative, 0x0100)

        self.assertIsNotNone(location)
        self.assertEqual(location["layer_data_base"], body_base)
        self.assertEqual(location["expected_absolute_offset"], absolute)
        self.assertEqual(location["matched_absolute_offset"], absolute)
        self.assertEqual(location["matched_shape_word"], 0x0100)
        self.assertTrue(location["matched"])

    def test_opposite_side_similarity_prefers_mirrored_transform(self):
        target = {"data": [20.0, 4.0, -0.5, 8.0, 30.0]}
        mirrored = {"data": [-20.0, 4.0, 0.5, -8.0, 330.0]}
        unrelated = {"data": [200.0, 80.0, 3.0, 1.0, 120.0]}

        self.assertLess(v3._mirror_similarity(target, mirrored), v3._mirror_similarity(target, unrelated))

    def test_app_installs_v3_after_v2(self):
        app_text = Path("app.py").read_text(encoding="utf-8")
        v2_call = "install_simple_layer_native_debug_v2()"
        v3_call = "install_simple_layer_native_debug_v3()"
        self.assertIn(v2_call, app_text)
        self.assertIn(v3_call, app_text)
        self.assertLess(app_text.index(v2_call), app_text.index(v3_call))


if __name__ == "__main__":
    unittest.main()
