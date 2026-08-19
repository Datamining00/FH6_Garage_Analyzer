from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fh6garage.livery_hash_cache import (
    enrich_sha256,
    lookup_cached_sha256,
    reset_hash_cache_state_for_tests,
)


class LiveryHashCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.cache = self.root / "cache.json"
        self.env = patch.dict(os.environ, {"FH6_ASSISTANT_HASH_CACHE": str(self.cache)})
        self.env.start()
        reset_hash_cache_state_for_tests()

    def tearDown(self) -> None:
        reset_hash_cache_state_for_tests()
        self.env.stop()
        self.temp.cleanup()

    def test_missing_digest_is_computed_once_then_reused_from_stat_cache(self) -> None:
        source = self.root / "C_livery"
        source.write_bytes(b"abc" * 1000)
        expected = hashlib.sha256(source.read_bytes()).hexdigest()

        self.assertEqual(lookup_cached_sha256(source), "")
        mapping, stats = enrich_sha256([source])
        self.assertEqual(stats["computed"], 1)
        self.assertEqual(stats["cache_hits"], 0)
        self.assertIn(expected, mapping.values())
        self.assertEqual(lookup_cached_sha256(source), expected)

        mapping2, stats2 = enrich_sha256([source])
        self.assertEqual(stats2["computed"], 0)
        self.assertEqual(stats2["cache_hits"], 1)
        self.assertIn(expected, mapping2.values())

    def test_file_change_invalidates_cached_digest_without_trusting_old_hash(self) -> None:
        source = self.root / "C_livery"
        source.write_bytes(b"first")
        first, _stats = enrich_sha256([source])
        first_digest = next(iter(first.values()))
        self.assertEqual(lookup_cached_sha256(source), first_digest)

        source.write_bytes(b"second-and-different-size")
        self.assertEqual(lookup_cached_sha256(source), "")
        second, stats = enrich_sha256([source])
        second_digest = next(iter(second.values()))
        self.assertNotEqual(first_digest, second_digest)
        self.assertEqual(stats["computed"], 1)

    def test_duplicate_paths_are_hashed_only_once_per_batch(self) -> None:
        source = self.root / "C_livery"
        source.write_bytes(b"payload")
        _mapping, stats = enrich_sha256([source, source, source])
        self.assertEqual(stats["paths"], 1)
        self.assertEqual(stats["computed"], 1)


if __name__ == "__main__":
    unittest.main()
