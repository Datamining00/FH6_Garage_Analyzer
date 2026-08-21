from __future__ import annotations

import struct
import unittest
import zlib

from fh6garage.fh6_clivery import CliveryDecodeError, inflate_clivery


def make_payload() -> bytes:
    payload = bytearray(160)
    payload[:4] = b"vlrc"
    struct.pack_into("<I", payload, 0x10, 3761)
    payload[51:55] = b"gyvl"
    payload[72:80] = b"ARTWORK!"
    payload[100:104] = b"yrvl"
    counts = (1, 21, 2980, 2761, 2785, 3, 0, 0, 0, 18, 0)
    for index, value in enumerate(counts):
        struct.pack_into("<I", payload, 104 + index * 4, value)
    struct.pack_into("<I", payload, 148, sum(counts))
    payload[152:156] = b"yrvl"
    return bytes(payload)


def wrap(payload: bytes) -> bytes:
    compressed = zlib.compress(payload)
    return struct.pack("<II", len(compressed), len(payload)) + compressed


class CliveryContainerTests(unittest.TestCase):
    def test_inflated_payload_is_accepted_without_mutation(self) -> None:
        payload = make_payload()
        decoded, info = inflate_clivery(payload)
        self.assertEqual(decoded, payload)
        self.assertEqual(info.source_kind, "inflated-payload")
        self.assertEqual(info.payload_offset, 0)

    def test_zlib_container_is_inflated(self) -> None:
        payload = make_payload()
        decoded, info = inflate_clivery(wrap(payload))
        self.assertEqual(decoded, payload)
        self.assertEqual(info.source_kind, "fh6-zlib-container")
        self.assertEqual(info.payload_offset, 8)
        self.assertEqual(info.actual_uncompressed_length, len(payload))

    def test_truncated_header_is_rejected(self) -> None:
        with self.assertRaises(CliveryDecodeError):
            inflate_clivery(b"\x00\x01\x02")

    def test_compressed_length_mismatch_is_rejected(self) -> None:
        payload = make_payload()
        raw = bytearray(wrap(payload))
        struct.pack_into("<I", raw, 0, len(raw))
        with self.assertRaises(CliveryDecodeError):
            inflate_clivery(raw)

    def test_uncompressed_length_mismatch_is_rejected(self) -> None:
        payload = make_payload()
        raw = bytearray(wrap(payload))
        struct.pack_into("<I", raw, 4, len(payload) + 1)
        with self.assertRaises(CliveryDecodeError):
            inflate_clivery(raw)

    def test_non_vlrc_decompressed_payload_is_rejected(self) -> None:
        payload = b"xxxx" + b"\x00" * 100
        with self.assertRaises(CliveryDecodeError):
            inflate_clivery(wrap(payload))


if __name__ == "__main__":
    unittest.main()
