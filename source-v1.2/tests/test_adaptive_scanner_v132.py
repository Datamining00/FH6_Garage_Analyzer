from __future__ import annotations

import struct
import tempfile
import unittest
import uuid
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from fh6garage.models import LiveryRecord, TuningRecord
from fh6garage.runtime_policy import RuntimePolicy
from fh6garage.scanner import scan_save


def _utf16(value: str) -> bytes:
    encoded = value.encode("utf-16le")
    return struct.pack("<I", len(value)) + encoded


def _header(name: str, car_id: int, identity: int) -> bytes:
    common = (
        struct.pack("<HIHHHHH", 2026, 8, 25, 10, 20, 30, 40)
        + (b"\0" * 10)
        + struct.pack("<H", 3)
    )
    return b"".join(
        (
            struct.pack("<I", 7),
            _utf16(name),
            _utf16("description"),
            common,
            _utf16("creator"),
            b"\0" * 8,
            struct.pack("<I", 2),
            struct.pack("<I", car_id),
            uuid.UUID(int=identity).bytes,
        )
    )


class _CarDb:
    def is_known(self, car_id: int) -> bool:
        return 1 <= int(car_id) <= 9999

    def get(self, car_id: int):
        return type("Car", (), {"label": f"Car {car_id}"})()


def _normalized(result) -> dict[str, object]:
    def record(item: LiveryRecord | TuningRecord) -> tuple[object, ...]:
        return (
            type(item).__name__,
            item.container_name,
            getattr(item, "kind", "Tuning"),
            asdict(item.header),
            str(item.thumbnail_path or ""),
            str(getattr(item, "livery_path", None) or ""),
            str(getattr(item, "data_path", None) or ""),
            getattr(item, "content_sha256", ""),
            getattr(item, "data_size", 0),
        )

    return {
        "liveries": [record(item) for item in result.liveries],
        "tunings": [record(item) for item in result.tunings],
        "summaries": [asdict(item) for item in result.car_summaries],
        "counts": result.container_counts,
        "warnings": result.warnings,
    }


class AdaptiveScannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.save = self.root / "save"
        self.containers = self.save / "current" / "ContainersRoot"
        self.containers.mkdir(parents=True)
        for index in range(8):
            kind = "Tuning" if index == 7 else (
                "SoulBoundLivery" if index == 6 else "Livery"
            )
            car_id = 1000 + index
            folder = self.containers / f"{kind}_{car_id}_{index:02d}"
            folder.mkdir()
            (folder / "header").write_bytes(
                _header(f"Item {index}", car_id, index + 1)
            )
            if kind == "Tuning":
                (folder / "Data").write_bytes(b"tuning-data")
                (folder / "Thumb.png").write_bytes(b"not-an-image")
            else:
                (folder / "C_livery").write_bytes(
                    (f"livery-{index}".encode("ascii")) * 20
                )
                (folder / "bigThumb.webp").write_bytes(b"not-an-image")

        self.policy = RuntimePolicy(
            cpu_count=8,
            physical_memory_bytes=16 * 1024**3,
            scan_workers=4,
            pixmap_cache_bytes=64 * 1024**2,
            parallel_scan_min_items=1,
            parallel_scan_min_bytes=0,
        )
        self.db = _CarDb()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_threaded_and_sequential_results_are_identical(self) -> None:
        sequential = scan_save(
            self.save,
            self.db,
            runtime_policy=self.policy,
            cache_base_dir=self.root / "cache-sequential",
            backend="sequential",
        )
        threaded = scan_save(
            self.save,
            self.db,
            runtime_policy=self.policy,
            cache_base_dir=self.root / "cache-threaded",
            backend="threaded",
        )
        self.assertEqual(_normalized(sequential), _normalized(threaded))
        counters = threaded.diagnostics["scan"]["counters"]
        self.assertEqual(counters["scan_backend"], "threaded-io")
        self.assertEqual(counters["scan_workers"], 4)

    def test_warm_scan_hits_headers_and_livery_hashes(self) -> None:
        cache = self.root / "cache"
        scan_save(
            self.save,
            self.db,
            runtime_policy=self.policy,
            cache_base_dir=cache,
            backend="sequential",
        )
        warm = scan_save(
            self.save,
            self.db,
            runtime_policy=self.policy,
            cache_base_dir=cache,
            backend="sequential",
        )
        counters = warm.diagnostics["scan"]["counters"]
        self.assertEqual(counters["header_cache_hits"], 8)
        self.assertEqual(counters["header_cache_misses"], 0)
        self.assertEqual(counters["hash_cache_hits"], 7)
        self.assertEqual(counters["hash_cache_misses"], 0)

    def test_only_changed_files_miss_the_warm_cache(self) -> None:
        cache = self.root / "cache"
        scan_save(
            self.save,
            self.db,
            runtime_policy=self.policy,
            cache_base_dir=cache,
            backend="sequential",
        )
        changed = self.containers / "Livery_1000_00"
        (changed / "header").write_bytes(_header("Changed", 1000, 100))
        (changed / "C_livery").write_bytes(b"changed-content-size")

        result = scan_save(
            self.save,
            self.db,
            runtime_policy=self.policy,
            cache_base_dir=cache,
            backend="sequential",
        )
        counters = result.diagnostics["scan"]["counters"]
        self.assertEqual(counters["header_cache_hits"], 7)
        self.assertEqual(counters["header_cache_misses"], 1)
        self.assertEqual(counters["hash_cache_hits"], 6)
        self.assertEqual(counters["hash_cache_misses"], 1)

    def test_executor_failure_uses_legacy_sequential_fallback(self) -> None:
        with patch(
            "fh6garage.scanner.ThreadedScanBackend.run",
            side_effect=RuntimeError("executor unavailable"),
        ):
            result = scan_save(
                self.save,
                self.db,
                runtime_policy=self.policy,
                cache_base_dir=self.root / "cache",
                backend="threaded",
            )
        self.assertEqual(len(result.liveries), 7)
        self.assertEqual(len(result.tunings), 1)
        counters = result.diagnostics["scan"]["counters"]
        self.assertTrue(counters["scan_fallback_used"])
        self.assertEqual(counters["scan_backend"], "sequential")
        self.assertEqual(counters["scan_fallback_error"], "RuntimeError")

    def test_corrupt_cache_is_ignored_and_rebuilt(self) -> None:
        cache = self.root / "cache"
        scan_save(
            self.save,
            self.db,
            runtime_policy=self.policy,
            cache_base_dir=cache,
            backend="sequential",
        )
        cache_file = next(cache.glob("*.json"))
        cache_file.write_text("{not-json", encoding="utf-8")

        result = scan_save(
            self.save,
            self.db,
            runtime_policy=self.policy,
            cache_base_dir=cache,
            backend="sequential",
        )

        counters = result.diagnostics["scan"]["counters"]
        self.assertEqual(counters["header_cache_misses"], 8)
        self.assertEqual(counters["hash_cache_misses"], 7)
        self.assertEqual(len(result.liveries), 7)

    def test_unwritable_cache_location_does_not_block_scan(self) -> None:
        not_a_directory = self.root / "cache-file"
        not_a_directory.write_text("occupied", encoding="utf-8")

        result = scan_save(
            self.save,
            self.db,
            runtime_policy=self.policy,
            cache_base_dir=not_a_directory,
            backend="sequential",
        )

        self.assertEqual(len(result.liveries), 7)
        self.assertEqual(len(result.tunings), 1)
        self.assertEqual(not_a_directory.read_text(encoding="utf-8"), "occupied")

    def test_scan_does_not_modify_fh6_source_files(self) -> None:
        def snapshot() -> dict[str, tuple[int, int, bytes]]:
            return {
                str(path.relative_to(self.save)): (
                    path.stat().st_size,
                    path.stat().st_mtime_ns,
                    path.read_bytes(),
                )
                for path in self.save.rglob("*")
                if path.is_file()
            }

        before = snapshot()
        scan_save(
            self.save,
            self.db,
            runtime_policy=self.policy,
            cache_base_dir=self.root / "cache",
            backend="threaded",
        )
        self.assertEqual(before, snapshot())


if __name__ == "__main__":
    unittest.main()
