from __future__ import annotations

import json
import struct
import unittest
import zlib

from fh6garage.fh6_clivery import CliveryDecodeError, SECTION_NAMES, decode_clivery_bytes


KNOWN_COUNTS = (1, 21, 2980, 2761, 2785, 3, 0, 0, 0, 18, 0)


def make_payload(
    *,
    car_id: int = 3761,
    gyvl_offset: int = 51,
    body_end: int = 100,
    counts: tuple[int, ...] = KNOWN_COUNTS,
) -> bytes:
    size = body_end + 4 + 48 + 16
    payload = bytearray(size)
    payload[:4] = b"vlrc"
    struct.pack_into("<I", payload, 0x10, car_id)
    payload[gyvl_offset:gyvl_offset + 4] = b"gyvl"
    body_start = gyvl_offset + 0x15
    payload[body_start:body_start + 8] = b"ARTWORK!"
    payload[body_end:body_end + 4] = b"yrvl"
    for index, value in enumerate(counts):
        struct.pack_into("<I", payload, body_end + 4 + index * 4, value)
    struct.pack_into("<I", payload, body_end + 48, sum(counts))
    payload[body_end + 52:body_end + 56] = b"yrvl"
    return bytes(payload)


class CliverySectionTests(unittest.TestCase):
    def test_known_3761_metadata_fixture(self) -> None:
        result = decode_clivery_bytes(make_payload())
        self.assertEqual(result.car_id, 3761)
        self.assertEqual(result.gyvl_offset, 51)
        self.assertEqual(result.body_start, 72)
        self.assertEqual([item.declared_count for item in result.sections], list(KNOWN_COUNTS))

    def test_section_names_and_slots_are_stable(self) -> None:
        result = decode_clivery_bytes(make_payload())
        self.assertEqual(
            [(item.slot, item.name) for item in result.sections],
            list(enumerate(SECTION_NAMES)),
        )

    def test_first_post_artwork_yrvl_is_body_end(self) -> None:
        result = decode_clivery_bytes(make_payload(body_end=137))
        self.assertEqual(result.body_end, 137)

    def test_container_and_inflated_inputs_have_same_semantics(self) -> None:
        payload = make_payload()
        compressed = zlib.compress(payload)
        wrapped = struct.pack("<II", len(compressed), len(payload)) + compressed
        plain = decode_clivery_bytes(payload).to_dict()
        packed = decode_clivery_bytes(wrapped).to_dict()
        for key in ("car_id", "gyvl_offset", "body_start", "body_end", "sections"):
            self.assertEqual(plain[key], packed[key])

    def test_json_output_uses_milestone_format_identifier(self) -> None:
        result = decode_clivery_bytes(make_payload())
        document = json.loads(result.to_json())
        self.assertEqual(document["format"], "fh6-assistant-clivery-scene-v1")
        self.assertEqual(len(document["sections"]), 11)
        self.assertIsInstance(document["diagnostics"], list)

    def test_missing_gyvl_is_rejected(self) -> None:
        payload = bytearray(make_payload())
        payload[51:55] = b"xxxx"
        with self.assertRaises(CliveryDecodeError):
            decode_clivery_bytes(payload)


if __name__ == "__main__":
    unittest.main()
