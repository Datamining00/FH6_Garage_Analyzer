from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from fh6garage import livery_simple_layer_native_debug as base
from fh6garage import livery_simple_layer_native_debug_v2 as debug_v2


class _Renderer:
    def _shape_mask_flag(self, layer, data):
        return bool(layer.get("mask"))

    def _shape_word_from_shape(self, layer, type_code):
        return int(layer.get("shape_word", 0x0100))

    def _resolve_vinyl_resource(self, type_code, layer):
        return None


class SimpleLayerNativeDebugV2Tests(unittest.TestCase):
    def test_split_range_refines_selected_coarse_window(self):
        ranges = debug_v2._split_range(2415, 2761, 8)
        self.assertEqual(ranges[0], (2415, 2458))
        self.assertEqual(ranges[-1], (2717, 2761))
        self.assertEqual(sum(end - start for start, end in ranges), 346)

    def test_dark_occluder_score_prefers_large_black_region(self):
        neutral = Image.new("RGB", (320, 180), (58, 58, 58))
        dark = neutral.copy()
        for x in range(100, 300):
            for y in range(20, 170):
                dark.putpixel((x, y), (0, 0, 0))

        def png_bytes(image):
            out = io.BytesIO()
            image.save(out, format="PNG")
            return out.getvalue()

        self.assertGreater(
            debug_v2._dark_occluder_score(png_bytes(dark)),
            debug_v2._dark_occluder_score(png_bytes(neutral)),
        )

    def test_missing_mask_log_contains_target_and_neighbors(self):
        renderer = _Renderer()
        layers = [
            {"type": 1048677 + index, "shape_word": 0x0065 + index, "source_offset": 100 + index * 32, "mask": False}
            for index in range(7)
        ]
        layers[3] = {
            "type": 0x100100,
            "shape_word": 0x0100,
            "source_offset": 196,
            "source_section": "Right",
            "mask": True,
            "data": [1, 2, 3, 4, 5, 0, 1],
            "color": [0, 0, 0, 255],
        }

        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "C_livery"
            source.write_bytes(b"not-a-real-container")
            out_dir = Path(temp) / "out"
            out_dir.mkdir()
            original_dir = base._probe_output_dir
            previous_source = getattr(base._TLS, "simple_debug_source", None)
            previous_section = getattr(base._TLS, "simple_debug_section", None)
            try:
                base._probe_output_dir = lambda _source: out_dir
                base._TLS.simple_debug_source = str(source)
                base._TLS.simple_debug_section = "Right"
                debug_v2._write_missing_mask_log(renderer, layers, 4, "layer 4 mask missing")
            finally:
                base._probe_output_dir = original_dir
                if previous_source is None:
                    delattr(base._TLS, "simple_debug_source")
                else:
                    base._TLS.simple_debug_source = previous_source
                if previous_section is None:
                    delattr(base._TLS, "simple_debug_section")
                else:
                    base._TLS.simple_debug_section = previous_section

            payload = json.loads((out_dir / "Right-missing-native-mask.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["target"]["shape_word"], 0x0100)
            self.assertTrue(payload["target"]["mask"])
            self.assertEqual(len(payload["neighbors"]), 7)
            self.assertEqual(payload["raw_payload_window"]["target_offset"], 196)

    def test_app_installs_v2_after_v1(self):
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        text = app_path.read_text(encoding="utf-8")
        self.assertGreater(
            text.index("install_simple_layer_native_debug_v2()"),
            text.index("install_simple_layer_native_debug()"),
        )


if __name__ == "__main__":
    unittest.main()
