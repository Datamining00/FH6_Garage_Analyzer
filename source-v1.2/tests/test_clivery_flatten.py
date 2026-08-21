from __future__ import annotations

import unittest

from fh6garage.fh6_clivery.flatten import (
    EffectiveTransform,
    FlattenedLayer,
    FlattenedLivery,
    FlattenedSection,
    _Frame,
    _compose,
    _normalize_rotation,
    _resolve_masks,
)
from fh6garage.fh6_clivery.records import RawRecord, SourceSpan, Transform
from fh6garage.fh6_clivery.scene import GroupNode, ShapeNode
from fh6garage.fh6_clivery.semantic_diff import (
    SemanticLayer,
    compare_semantic_layers,
    semantic_layers_from_flattened,
)


class M4TransformTests(unittest.TestCase):
    def test_group_position_composition_uses_parent_scale_then_rotation(self) -> None:
        parent = _Frame(-309.5, -33.5, 0.40000057220458984, 0.40000057220458984, 306.2998352050781)
        result = _compose(parent, x=0.25, y=416.25, sx=0.28646013140678406, sy=0.28645992279052734, rotation=0.0)
        self.assertAlmostEqual(result.x, -175.25326436990815, places=10)
        self.assertAlmostEqual(result.y, 64.98935621042008, places=10)
        self.assertAlmostEqual(result.sx, 0.11458421647651561, places=12)
        self.assertAlmostEqual(result.sy, 0.11458413302989355, places=12)
        self.assertAlmostEqual(result.rotation, 306.2998352050781, places=10)

    def test_reflected_parent_negates_child_rotation_contribution(self) -> None:
        parent = _Frame(171.5, -12.5, 0.09000031650066376, -0.09000031650066376, 112.90007781982422)
        result = _compose(parent, x=20.5, y=-211.75, sx=0.5524863004684448, sy=1.4609191417694092, rotation=264.20013427734375)
        self.assertAlmostEqual(result.rotation, 208.69994354248047, places=9)
        self.assertLess(result.sy, 0.0)
        # Final renderer canonicalization adds 180 degrees when Y scale is negative.
        self.assertAlmostEqual(_normalize_rotation(result.rotation + 180.0), 28.69994354248047, places=9)

    def _shape(self, offset: int, marker: str, color: tuple[int,int,int,int]) -> ShapeNode:
        span=SourceSpan(offset,32)
        raw=RawRecord("shape",span,b"\x00"*32,"test",marker)
        return ShapeNode(span,raw,101,Transform(source_span=span),color,marker,False,"test",(0,offset))

    def _group(self, children, *, mask: bool=False, evidence: str="NO_CONFIRMED_MASK_ANCESTRY") -> GroupNode:
        span=SourceSpan(0,1)
        raw=RawRecord("group",span,b"\x20","test","20")
        return GroupNode(span,span,raw,"20",len(children),b"\x00",Transform(),mask,evidence,(0,),list(children),[],True)

    def test_0102_trailing_state_targets_previous_direct_achromatic_shape(self) -> None:
        previous=self._shape(10,"0002",(127,127,127,255))
        current=self._shape(42,"0102",(211,200,0,255))
        masks=_resolve_masks(self._group([previous,current]))
        self.assertEqual(masks[id(previous)],(True,("shape_0102_trailing_state",)))
        self.assertEqual(masks[id(current)],(False,("NO_EFFECTIVE_MASK",)))

    def test_0102_trailing_state_targets_previous_direct_chromatic_shape(self) -> None:
        previous=self._shape(10,"0002",(255,0,0,255))
        current=self._shape(42,"0102",(255,255,255,255))
        masks=_resolve_masks(self._group([previous,current]))
        self.assertEqual(masks[id(previous)],(True,("shape_0102_trailing_state",)))
        self.assertEqual(masks[id(current)],(False,("NO_EFFECTIVE_MASK",)))

    def test_0102_after_completed_group_remains_unresolved(self) -> None:
        nested_shape=self._shape(10,"0002",(255,255,255,255))
        nested=self._group([nested_shape])
        current=self._shape(42,"0102",(255,255,255,255))
        masks=_resolve_masks(self._group([nested,current]))
        self.assertEqual(masks[id(nested_shape)],(False,("NO_EFFECTIVE_MASK",)))
        self.assertEqual(masks[id(current)],(False,("NO_EFFECTIVE_MASK",)))

    def test_confirmed_60_ancestry_is_authoritative(self) -> None:
        a=self._shape(10,"0002",(1,2,3,255))
        b=self._shape(42,"0102",(4,5,6,255))
        masks=_resolve_masks(self._group([a,b],mask=True,evidence="CONFIRMED_GROUP_60_ANCESTRY"))
        self.assertEqual(masks[id(a)],(True,("CONFIRMED_GROUP_60_ANCESTRY",)))
        self.assertEqual(masks[id(b)],(True,("CONFIRMED_GROUP_60_ANCESTRY",)))

    def test_semantic_comparator_covers_required_m4_fields(self) -> None:
        a = SemanticLayer("Left", 0, 101, (3, 0), 99623, (-56.0, 5.0, 8.0, 8.0, 0.0, 0.0), False, (1, 2, 3, 255))
        b = SemanticLayer("Left", 0, 101, (3, 0), 99623, (-56.0, 5.0, 8.0, 8.0, 0.0, 0.0), False, (1, 2, 3, 255))
        self.assertTrue(compare_semantic_layers([a], [b]).match)
        changed = SemanticLayer("Left", 0, 102, (3, 1), 99654, (-55.0, 5.0, 8.0, 8.0, 0.0, 0.0), True, (9, 9, 9, 255))
        report = compare_semantic_layers([a], [changed])
        self.assertFalse(report.match)
        self.assertTrue({d.field for d in report.differences} >= {"shape_identity", "parent_path", "source_offset", "transform", "mask", "color"})

    def test_flattened_document_preserves_structural_order_not_offset_sort_contract(self) -> None:
        first = FlattenedLayer(101, EffectiveTransform(0,0,1,1,0,0), (0,0,0,255), False, 200, "02", "Front", (0,0), ("NO_EFFECTIVE_MASK",), 0, "test")
        second = FlattenedLayer(102, EffectiveTransform(0,0,1,1,0,0), (0,0,0,255), False, 100, "0002", "Front", (0,1), ("NO_EFFECTIVE_MASK",), 1, "test")
        section = FlattenedSection(0, "Front", 2, (first, second), True)
        doc = FlattenedLivery(1, 0, 0, (section,))
        layers = semantic_layers_from_flattened(doc)
        self.assertEqual([layer.source_offset for layer in layers], [200, 100])
        self.assertEqual(doc.order_semantics, "STRUCTURAL_DEPTH_FIRST_CHILD_ORDER")
        self.assertEqual(doc.draw_order_evidence, "PROVISIONAL_NOT_RENDERER_BOUND")


if __name__ == "__main__":
    unittest.main()
