from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fh6garage.fh6_clivery.render_adapter import (
    IndependentRenderAdapterError,
    IndependentRendererScene,
    RENDER_ADAPTER_FORMAT_ID,
)
from fh6garage.livery_independent_render_bridge_patch import (
    _FALLBACK_PREFIX,
    _decode_with_independent_bridge,
)
from fh6garage.livery_preview import DecodedLiveryPreview


class IndependentRenderBridgePatchTests(unittest.TestCase):
    def test_exact_independent_vector_scene_is_preferred_over_legacy_decoder(self) -> None:
        independent = IndependentRendererScene(
            car_id=2997,
            sections={
                "Left": (
                    {
                        "type": 0x100000 + 101,
                        "type_word": 101,
                        "data": [0, 0, 1, 1, 0, 0, 0],
                        "color": [255, 0, 0, 255],
                        "mask": False,
                        "source_section": "Left",
                        "source_format": RENDER_ADAPTER_FORMAT_ID,
                    },
                )
            },
            total_layers=1,
        )
        legacy = Mock(side_effect=AssertionError("legacy decoder must not run"))

        with patch(
            "fh6garage.livery_independent_render_bridge_patch.decode_clivery_renderer_scene",
            return_value=independent,
        ):
            result = _decode_with_independent_bridge(
                "C_livery",
                100,
                200,
                legacy_decode=legacy,
                preview_type=DecodedLiveryPreview,
            )

        legacy.assert_not_called()
        self.assertEqual(result.total_layers, 1)
        self.assertEqual(result.raster_logo_count, 0)
        self.assertEqual(result.sections["Left"][0]["source_format"], RENDER_ADAPTER_FORMAT_ID)
        self.assertEqual(result.warnings, ())

    def test_unvalidated_semantics_use_explicit_legacy_fallback_warning(self) -> None:
        legacy_result = DecodedLiveryPreview(
            sections={"Left": ({"type": 123},)},
            warnings=("legacy warning",),
            total_layers=1,
            raster_logo_count=1,
        )
        legacy = Mock(return_value=legacy_result)

        with patch(
            "fh6garage.livery_independent_render_bridge_patch.decode_clivery_renderer_scene",
            side_effect=IndependentRenderAdapterError("raster semantics unvalidated"),
        ):
            result = _decode_with_independent_bridge(
                "C_livery",
                100,
                200,
                legacy_decode=legacy,
                preview_type=DecodedLiveryPreview,
            )

        legacy.assert_called_once_with("C_livery", 100, 200)
        self.assertEqual(result.sections, legacy_result.sections)
        self.assertEqual(result.raster_logo_count, 1)
        self.assertIn("legacy warning", result.warnings)
        self.assertTrue(any(item.startswith(_FALLBACK_PREFIX) for item in result.warnings))

    def test_app_wires_bridge_after_legacy_recovery_and_before_render_patches(self) -> None:
        app_text = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
        recovery = app_text.index("apply_livery_decoder_recovery_patch()")
        bridge = app_text.index("apply_livery_independent_render_bridge_patch()")
        render_patch = app_text.index("apply_v1_4_preview2_patch(MainWindow)")
        self.assertLess(recovery, bridge)
        self.assertLess(bridge, render_patch)


if __name__ == "__main__":
    unittest.main()
