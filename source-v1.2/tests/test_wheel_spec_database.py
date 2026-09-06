from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fh6garage.preview3d.wheel_spec_database import (
    WheelSpecDatabaseError,
    WheelSpecDatabaseSource,
    ensure_stock_wheel_database,
    stock_wheel_database_is_valid,
    stock_wheel_database_path,
)


def _source(data: bytes) -> WheelSpecDatabaseSource:
    blob = hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()
    sha256 = hashlib.sha256(data).hexdigest()
    return WheelSpecDatabaseSource(
        repository="fixture/repo",
        commit="fixture-commit",
        url="https://example.invalid/fh6_game_db.sqlite",
        size=len(data),
        git_blob_sha1=blob,
        sha256=sha256,
        cache_name="fixture.sqlite",
    )


class WheelSpecDatabaseRuntimeTests(unittest.TestCase):
    def test_reuses_verified_cached_database_without_network(self) -> None:
        data = b"SQLite format 3\0fixture-wheel-db"
        source = _source(data)
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            os.environ, {"LOCALAPPDATA": temp_dir}, clear=False
        ):
            target = stock_wheel_database_path(source)
            target.write_bytes(data)
            self.assertTrue(stock_wheel_database_is_valid(target, source))
            with patch("urllib.request.urlopen") as urlopen:
                resolved = ensure_stock_wheel_database(source=source)
            self.assertEqual(resolved, target)
            self.assertEqual(resolved.read_bytes(), data)
            urlopen.assert_not_called()

    def test_replaces_invalid_cached_database_with_verified_download(self) -> None:
        data = b"SQLite format 3\0fixture-wheel-db-valid"
        source = _source(data)
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            os.environ, {"LOCALAPPDATA": temp_dir}, clear=False
        ):
            target = stock_wheel_database_path(source)
            target.write_bytes(b"bad")
            progress: list[str] = []
            with patch("urllib.request.urlopen", return_value=io.BytesIO(data)):
                resolved = ensure_stock_wheel_database(progress.append, source=source)
            self.assertEqual(resolved, target)
            self.assertEqual(target.read_bytes(), data)
            self.assertTrue(stock_wheel_database_is_valid(target, source))
            self.assertTrue(any("integrity-verified" in item for item in progress))

    def test_rejects_download_with_wrong_identity_and_leaves_no_cache(self) -> None:
        expected = b"SQLite format 3\0expected"
        source = _source(expected)
        bad = b"SQLite format 3\0wrong---"
        self.assertEqual(len(expected), len(bad))
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            os.environ, {"LOCALAPPDATA": temp_dir}, clear=False
        ):
            target = stock_wheel_database_path(source)
            with patch("urllib.request.urlopen", return_value=io.BytesIO(bad)):
                with self.assertRaises(WheelSpecDatabaseError):
                    ensure_stock_wheel_database(source=source)
            self.assertFalse(target.exists())
            self.assertFalse(target.with_suffix(target.suffix + ".download").exists())


if __name__ == "__main__":
    unittest.main()
