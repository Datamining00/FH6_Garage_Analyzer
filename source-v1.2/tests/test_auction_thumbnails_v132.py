from __future__ import annotations

import struct
import tempfile
import unittest
import uuid
from pathlib import Path

from fh6garage.auction_thumbnails import (
    assign_auction_thumbnails,
    auto_detect_thumbnail_cache,
    crockford32_rfc_encode,
    read_thumbnail_manifest,
)
from fh6garage.models import HeaderInfo, LiveryRecord


def _write_manifest(cache: Path, rows: list[tuple[str, str]]) -> None:
    data = bytearray(struct.pack("<II", 2, len(rows)))
    for logical_name, guid_text in rows:
        encoded = logical_name.encode("utf-8")
        data += struct.pack("<I", len(encoded))
        data += encoded
        data += uuid.UUID(guid_text).bytes_le
    # Real manifests have additional tables after the verified first table.
    data += b"EXTRA_TABLE_DATA"
    (cache / ".manifest").write_bytes(data)


def _record(
    root: Path,
    car_id: int,
    stamp: str,
    header_tail_hex: str,
) -> LiveryRecord:
    name = f"SoulBoundLivery_{car_id:04d}_{stamp}"
    container = root / name
    container.mkdir()
    raw_tail = bytes.fromhex(header_tail_hex)
    # Only the final 16 bytes are required by the verified thumbnail resolver.
    (container / "header").write_bytes(b"\x00" * 131 + raw_tail)
    return LiveryRecord(
        container_name=name,
        container_path=container,
        kind="SoulBoundLivery",
        header=HeaderInfo(car_id=car_id),
    )


