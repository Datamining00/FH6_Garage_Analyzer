from __future__ import annotations

import unittest

from fh6garage.fh6_clivery.decoder import SECTION_NAMES
from fh6garage.fh6_clivery.flatten import (
    EffectiveTransform,
    FlattenedLayer,
    FlattenedLivery,
    FlattenedSection,
)
from fh6garage.fh6_clivery.render_adapter import (
    IndependentRenderAdapterError,
    RENDER_ADAPTER_FORMAT_ID,
    renderer_scene_from_flattened,
)


def _layer(
    word: int,
    offset: int,
    traversal_index: int,
    section: str,
    *,
    mask: bool = False,
    color=(255, 255, 255, 255),
) -> FlattenedLayer:
    return FlattenedLayer(
        type_word=word,
        transform=EffectiveTransform(1.0, 2.0, 3.0, 4.0, 5.0, 0.25),
        color_rgba=tuple(color),
        mask=mask,
        source_offset=offset,
        source_marker="0002",
        source_section=section,
        source_parent_path=(3, traversal_index),
        mask_evidence=("test",),
        traversal_index=traversal_index,
        transform_evidence="test-transform",
    )


def _livery_with_section(
    target_name: str,
    layers: tuple[FlattenedLayer, ...],
    *,
    complete: bool = True,
    declared_count: int | None = None,
) -> FlattenedLivery:
    sections = []
    for slot, name in enumerate(SECTION_NAMES):
        current = layers if name == target_name else ()
        declared = len(current) if declared_count is None or name != target_name else declared_count
        sections.append(
            FlattenedSection(
                slot=slot,
                name=name,
                declared_count=declared,
                layers=current,
                complete=complete if name == target_name else True,
            )
        )
    return FlattenedLivery(car_id=2997, body_start=72, body_end=1000, sections=tuple(sections))


class IndependentRenderAdapterTests(unittest.TestCase):
    def test_vector_bridge_preserves_structural_order_not_source_offset_order(self) -> None:
        layers = (
            _layer(101, 300, 0, "Left", color=(255, 0, 0, 255)),
            _layer(102, 100, 1, "Left", mask=True, color=(0, 255, 0, 255)),
            _layer(103, 200, 2, "Left", color=(0, 0, 255, 255)),
        )
        result = renderer_scene_from_flattened(_livery_with_section("Left", layers))
        left = result.sections["Left"]

        self.assertEqual(result.total_layers, 3)
        self.assertEqual([item["type_word"] for item in left], [101, 102, 103])
        self.assertEqual([item["source_offset"] for item in left], [300, 100, 200])
        self.assertEqual([item["type"] for item in left], [0x100000 + 101, 0x100000 + 102, 0x100000 + 103])
        self.assertEqual(left[1]["data"][6], 1.0)
        self.assertEqual(left[1]["color"], [0, 255, 0, 255])
        self.assertEqual(left[1]["source_format"], RENDER_ADAPTER_FORMAT_ID)

    def test_incomplete_section_fails_closed(self) -> None:
        layers = (_layer(101, 100, 0, "Left"),)
        with self.assertRaisesRegex(IndependentRenderAdapterError, "incomplete"):
            renderer_scene_from_flattened(
                _livery_with_section("Left", layers, complete=False)
            )

    def test_declared_count_mismatch_fails_closed(self) -> None:
        layers = (_layer(101, 100, 0, "Left"),)
        with self.assertRaisesRegex(IndependentRenderAdapterError, "declared 2"):
            renderer_scene_from_flattened(
                _livery_with_section("Left", layers, declared_count=2)
            )

    def test_raster_like_high_bit_word_falls_back_instead_of_vector_guess(self) -> None:
        layers = (_layer(0x8001, 100, 0, "Left"),)
        with self.assertRaisesRegex(IndependentRenderAdapterError, "raster/logo-like"):
            renderer_scene_from_flattened(_livery_with_section("Left", layers))

    def test_traversal_index_discontinuity_is_rejected(self) -> None:
        layers = (_layer(101, 100, 1, "Left"),)
        with self.assertRaisesRegex(IndependentRenderAdapterError, "traversal index"):
            renderer_scene_from_flattened(_livery_with_section("Left", layers))


if __name__ == "__main__":
    unittest.main()
