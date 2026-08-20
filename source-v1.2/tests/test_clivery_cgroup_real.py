from __future__ import annotations

import hashlib
import os
from pathlib import Path
import struct
import unittest

from fh6garage.fh6_clivery.cgroup import decode_cgroup_bytes, decode_cgroup_file, inflate_cgroup


NESTED_SAMPLE_SHA256 = "00e2d548fc91af5d8d449020f26c468b6a2d63820596d828561b56a8fd6028f9"
NESTED_PAYLOAD_SHA256 = "68ff616748d2cbf64b69d681fa4707612f4d0a8db6177deb313c297df873fc7e"


def shape(shape_id: int, *, marker: bytes = b"\x00\x02") -> bytes:
    return marker + struct.pack(
        "<Hffffff",
        shape_id,
        0.0,
        0.0,
        0.0,
        1.0,
        1.0,
        0.0,
    ) + bytes((10, 20, 30, 255))


def counted_group(marker: int, count: int, bitmap: bytes, children: bytes) -> bytes:
    blocks = (count + 7) // 8
    assert len(bitmap) == blocks
    return (
        bytes([marker])
        + struct.pack("<HH", count, blocks)
        + b"\x00\x00"
        + bitmap
        + children
    )


def cgroup_payload(*, root_count: int, root_bitmap: bytes, body: bytes) -> bytes:
    blocks = (root_count + 7) // 8
    assert len(root_bitmap) == blocks
    payload = bytearray(0x24 + blocks)
    payload[:4] = b"gyvl"
    struct.pack_into("<I", payload, 4, 1)
    payload[0x0C] = 0x03
    struct.pack_into("<ffff", payload, 0x0D, 0.0, 0.0, 1.0, 0.0)
    payload[0x1D] = 0x20
    struct.pack_into("<H", payload, 0x1E, root_count)
    payload[0x20] = blocks
    payload[0x21:0x24] = b"\x00\x00\x00"
    payload[0x24:0x24 + blocks] = root_bitmap
    return bytes(payload) + body


class GroupToShapeControlTests(unittest.TestCase):
    def test_single_zero_after_completed_group_requires_following_shape_proof(self) -> None:
        child = counted_group(0x20, 1, b"\x00", shape(102, marker=b"\x02"))
        parent = counted_group(
            0x20,
            2,
            b"\x01",
            child + b"\x00" + shape(105, marker=b"\x01\x02"),
        )
        payload = cgroup_payload(root_count=1, root_bitmap=b"\x01", body=parent)
        scene = decode_cgroup_bytes(payload)

        parent_node = scene.root.children[0]
        self.assertTrue(scene.root.complete)
        self.assertTrue(parent_node.complete)
        self.assertTrue(scene.lossless_record_coverage)
        self.assertEqual(scene.to_dict()["stats"]["nested_group_count"], 2)
        self.assertEqual(scene.to_dict()["stats"]["leaf_count"], 2)
        self.assertEqual(parent_node.children[1].shape_id, 105)
        controls = [
            record
            for record in parent_node.control_records
            if record.kind == "group_to_shape_control"
        ]
        self.assertEqual(len(controls), 1)
        self.assertEqual(controls[0].raw, b"\x00")
        self.assertEqual(controls[0].evidence_state, "CONFIRMED")
        self.assertEqual(b"".join(record.raw for record in scene.records), payload)

    def test_single_zero_is_not_skipped_without_complete_following_shape(self) -> None:
        child = counted_group(0x20, 1, b"\x00", shape(102, marker=b"\x02"))
        invalid_tail = b"\x00\x99\x88\x77"
        parent = counted_group(0x20, 2, b"\x01", child + invalid_tail)
        payload = cgroup_payload(root_count=1, root_bitmap=b"\x01", body=parent)
        scene = decode_cgroup_bytes(payload)

        self.assertFalse(scene.root.complete)
        self.assertTrue(scene.lossless_record_coverage)
        self.assertEqual(scene.records[-1].kind, "unknown_span")
        self.assertEqual(scene.records[-1].raw, invalid_tail)
        self.assertNotIn(
            "group_to_shape_control",
            [record.kind for record in scene.records],
        )


class RealNestedCGroupRegressionTests(unittest.TestCase):
    def test_uploaded_nested_cgroup_when_sample_is_available(self) -> None:
        value = os.environ.get("FH6_CGROUP_NESTED")
        if not value or not Path(value).is_file():
            self.skipTest("set FH6_CGROUP_NESTED to uploaded raw sample C_group(5)")

        path = Path(value)
        raw = path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), NESTED_SAMPLE_SHA256)
        payload, _ = inflate_cgroup(raw)
        self.assertEqual(hashlib.sha256(payload).hexdigest(), NESTED_PAYLOAD_SHA256)

        scene = decode_cgroup_file(path)
        stats = scene.to_dict()["stats"]
        self.assertEqual(scene.payload_length, 366)
        self.assertEqual(scene.root.expected_direct_children, 2)
        self.assertEqual(scene.root.child_bitmap, b"\x03")
        self.assertTrue(scene.root.complete)
        self.assertTrue(scene.lossless_record_coverage)
        self.assertEqual(stats["nested_group_count"], 4)
        self.assertEqual(stats["leaf_count"], 7)
        self.assertEqual(stats["unknown_node_count"], 0)
        self.assertEqual(stats["max_group_depth"], 2)

        first, second = scene.root.children
        self.assertEqual(first.child_bitmap, b"\x01")
        self.assertEqual(second.child_bitmap, b"\x01")
        self.assertEqual(
            [
                node.shape_id if hasattr(node, "shape_id") else None
                for node in first.children
            ],
            [None, 105, 109],
        )
        self.assertEqual(
            [
                node.shape_id if hasattr(node, "shape_id") else None
                for node in second.children
            ],
            [None, 101],
        )
        self.assertEqual(
            [node.shape_id for node in first.children[0].children],
            [102, 104],
        )
        self.assertEqual(
            [node.shape_id for node in second.children[0].children],
            [102, 104],
        )

        control_offsets = [
            record.span.offset
            for record in scene.records
            if record.kind == "group_to_shape_control"
        ]
        self.assertEqual(control_offsets, [0x96, 0x14A])
        self.assertEqual(scene.records[-1].kind, "trailing_bytes")
        self.assertEqual(scene.records[-1].raw, b"\x00\x01\x01")
        self.assertEqual(b"".join(record.raw for record in scene.records), payload)


if __name__ == "__main__":
    unittest.main()
