from __future__ import annotations

import struct
import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fh6garage.auction_thumbnails import (
    assign_auction_thumbnails,
    auto_detect_thumbnail_cache,
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
    # Extra bytes deliberately emulate the real manifest's later tables.  The
    # parser must stop after the verified first table instead of interpreting it.
    data += b"EXTRA_TABLE_DATA"
    (cache / ".manifest").write_bytes(data)


def _record(car_id: int, stamp: str) -> LiveryRecord:
    name = f"SoulBoundLivery_{car_id:04d}_{stamp}"
    return LiveryRecord(
        container_name=name,
        container_path=Path(name),
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
            self.assertEqual(entries[0].guid, guid_text)
            self.assertEqual(entries[0].path, cache / f"{guid_text}.webp")

    def test_reinstall_style_equal_times_use_manifest_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            rows = [
                (
                    "0625_oldcacheentry_bigThumb.webp",
                    "11111111-1111-4111-8111-111111111111",
                ),
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

            older = _record(625, "20260822053159")
            newer = _record(625, "20260822055535")
            stats = assign_auction_thumbnails([newer, older], cache)

            self.assertEqual(
                older.thumbnail_path,
                cache / "e02dd3df-4ef2-4bcd-a09d-033d2c40a037.webp",
            )
            self.assertEqual(
                newer.thumbnail_path,
                cache / "deb2d905-fa92-41fd-b834-e6ae7f1422f4.webp",
            )
            self.assertEqual(stats.matched_by_order, 2)
            expected = datetime(
                2026, 8, 22, 5, 31, 59, tzinfo=timezone.utc
            ).timestamp()
            self.assertEqual(older.downloaded_at, expected)

    def test_auto_detects_fortebasegame_only_with_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp)
            invalid = (
                local
                / "Packages"
                / "Microsoft.ForteBaseGame_other"
                / "LocalCache"
                / "Local"
                / "LocalStorage_Cache"
                / "CacheThumbnails"
            )
            valid = (
                local
                / "Packages"
                / "Microsoft.ForteBaseGame_8wekyb3d8bbwe"
                / "LocalCache"
                / "Local"
                / "LocalStorage_Cache"
                / "CacheThumbnails"
            )
            invalid.mkdir(parents=True)
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
