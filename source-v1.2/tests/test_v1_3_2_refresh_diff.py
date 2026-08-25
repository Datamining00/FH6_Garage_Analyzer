from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import time
import unittest

from fh6garage.models import HeaderInfo, LiveryRecord, SaveMetadata, ScanResult
from fh6garage.refresh_history import cached_thumbnail_path, process_livery_refresh


class V132RefreshDiffTests(unittest.TestCase):
    def _result(self, save_root: Path, records: list[LiveryRecord]) -> ScanResult:
        metadata = SaveMetadata(
            selected_path=save_root,
            save_root=save_root,
            containers_root=save_root / "ContainersRoot",
        )
        return ScanResult(metadata=metadata, liveries=records)

    def _record(
        self,
        root: Path,
        container: str,
        *,
        name: str,
        guid: str,
        digest: str,
        thumb_bytes: bytes,
        kind: str = "Livery",
        creator: str = "Creator",
    ) -> LiveryRecord:
        container_path = root / container
        container_path.mkdir(parents=True, exist_ok=True)
        thumb = container_path / "bigThumb.webp"
        thumb.write_bytes(thumb_bytes)
        return LiveryRecord(
            container_name=container,
            container_path=container_path,
            kind=kind,
            header=HeaderInfo(
                name=name,
                creator=creator,
                car_id=100,
                guid=guid,
            ),
            thumbnail_path=thumb,
            livery_path=container_path / "C_livery",
            content_sha256=digest,
        )

    def test_first_scan_is_baseline_and_caches_thumbnail(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            save_root = root / "save"
            history = root / "history"
            record = self._record(
                save_root,
                "Livery_100_A",
                name="Alpha",
                guid="guid-a",
                digest="hash-a",
                thumb_bytes=b"thumb-a",
            )
            diff = process_livery_refresh(self._result(save_root, [record]), history)
            self.assertTrue(diff.baseline)
            self.assertEqual(diff.total, 0)
            snapshot = json.loads((history / "snapshot.json").read_text(encoding="utf-8"))
            self.assertEqual(len(snapshot["entries"]), 1)
            cached_name = snapshot["entries"][0]["thumbnail_cache"]
            self.assertTrue((history / "thumbnails" / cached_name).is_file())
            self.assertEqual(diff.cache_files, 1)
            self.assertEqual(diff.cache_bytes, len(b"thumb-a"))

    def test_stale_temp_file_is_cleaned_automatically(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            save_root = root / "save"
            history = root / "history"
            thumbnails = history / "thumbnails"
            thumbnails.mkdir(parents=True)
            stale = thumbnails / "interrupted.tmp"
            stale.write_bytes(b"stale")
            stamp = time.time() - 2 * 24 * 60 * 60
            os.utime(stale, (stamp, stamp))
            record = self._record(
                save_root,
                "Livery_100_A",
                name="Alpha",
                guid="guid-a",
                digest="hash-a",
                thumb_bytes=b"thumb-a",
            )

            diff = process_livery_refresh(
                self._result(save_root, [record]),
                history,
            )

            self.assertFalse(stale.exists())
            self.assertEqual(diff.cleanup_removed_files, 1)
            self.assertEqual(diff.cleanup_removed_bytes, len(b"stale"))

    def test_added_removed_changed_keep_required_thumbnails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            save_root = root / "save"
            history = root / "history"
            removed = self._record(
                save_root,
                "Livery_100_A",
                name="Removed",
                guid="guid-a",
                digest="hash-a",
                thumb_bytes=b"thumb-removed",
            )
            changed_old = self._record(
                save_root,
                "Livery_100_B",
                name="Before",
                guid="guid-b",
                digest="hash-b-old",
                thumb_bytes=b"thumb-before",
            )
            process_livery_refresh(self._result(save_root, [removed, changed_old]), history)

            # Simulate FH6 replacing/removing the original files before refresh.
            removed.thumbnail_path.unlink()
            changed_old.thumbnail_path.unlink()

            changed_new = self._record(
                save_root,
                "Livery_100_B",
                name="After",
                guid="guid-b",
                digest="hash-b-new",
                thumb_bytes=b"thumb-after",
            )
            added = self._record(
                save_root,
                "Livery_100_C",
                name="Added",
                guid="guid-c",
                digest="hash-c",
                thumb_bytes=b"thumb-added",
            )
            diff = process_livery_refresh(
                self._result(save_root, [changed_new, added]),
                history,
            )

            self.assertFalse(diff.baseline)
            self.assertEqual(len(diff.added), 1)
            self.assertEqual(len(diff.removed), 1)
            self.assertEqual(len(diff.changed), 1)
            self.assertEqual(diff.removed[0].before.name, "Removed")
            self.assertEqual(diff.changed[0].before.name, "Before")
            self.assertEqual(diff.changed[0].after.name, "After")

            removed_thumb = cached_thumbnail_path(diff.removed[0].before, history)
            before_thumb = cached_thumbnail_path(diff.changed[0].before, history)
            after_thumb = cached_thumbnail_path(diff.changed[0].after, history)
            added_thumb = cached_thumbnail_path(diff.added[0].after, history)
            self.assertIsNotNone(removed_thumb)
            self.assertIsNotNone(before_thumb)
            self.assertIsNotNone(after_thumb)
            self.assertIsNotNone(added_thumb)
            self.assertEqual(removed_thumb.read_bytes(), b"thumb-removed")
            self.assertEqual(before_thumb.read_bytes(), b"thumb-before")
            self.assertEqual(after_thumb.read_bytes(), b"thumb-after")

    def test_unique_guid_reconciles_container_rename_as_change(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            save_root = root / "save"
            history = root / "history"
            old = self._record(
                save_root,
                "Livery_100_OLD",
                name="Same",
                guid="same-guid",
                digest="same-hash",
                thumb_bytes=b"same-thumb",
            )
            process_livery_refresh(self._result(save_root, [old]), history)
            new = self._record(
                save_root,
                "Livery_100_NEW",
                name="Same",
                guid="same-guid",
                digest="same-hash",
                thumb_bytes=b"same-thumb",
            )
            diff = process_livery_refresh(self._result(save_root, [new]), history)
            self.assertEqual(len(diff.added), 0)
            self.assertEqual(len(diff.removed), 0)
            self.assertEqual(len(diff.changed), 1)

    def test_different_save_root_starts_new_baseline(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            history = root / "history"
            save_a = root / "save-a"
            save_b = root / "save-b"
            first = self._record(
                save_a,
                "Livery_100_A",
                name="A",
                guid="a",
                digest="a",
                thumb_bytes=b"a",
            )
            process_livery_refresh(self._result(save_a, [first]), history)
            second = self._record(
                save_b,
                "Livery_100_B",
                name="B",
                guid="b",
                digest="b",
                thumb_bytes=b"b",
            )
            diff = process_livery_refresh(self._result(save_b, [second]), history)
            self.assertTrue(diff.baseline)
            self.assertEqual(diff.total, 0)

    def test_refresh_diff_is_integrated_into_population(self):
        app_text = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
        self.assertNotIn("apply_v1_3_2_refresh_diff_patch", app_text)
        ui_text = (Path(__file__).resolve().parents[1] / "fh6garage" / "ui.py").read_text(encoding="utf-8")
        self.assertIn("update_livery_refresh_diff(self)", ui_text)


if __name__ == "__main__":
    unittest.main()
