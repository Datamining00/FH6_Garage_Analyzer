from __future__ import annotations

import struct
import tempfile
import unittest
import uuid
from pathlib import Path

from fh6garage.models import HeaderInfo, LiveryRecord
from fh6garage.scan_result_processing import assign_auction_thumbnails


def _write_manifest(cache: Path, rows: list[tuple[str, str]]) -> None:
    data = bytearray(struct.pack("<II", 2, len(rows)))
    for logical_name, guid_text in rows:
        encoded = logical_name.encode("utf-8")
        data += struct.pack("<I", len(encoded))
        data += encoded
        data += uuid.UUID(guid_text).bytes_le
    (cache / ".manifest").write_bytes(data)


def _record(root: Path) -> LiveryRecord:
    container = root / "SoulBoundLivery_0365_20260621155524"
    container.mkdir()
    # Verified 2005 Subaru WRX STi SoulBound header tail/token pair from sample.
    (container / "header").write_bytes(
        b"\x00" * 131 + bytes.fromhex("9228254fc93c4a46a80e4396a9752c72")
    )
    return LiveryRecord(
        container_name=container.name,
        container_path=container,
        kind="SoulBoundLivery",
        header=HeaderInfo(car_id=365),
    )


class V132ExistingCandidateThumbnailTests(unittest.TestCase):
    def test_two_manifest_rows_resolve_when_only_one_webp_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = root / "cache"
            cache.mkdir()
            token = "j8m2aky97h54da0e8ebajx9ce8"
            guid_old = "8d75fc3a-20cd-4f6e-820c-9e8f5f7e0423"
            guid_live = "5f3942b1-bacd-4bea-ba8c-cc289aca120f"
            _write_manifest(
                cache,
                [
                    (f"0365_5bdb9c0b564fe7c2u{token}_bigThumb.webp", guid_old),
                    (f"0365_3005d1dd64f004a3u{token}_bigThumb.webp", guid_live),
                ],
            )
            (cache / f"{guid_live}.webp").write_bytes(b"RIFF-live")

            record = _record(root)
            stats = assign_auction_thumbnails([record], cache)

            self.assertEqual(record.thumbnail_path, cache / f"{guid_live}.webp")
            self.assertEqual(stats.matched, 1)
            self.assertEqual(stats.ambiguous, 0)
            self.assertEqual(stats.unmatched, 0)

    def test_two_existing_webps_remain_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = root / "cache"
            cache.mkdir()
            token = "j8m2aky97h54da0e8ebajx9ce8"
            guid_a = "8d75fc3a-20cd-4f6e-820c-9e8f5f7e0423"
            guid_b = "5f3942b1-bacd-4bea-ba8c-cc289aca120f"
            _write_manifest(
                cache,
                [
                    (f"0365_5bdb9c0b564fe7c2u{token}_bigThumb.webp", guid_a),
                    (f"0365_3005d1dd64f004a3u{token}_bigThumb.webp", guid_b),
                ],
            )
            (cache / f"{guid_a}.webp").write_bytes(b"RIFF-a")
            (cache / f"{guid_b}.webp").write_bytes(b"RIFF-b")

            record = _record(root)
            stats = assign_auction_thumbnails([record], cache)

            self.assertIsNone(record.thumbnail_path)
            self.assertEqual(stats.matched, 0)
            self.assertEqual(stats.ambiguous, 1)
            self.assertEqual(stats.unmatched, 1)

    def test_no_matching_manifest_token_is_not_guessed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = root / "cache"
            cache.mkdir()
            _write_manifest(cache, [])

            record = _record(root)
            stats = assign_auction_thumbnails([record], cache)

            self.assertIsNone(record.thumbnail_path)
            self.assertEqual(stats.matched, 0)
            self.assertEqual(stats.ambiguous, 0)
            self.assertEqual(stats.unmatched, 1)


if __name__ == "__main__":
    unittest.main()
