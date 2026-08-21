from __future__ import annotations

import struct
import unittest

from fh6garage.fh6_clivery.livery_sections import decode_livery_sections
from fh6garage.fh6_clivery.scene import GroupNode, tree_stats

NAMES = tuple(f"S{i}" for i in range(11))

def shape(shape_id: int, *, marker: bytes = b"\x02") -> bytes:
    return marker + struct.pack("<Hffffff", shape_id, 0.0, 0.0, 0.0, 1.0, 1.0, 0.0) + bytes((1,2,3,255))

def markerless(count: int, bitmap: bytes, children: bytes) -> bytes:
    blocks=(count+7)//8
    assert len(bitmap)==blocks
    return struct.pack("<HH",count,blocks)+b"\x00\x00"+bitmap+children

def transform(x=0.0,y=0.0,scale=1.0,rotation=0.0)->bytes:
    return struct.pack("<ffff",x,y,scale,rotation)

def remnant(rotation=0.0)->bytes:
    return b"\x00"+transform(rotation=rotation)+b"\x00"

def trailing_empty(rotation=0.0)->bytes:
    return transform(rotation=rotation)+b"\x00"*7

def standard_empty(rotation=0.0)->bytes:
    return b"\x00"*6+transform(rotation=rotation)+b"\x00"

def flat_root(shape_id:int)->bytes:
    return markerless(1,b"\x00",shape(shape_id))

class LiveryArtworkTests(unittest.TestCase):
    def test_populated_remnant_final_state_and_trailing_empty_scaffolds(self)->None:
        counts=(1,1,0,0,0,0,0,0,0,0,0)
        first=flat_root(101); second=flat_root(102)
        body=first+remnant()+second+b"\x00"+b"".join(trailing_empty() for _ in range(9))
        result=decode_livery_sections(body,0,len(body),NAMES,counts)
        self.assertTrue(result.lossless_record_coverage)
        self.assertEqual(len(result.sections),11)
        self.assertEqual(result.sections[0].parsed_leaf_count,1)
        self.assertEqual(result.sections[0].tree_end,len(first))
        self.assertEqual(result.sections[0].section_end,len(first)+18)
        self.assertEqual(result.sections[1].section_end,len(first)+18+len(second)+1)
        self.assertTrue(all(section.complete for section in result.sections))
        self.assertEqual(b"".join(record.raw for record in result.records),body)

    def test_empty_before_later_artwork_uses_bounded_standard_scaffold(self)->None:
        counts=(0,1,0,0,0,0,0,0,0,0,0)
        body=standard_empty(rotation=-90.0)+flat_root(105)+b"\x00"+b"".join(trailing_empty() for _ in range(9))
        result=decode_livery_sections(body,0,len(body),NAMES,counts)
        self.assertTrue(result.lossless_record_coverage)
        self.assertEqual(result.sections[0].section_end,23)
        self.assertEqual(result.sections[1].section_start,23)
        self.assertEqual(result.sections[1].parsed_leaf_count,1)

    def test_shifted_markerless_after_root_inline_transform_prefers_later_header(self)->None:
        counts=(1,0,0,0,0,0,0,0,0,0,0)
        nested=markerless(1,b"\x00",shape(109))
        root=markerless(1,b"\x01",transform(x=2.0,y=-3.0)+b"\x00"+nested)
        body=root+b"\x00"+b"".join(trailing_empty() for _ in range(10))
        result=decode_livery_sections(body,0,len(body),NAMES,counts)
        section=result.sections[0]
        self.assertTrue(section.complete)
        self.assertEqual(section.parsed_leaf_count,1)
        self.assertIsInstance(section.root.children[0],GroupNode)
        nested_group=section.root.children[0]
        self.assertEqual(nested_group.expected_direct_children,1)
        self.assertEqual(nested_group.children[0].shape_id,109)
        self.assertIn("livery_group_successor_control",[record.kind for record in result.records])
        self.assertTrue(result.lossless_record_coverage)

    def test_invalid_remnant_does_not_scan_forward_for_next_section(self)->None:
        counts=(1,1,0,0,0,0,0,0,0,0,0)
        first=flat_root(111)
        bad=bytearray(remnant()); struct.pack_into("<f",bad,1+8,0.0)
        second=flat_root(112)
        body=first+bytes(bad)+second+b"\x00"+b"".join(trailing_empty() for _ in range(9))
        result=decode_livery_sections(body,0,len(body),NAMES,counts)
        self.assertFalse(result.sections[0].complete)
        self.assertEqual(result.sections[0].unknown_spans[0].offset,len(first))
        self.assertEqual(result.sections[1].section_start,len(body))
        self.assertIn("LIVERY_SECTION_UNKNOWN_TAIL",[item.code for item in result.diagnostics])
        self.assertTrue(result.lossless_record_coverage)

    def test_tree_stats_are_structural_not_source_offset_order(self)->None:
        counts=(1,0,0,0,0,0,0,0,0,0,0)
        nested=markerless(1,b"\x00",shape(113))
        root=markerless(1,b"\x01",transform()+b"\x00"+nested)
        body=root+b"\x00"+b"".join(trailing_empty() for _ in range(10))
        result=decode_livery_sections(body,0,len(body),NAMES,counts)
        stats=tree_stats(result.sections[0].root)
        self.assertEqual(stats["nested_group_count"],1)
        self.assertEqual(stats["leaf_count"],1)
        self.assertEqual(stats["max_group_depth"],1)

if __name__=="__main__": unittest.main()