class AuctionThumbnailManifestTests(unittest.TestCase):
    def test_windows_guid_mapping_and_trailing_tables(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            guid_text = "e02dd3df-4ef2-4bcd-a09d-033d2c40a037"
            _write_manifest(
                cache,
                [
                    (
                        "0625_02367890cc130b65ugcxs2tnrwzvm17p19vnqa6e7tw_bigThumb.webp",
                        guid_text,
                    )
                ],
            )
            entries = read_thumbnail_manifest(cache)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].car_id, 625)
            self.assertEqual(entries[0].instance_key, "02367890cc130b65")
            self.assertEqual(
                entries[0].livery_token,
                "gcxs2tnrwzvm17p19vnqa6e7tw",
            )
            self.assertEqual(entries[0].guid, guid_text)
            self.assertEqual(entries[0].path, cache / f"{guid_text}.webp")

    def test_verified_header_tokens(self) -> None:
        samples = {
            "833b916ab8e7f7409ec14eeb7519c7d7":
                "gcxs2tnrwzvm17p19vnqa6e7tw",
            "f10e5b8c7915a945bf7dc5d7d8406a7a":
                "y475q33s2pmmbfvxrqbxgg3af8",
            "dbeccf27d57b0a4f97a41257d4d885be":
                "vfpcy9ynfc54z5x429bx9p45qr",
            "8a63c1e66bca6d479f7e3bf11a049d9f":
                "h9hw3skbs9pmf7vy7frhm14xkw",
            "f72981b647b4cb48a9926dd973af8970":
                "ywmr3dj7pk5mhacjdqcq7bw9e0",
        }
        for raw_hex, expected in samples.items():
            with self.subTest(raw_hex=raw_hex):
                self.assertEqual(
                    crockford32_rfc_encode(bytes.fromhex(raw_hex)),
                    expected,
                )

    def test_duplicate_carordinal_uses_header_token_not_time_or_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = root / "cache"
            cache.mkdir()
            rows = [
                (
                    "0625_02367890cc130b65ugcxs2tnrwzvm17p19vnqa6e7tw_bigThumb.webp",
                    "e02dd3df-4ef2-4bcd-a09d-033d2c40a037",
                ),
                (
                    "0625_f4af82da733ea0eeuy475q33s2pmmbfvxrqbxgg3af8_bigThumb.webp",
                    "deb2d905-fa92-41fd-b834-e6ae7f1422f4",
                ),
            ]
            _write_manifest(cache, rows)
            for _logical_name, guid_text in rows:
                (cache / f"{guid_text}.webp").write_bytes(b"RIFF")

            older = _record(
                root,
                625,
                "20260822053159",
                "833b916ab8e7f7409ec14eeb7519c7d7",
            )
            newer = _record(
                root,
                625,
                "20260822055535",
                "f10e5b8c7915a945bf7dc5d7d8406a7a",
            )

            # Deliberately reverse input order. Exact header identity must win.
            stats = assign_auction_thumbnails([newer, older], cache)

            self.assertEqual(
                older.thumbnail_path,
                cache / "e02dd3df-4ef2-4bcd-a09d-033d2c40a037.webp",
            )
            self.assertEqual(
                newer.thumbnail_path,
                cache / "deb2d905-fa92-41fd-b834-e6ae7f1422f4.webp",
            )
            self.assertEqual(stats.matched_by_header_id, 2)
            self.assertEqual(stats.matched_by_time, 0)
            self.assertEqual(stats.matched_by_order, 0)
            self.assertEqual(stats.unmatched, 0)

    def test_368_soulbound_sample_maps_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = root / "cache"
            cache.mkdir()
            guid_text = "d8fec068-206b-41df-bbb5-8565148ef45d"
            _write_manifest(
                cache,
                [
                    (
                        "0368_bde1c885b0ea852euh9hw3skbs9pmf7vy7frhm14xkw_bigThumb.webp",
                        guid_text,
                    )
                ],
            )
            (cache / f"{guid_text}.webp").write_bytes(b"RIFF")
            record = _record(
                root,
                368,
                "20260822070520",
                "8a63c1e66bca6d479f7e3bf11a049d9f",
            )
            stats = assign_auction_thumbnails([record], cache)
            self.assertEqual(record.thumbnail_path, cache / f"{guid_text}.webp")
            self.assertEqual(stats.matched, 1)

    def test_ambiguous_same_car_and_token_is_not_guessed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = root / "cache"
            cache.mkdir()
            token = "gcxs2tnrwzvm17p19vnqa6e7tw"
            rows = [
                (
                    f"0625_1111111111111111u{token}_bigThumb.webp",
                    "11111111-1111-4111-8111-111111111111",
                ),
                (
                    f"0625_2222222222222222u{token}_bigThumb.webp",
                    "22222222-2222-4222-8222-222222222222",
                ),
            ]
            _write_manifest(cache, rows)
            for _name, guid_text in rows:
                (cache / f"{guid_text}.webp").write_bytes(b"RIFF")
            record = _record(
                root,
                625,
                "20260822053159",
                "833b916ab8e7f7409ec14eeb7519c7d7",
            )
            stats = assign_auction_thumbnails([record], cache)
            self.assertIsNone(record.thumbnail_path)
            self.assertEqual(stats.ambiguous, 1)
            self.assertEqual(stats.unmatched, 1)

    def test_missing_cached_webp_does_not_guess(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = root / "cache"
            cache.mkdir()
            _write_manifest(
                cache,
                [
                    (
                        "0625_02367890cc130b65ugcxs2tnrwzvm17p19vnqa6e7tw_bigThumb.webp",
                        "e02dd3df-4ef2-4bcd-a09d-033d2c40a037",
                    )
                ],
            )
            record = _record(
                root,
                625,
                "20260822053159",
                "833b916ab8e7f7409ec14eeb7519c7d7",
            )
            stats = assign_auction_thumbnails([record], cache)
            self.assertIsNone(record.thumbnail_path)
            self.assertEqual(stats.unmatched, 1)

    def test_auto_detects_known_fortebasegame_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp)
            valid = (
                local
                / "Packages"
                / "Microsoft.ForteBaseGame_8wekyb3d8bbwe"
                / "LocalCache"
                / "Local"
                / "LocalStorage_Cache"
                / "CacheThumbnails"
            )
            valid.mkdir(parents=True)
            (valid / ".manifest").write_bytes(struct.pack("<II", 2, 0))
            self.assertEqual(auto_detect_thumbnail_cache(local), valid)

    def test_auto_detects_alternate_microsoft_package_with_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp)
            valid = (
                local
                / "Packages"
                / "Microsoft.624F8B84B80_8wekyb3d8bbwe"
                / "LocalCache"
                / "Local"
                / "LocalStorage_Cache"
                / "CacheThumbnails"
            )
            valid.mkdir(parents=True)
            (valid / ".manifest").write_bytes(struct.pack("<II", 2, 0))
            self.assertEqual(auto_detect_thumbnail_cache(local), valid)

    def test_auto_detects_steam_candidate_only_when_manifest_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp)
            steam = (
                local
                / "ForzaHorizon6"
                / "LocalStorage_Cache"
                / "CacheThumbnails"
            )
            steam.mkdir(parents=True)
            self.assertIsNone(auto_detect_thumbnail_cache(local))
            (steam / ".manifest").write_bytes(struct.pack("<II", 2, 0))
            self.assertEqual(auto_detect_thumbnail_cache(local), steam)


if __name__ == "__main__":
    unittest.main()
