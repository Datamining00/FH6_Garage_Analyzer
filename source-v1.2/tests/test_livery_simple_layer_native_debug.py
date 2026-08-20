from __future__ import annotations

import unittest
from pathlib import Path

from fh6garage import livery_simple_layer_native_debug as debug
from fh6garage.livery_preview import LiveryPreviewError


class _Renderer:
    def _shape_mask_flag(self, layer, data):
        return bool(layer.get("mask"))

    def _shape_word_from_shape(self, layer, type_code):
        return int(layer.get("shape_word", 0x0100))


class SimpleLayerNativeDebugTests(unittest.TestCase):
    def setUp(self):
        self.original = debug._ORIGINAL_CORE_VALIDATOR
        self.previous_log = getattr(debug._TLS, "missing_native", None)
        debug._TLS.missing_native = []

    def tearDown(self):
        debug._ORIGINAL_CORE_VALIDATOR = self.original
        debug._TLS.missing_native = self.previous_log

    def _strict_missing(self, renderer, layers, raster_resolver):
        raise LiveryPreviewError(
            "layer 1에 정확한 native FH6 도형 리소스가 없습니다: shape word 0x0100"
        )

    def test_missing_visible_native_is_skipped_and_logged(self):
        debug._ORIGINAL_CORE_VALIDATOR = self._strict_missing
        layer = {
            "type": 1048832,
            "shape_word": 0x0100,
            "source_offset": 123456,
            "mask": False,
        }
        visible, skipped = debug._tolerant_validator(_Renderer(), [layer], None)
        self.assertEqual(visible, [])
        self.assertEqual(skipped, 1)
        self.assertEqual(len(debug._TLS.missing_native), 1)
        self.assertEqual(debug._TLS.missing_native[0]["shape_word"], 0x0100)
        self.assertEqual(debug._TLS.missing_native[0]["source_offset"], 123456)

    def test_missing_native_mask_still_fails_closed(self):
        debug._ORIGINAL_CORE_VALIDATOR = self._strict_missing
        layer = {"type": 1048832, "shape_word": 0x0100, "mask": True}
        with self.assertRaises(LiveryPreviewError) as context:
            debug._tolerant_validator(_Renderer(), [layer], None)
        self.assertIn("mask", str(context.exception))
        self.assertIn("0x0100", str(context.exception))

    def test_existing_asset_keeps_original_validator_result(self):
        layer = {"type": 1048677, "mask": False}

        def strict_ok(renderer, layers, raster_resolver):
            return list(layers), 0

        debug._ORIGINAL_CORE_VALIDATOR = strict_ok
        visible, skipped = debug._tolerant_validator(_Renderer(), [layer], None)
        self.assertEqual(visible, [layer])
        self.assertEqual(skipped, 0)

    def test_app_installs_debug_after_runtime_render_patches(self):
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        text = app_path.read_text(encoding="utf-8")
        debug_pos = text.index("install_simple_layer_native_debug()")
        baseline_pos = text.index("apply_livery_baseline_behavior_patch()")
        self.assertGreater(debug_pos, baseline_pos)


if __name__ == "__main__":
    unittest.main()
