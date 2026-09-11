from __future__ import annotations

import struct
import tempfile
import unittest
import uuid
from pathlib import Path

from fh6garage.auction_manifest_registry import read_auction_manifest_registry


def _write_manifest(
    path: Path,
    materialized: list[tuple[str, str]],
    registered: list[str],
    *,
    generation_id: int = 2535432012836245,
) -> None:
    data = bytearray(struct.pack("<II", 2, len(materialized)))
    for logical_name, guid_text in materialized:
        encoded = logical_name.encode("utf-8")
        data += struct.pack("<I", len(encoded))
        data += encoded
        data += uuid.UUID(guid_text).bytes_le

    data += struct.pack("<IQI", 1, generation_id, len(registered))
    for logical_name in registered:
        encoded = logical_name.encode("utf-8")
        data += struct.pack("<I", len(encoded))
        data += encoded

    # Third table mirrors currently materialized names in the captured FH6
    # manifests. The registry parser intentionally does not depend on it.
    data += struct.pack("<I", len(materialized))
    for logical_name, _guid_text in materialized:
        encoded = logical_name.encode("utf-8")
        data += struct.pack("<I", len(encoded))
        data += encoded

    path.write_bytes(data)


class AuctionManifestRegistryTests(unittest.TestCase):
    def test_registered_auction_identities_do_not_depend_on_hydration(self) -> None:
        registered = [
            "0368_bde1c885b0ea852euh9hw3skbs9pmf7vy7frhm14xkw_bigThumb.webp",
            "0625_02367890cc130b65ugcxs2tnrwzvm17p19vnqa6e7tw_bigThumb.webp",
            "2017_07d33fdb193f8b01bm0_bigThumb.webp",
        ]
        hydrated_one = [
            (
                "2017_07d33fdb193f8b01bm0_bigThumb.webp",
                "11111111-1111-4111-8111-111111111111",
            )
        ]
        hydrated_all = [
            (
                registered[0],
                "22222222-2222-4222-8222-222222222222",
            ),
            (
                registered[1],
                "33333333-3333-4333-8333-333333333333",
            ),
            hydrated_one[0],
        ]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "before.manifest"
            second = root / "after.manifest"
            _write_manifest(first, hydrated_one, registered)
            _write_manifest(second, hydrated_all, registered)

            before = read_auction_manifest_registry(root) if False else None
            # Use isolated cache directories because the public parser accepts
            # CacheThumbnails-like directories rather than manifest file paths.
            before_dir = root / "before"
            after_dir = root / "after"
            before_dir.mkdir()
            after_dir.mkdir()
            (before_dir / ".manifest").write_bytes(first.read_bytes())
            (after_dir / ".manifest").write_bytes(second.read_bytes())

            before = read_auction_manifest_registry(before_dir)
            after = read_auction_manifest_registry(after_dir)

            self.assertEqual(before.logical_names, after.logical_names)
            self.assertEqual(before.auction_identities, after.auction_identities)
            self.assertEqual(len(before.logical_names), 3)
            self.assertEqual(
                before.auction_identities,
                frozenset(
                    {
                        (368, "h9hw3skbs9pmf7vy7frhm14xkw"),
                        (625, "gcxs2tnrwzvm17p19vnqa6e7tw"),
                    }
                ),
            )
            self.assertEqual(before.generation_id, 2535432012836245)

    def test_trailing_materialized_table_is_not_required(self) -> None:
        registered = [
            "0368_bde1c885b0ea852euh9hw3skbs9pmf7vy7frhm14xkw_bigThumb.webp"
        ]
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            data = bytearray(struct.pack("<II", 2, 0))
            data += struct.pack("<IQI", 1, 7, len(registered))
            encoded = registered[0].encode("utf-8")
            data += struct.pack("<I", len(encoded)) + encoded
            (cache / ".manifest").write_bytes(data)

            registry = read_auction_manifest_registry(cache)
            self.assertEqual(
                registry.auction_identities,
                frozenset({(368, "h9hw3skbs9pmf7vy7frhm14xkw")}),
            )


if __name__ == "__main__":
    unittest.main()
