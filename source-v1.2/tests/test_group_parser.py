from __future__ import annotations
import struct
import unittest
import zlib

from fh6garage.fh6_clivery.cgroup import CGroupDecodeError, decode_cgroup_bytes


def shape(shape_id: int, *, marker: bytes=b"\x00\x02", x=0.0, y=0.0, sx=1.0, sy=1.0, rotation=0.0, skew=0.0, bgra=(10,20,30,255)) -> bytes:
    return marker + struct.pack("<Hffffff", shape_id, rotation, x, y, sx, sy, skew) + bytes(bgra)


def transform(*, marker: bytes=b"\x03", x=0.0, y=0.0, scale=1.0, rotation=0.0, sy=None) -> bytes:
    raw = marker + struct.pack("<ffff", x, y, scale, rotation)
    if sy is not None:
        raw += b"\x30" + struct.pack("<f", sy)
    return raw


def counted_group(marker: int, count: int, bitmap: bytes, children: bytes) -> bytes:
    blocks = (count + 7) // 8
    assert len(bitmap) == blocks
    return bytes([marker]) + struct.pack("<HH", count, blocks) + b"\x00\x00" + bitmap + children


def markerless_group(count: int, bitmap: bytes, children: bytes) -> bytes:
    blocks = (count + 7) // 8
    assert len(bitmap) == blocks
    return struct.pack("<HH", count, blocks) + b"\x00\x00" + bitmap + children


def cgroup_payload(*, root_count: int, root_bitmap: bytes, body: bytes, root_group_marker: int=0x20, root_transform_marker: int=0x03) -> bytes:
    blocks = (root_count + 7) // 8
    assert len(root_bitmap) == blocks
    payload = bytearray(0x24 + blocks)
    payload[:4] = b"gyvl"
    struct.pack_into("<I", payload, 4, 1)
    payload[0x0C] = root_transform_marker
    struct.pack_into("<ffff", payload, 0x0D, 0.0, 0.0, 1.0, 0.0)
    payload[0x1D] = root_group_marker
    struct.pack_into("<H", payload, 0x1E, root_count)
    payload[0x20] = blocks
    payload[0x21:0x24] = b"\x00\x00\x00"
    payload[0x24:0x24 + blocks] = root_bitmap
    return bytes(payload) + body


