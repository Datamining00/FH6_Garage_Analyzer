from __future__ import annotations

import struct
import unittest
import uuid

from fh6garage.parsers import parse_forza_header


def _utf16(value: str) -> bytes:
    return struct.pack("<I", len(value)) + value.encode("utf-16le")


def _creator_relative_header(
    kind: str,
    car_id: int,
    identity: int,
    marker: bytes,
    *,
    trailing: bytes = b"",
) -> bytes:
    if len(marker) != 2:
        raise ValueError("marker must be exactly two bytes")

    common = (
        struct.pack("<HIHHHHH", 2026, 8, 31, 15, 45, 30, 500)
        + (b"\0" * 10)
        + struct.pack("<H", 3)
    )
    creator_tail = b"".join(
        (
            b"\0" * 28,
            marker,
            b"\0" * 7,
        )
    )
    if kind == "Tuning":
        creator_tail += struct.pack("<I", car_id)
        creator_tail += uuid.UUID(int=identity).bytes
    else:
        creator_tail += struct.pack("<I", 319)
        creator_tail += struct.pack("<I", car_id)
        creator_tail += uuid.UUID(int=identity).bytes

    return b"".join(
        (
            struct.pack("<I", 7),
            _utf16(f"{kind} structural"),
            _utf16("description"),
            common,
            _utf16("creator"),
            creator_tail,
            trailing,
        )
    )


class MarkerIndependentHeaderTests(unittest.TestCase):
    def test_livery_family_car_id_does_not_depend_on_marker_value(self) -> None:
        markers = (
            b"\x01\x00",
            b"\x01\x01",
            b"\x01\x02",
            b"\x7a\xb4",
            b"\xff\xff",
        )
        for kind in ("Livery", "BaseLivery", "SoulBoundLivery"):
            for index, marker in enumerate(markers, start=1):
                identity = 1000 + index
                with self.subTest(kind=kind, marker=marker.hex()):
                    header = parse_forza_header(
                        _creator_relative_header(
                            kind,
                            4234,
                            identity,
                            marker,
                            trailing=b"extra-trailing-bytes",
                        ),
                        kind,
                    )
                    self.assertEqual(header.car_id, 4234)
                    self.assertEqual(header.type_value, 319)
                    self.assertEqual(
                        header.asset_guid,
                        str(uuid.UUID(int=identity)),
                    )

    def test_tuning_car_id_does_not_depend_on_marker_value(self) -> None:
        markers = (
            b"\x01\x00",
            b"\x01\x01",
            b"\x01\x02",
            b"\x7a\xb4",
            b"\xff\xff",
        )
        for index, marker in enumerate(markers, start=1):
            identity = 2000 + index
            with self.subTest(marker=marker.hex()):
                header = parse_forza_header(
                    _creator_relative_header(
                        "Tuning",
                        1011,
                        identity,
                        marker,
                        trailing=b"extra-trailing-bytes",
                    ),
                    "Tuning",
                )
                self.assertEqual(header.car_id, 1011)
                self.assertIsNone(header.type_value)
                self.assertEqual(
                    header.asset_guid,
                    str(uuid.UUID(int=identity)),
                )


if __name__ == "__main__":
    unittest.main()
