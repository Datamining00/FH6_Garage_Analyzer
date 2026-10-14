from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

from fh6garage.cache_housekeeping import (
    cleanup_stale_temp_files,
    prune_scan_cache_namespaces,
)


class CacheHousekeepingTests(unittest.TestCase):
    def test_stale_temp_cleanup_respects_grace_period(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = root / "old.tmp"
            recent = root / "recent.tmp"
            keep = root / "keep.json"
            old.write_bytes(b"old")
            recent.write_bytes(b"recent")
            keep.write_bytes(b"keep")
            timestamp = time.time() - 2 * 24 * 60 * 60
            os.utime(old, (timestamp, timestamp))

            stats = cleanup_stale_temp_files(root)

            self.assertFalse(old.exists())
            self.assertTrue(recent.exists())
            self.assertTrue(keep.exists())
            self.assertEqual(stats.removed_files, 1)
            self.assertEqual(stats.removed_bytes, 3)

    def test_namespace_pruning_keeps_active_and_four_recent_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            active = root / "active.json"
            active.write_text("active", encoding="utf-8")
            now = time.time()
            others: list[Path] = []
            for index in range(7):
                path = root / f"cache-{index}.json"
                path.write_text(str(index), encoding="utf-8")
                stamp = now - index * 60
                os.utime(path, (stamp, stamp))
                others.append(path)

            prune_scan_cache_namespaces(
                root,
                active_path=active,
                max_namespaces=5,
                max_age_days=30,
            )

            self.assertTrue(active.exists())
            self.assertEqual(
                {path.name for path in root.glob("*.json")},
                {"active.json", "cache-0.json", "cache-1.json", "cache-2.json", "cache-3.json"},
            )

    def test_namespace_pruning_removes_expired_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            active = root / "active.json"
            expired = root / "expired.json"
            active.write_text("active", encoding="utf-8")
            expired.write_text("expired", encoding="utf-8")
            stamp = time.time() - 31 * 24 * 60 * 60
            os.utime(expired, (stamp, stamp))

            stats = prune_scan_cache_namespaces(
                root,
                active_path=active,
                max_namespaces=5,
                max_age_days=30,
            )

            self.assertFalse(expired.exists())
            self.assertTrue(active.exists())
            self.assertEqual(stats.removed_files, 1)


if __name__ == "__main__":
    unittest.main()