class CGroupSceneTests(unittest.TestCase):
    def test_flat_shapes_preserve_ids_transforms_colors_paths_and_bytes(self):
        first = shape(101, x=12.5, y=-7.25, sx=2.0, sy=-3.0, rotation=45.0, skew=0.25)
        second = shape(105, marker=b"\x02", bgra=(1,2,3,4))
        payload = cgroup_payload(root_count=2, root_bitmap=b"\x00", body=first + second)
        scene = decode_cgroup_bytes(payload)
        self.assertTrue(scene.root.complete)
        self.assertTrue(scene.lossless_record_coverage)
        self.assertEqual(scene.to_dict()["stats"]["leaf_count"], 2)
        a, b = scene.root.children
        self.assertEqual(a.shape_id, 101)
        self.assertEqual(a.parent_path, (0,))
        self.assertAlmostEqual(a.transform.x, 12.5)
        self.assertAlmostEqual(a.transform.sy, -3.0)
        self.assertEqual(a.color_rgba, (30,20,10,255))
        self.assertEqual(b.shape_id, 105)
        self.assertEqual(b.parent_path, (1,))
        self.assertEqual(b.marker_hex, "02")
        self.assertEqual(b.color_rgba, (3,2,1,4))
        self.assertEqual(b"".join(record.raw for record in scene.records), payload)

    def test_nested_counted_group_uses_parent_bitmap_not_shape_guessing(self):
        child_body = shape(109) + shape(113)
        nested = counted_group(0x20, 2, b"\x00", child_body)
        payload = cgroup_payload(root_count=2, root_bitmap=b"\x01", body=nested + shape(117))
        scene = decode_cgroup_bytes(payload)
        group = scene.root.children[0]
        self.assertEqual(group.expected_direct_children, 2)
        self.assertEqual(group.parsed_direct_children, 2)
        self.assertEqual([node.shape_id for node in group.children], [109,113])
        self.assertEqual(group.parent_path, (0,))
        self.assertEqual(group.children[1].parent_path, (0,1))
        self.assertEqual(scene.root.children[1].shape_id, 117)
        self.assertEqual(scene.to_dict()["stats"]["nested_group_count"], 1)
        self.assertEqual(scene.to_dict()["stats"]["leaf_count"], 3)

    def test_preceding_transform_binds_to_counted_group(self):
        tr = transform(x=5.0, y=6.0, scale=2.0, rotation=30.0, sy=-4.0)
        nested = counted_group(0x20, 1, b"\x00", shape(121))
        payload = cgroup_payload(root_count=1, root_bitmap=b"\x01", body=tr + nested)
        scene = decode_cgroup_bytes(payload)
        group = scene.root.children[0]
        self.assertAlmostEqual(group.transform.x, 5.0)
        self.assertAlmostEqual(group.transform.sy, -4.0)
        self.assertEqual(group.transform.source_span.offset, 0x25)
        self.assertTrue(scene.lossless_record_coverage)

    def test_markerless_group_is_only_accepted_after_transform(self):
        tr = transform(x=2.0)
        nested = markerless_group(1, b"\x00", shape(125))
        payload = cgroup_payload(root_count=1, root_bitmap=b"\x01", body=tr + nested)
        scene = decode_cgroup_bytes(payload)
        group = scene.root.children[0]
        self.assertEqual(group.marker_hex, "")
        self.assertEqual(group.raw_header.kind, "markerless_group_header")
        self.assertEqual(group.children[0].shape_id, 125)
        self.assertTrue(scene.root.complete)

    def test_mask_group_inherits_to_descendant_shape(self):
        nested = counted_group(0x60, 1, b"\x00", shape(129))
        payload = cgroup_payload(root_count=1, root_bitmap=b"\x01", body=nested)
        scene = decode_cgroup_bytes(payload)
        group = scene.root.children[0]
        leaf = group.children[0]
        self.assertTrue(group.mask)
        self.assertTrue(leaf.mask)
        self.assertEqual(leaf.mask_evidence, "CONFIRMED_GROUP_60_ANCESTRY")

    def test_contextual_odd_lead_preserves_previous_mask_as_unresolved(self):
        previous = shape(133, bgra=(100,100,100,255))
        contextual = shape(137, marker=b"\x01\x02")
        payload = cgroup_payload(root_count=2, root_bitmap=b"\x00", body=previous + contextual)
        scene = decode_cgroup_bytes(payload)
        first, second = scene.root.children
        self.assertIsNone(first.mask)
        self.assertEqual(first.mask_evidence, "UNRESOLVED_CONTEXTUAL_ODD_LEAD_ON_NEXT_SIBLING")
        self.assertFalse(second.mask)
        self.assertIsNone(scene.generation)

    def test_contextual_odd_lead_does_not_apply_chromatic_rule_without_generation(self):
        previous = shape(141, bgra=(1,2,3,255))
        contextual = shape(145, marker=b"\x01\x02")
        payload = cgroup_payload(root_count=2, root_bitmap=b"\x00", body=previous + contextual)
        scene = decode_cgroup_bytes(payload)
        first = scene.root.children[0]
        self.assertIsNone(first.mask)
        self.assertEqual(first.mask_evidence, "UNRESOLVED_CONTEXTUAL_ODD_LEAD_ON_NEXT_SIBLING")

    def test_inline_transform_before_first_shape_binds_to_group(self):
        inline = transform(x=9.0, y=-2.0, scale=0.5, rotation=15.0)
        nested = counted_group(0x20, 1, b"\x00", inline + shape(149))
        payload = cgroup_payload(root_count=1, root_bitmap=b"\x01", body=nested)
        scene = decode_cgroup_bytes(payload)
        group = scene.root.children[0]
        self.assertAlmostEqual(group.transform.x, 9.0)
        self.assertAlmostEqual(group.transform.sx, 0.5)
        self.assertEqual(group.children[0].shape_id, 149)
        self.assertTrue(scene.lossless_record_coverage)

    def test_inline_transform_before_first_group_binds_to_first_child(self):
        inline = transform(x=11.0, y=3.0, scale=1.25, rotation=90.0)
        grandchild = counted_group(0x20, 1, b"\x00", shape(151))
        nested = counted_group(0x20, 1, b"\x01", inline + grandchild)
        payload = cgroup_payload(root_count=1, root_bitmap=b"\x01", body=nested)
        scene = decode_cgroup_bytes(payload)
        group = scene.root.children[0]
        first_child = group.children[0]
        self.assertAlmostEqual(first_child.transform.x, 11.0)
        self.assertAlmostEqual(first_child.transform.rotation, 90.0)
        self.assertEqual(first_child.children[0].shape_id, 151)
        self.assertTrue(scene.lossless_record_coverage)

    def test_unknown_child_preserves_remaining_bytes_without_scanning(self):
        tail = b"\x99\x88\x77" + shape(149)
        payload = cgroup_payload(root_count=1, root_bitmap=b"\x00", body=tail)
        scene = decode_cgroup_bytes(payload)
        unknown = scene.root.children[0]
        self.assertTrue(unknown.reason.startswith("parent bitmap requires a shape"))
        self.assertEqual(unknown.raw_record.raw, tail)
        self.assertFalse(scene.root.complete)
        self.assertTrue(scene.lossless_record_coverage)
        self.assertEqual(scene.to_dict()["stats"]["leaf_count"], 0)
        self.assertEqual(scene.to_dict()["stats"]["unknown_node_count"], 1)

    def test_consecutive_group_transforms_are_preserved_as_unknown_tail(self):
        first = transform(x=1.0)
        second = transform(x=2.0)
        nested = counted_group(0x20, 1, b"\x00", shape(153))
        payload = cgroup_payload(root_count=1, root_bitmap=b"\x01", body=first + second + nested)
        scene = decode_cgroup_bytes(payload)
        self.assertFalse(scene.root.complete)
        self.assertTrue(scene.lossless_record_coverage)
        kinds = [record.kind for record in scene.records]
        self.assertIn("group_transform", kinds)
        self.assertEqual(kinds[-1], "unknown_span")

    def test_root_zero_padding_is_preserved_before_first_flat_shape(self):
        payload = cgroup_payload(root_count=1, root_bitmap=b"\x00", body=b"\x00\x00\x00" + shape(157))
        scene = decode_cgroup_bytes(payload)
        self.assertTrue(scene.root.complete)
        self.assertIn("zero_padding", [record.kind for record in scene.records])
        self.assertEqual(scene.root.children[0].shape_id, 157)
        self.assertTrue(scene.lossless_record_coverage)

    def test_zlib_container_and_inflated_payload_match(self):
        payload = cgroup_payload(root_count=1, root_bitmap=b"\x00", body=shape(161))
        compressed = zlib.compress(payload)
        wrapped = struct.pack("<II", len(compressed), len(payload)) + compressed
        plain = decode_cgroup_bytes(payload)
        packed = decode_cgroup_bytes(wrapped)
        self.assertEqual(plain.payload_sha256, packed.payload_sha256)
        self.assertEqual(plain.root.to_dict(), packed.root.to_dict())

    def test_invalid_root_bitmap_block_count_is_rejected(self):
        payload = bytearray(cgroup_payload(root_count=9, root_bitmap=b"\x00\x00", body=b""))
        payload[0x20] = 1
        with self.assertRaises(CGroupDecodeError):
            decode_cgroup_bytes(payload)


if __name__ == "__main__":
    unittest.main()
