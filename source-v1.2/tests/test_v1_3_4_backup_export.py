from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fh6garage.backup_export import (
    INDEX_NAME,
    backup_contains_record,
    backup_records,
    export_records,
)
from fh6garage.models import HeaderInfo, LiveryRecord


class BackupExportBackendTests(unittest.TestCase):
    def _record(
        self,
        root: Path,
        name: str,
        *,
        kind: str = "Livery",
        creator: str = "Creator_A",
        payload: bytes = b"same-livery-content",
    ) -> LiveryRecord:
        container = root / name
        container.mkdir(parents=True)
        (container / "header").write_bytes(b"header-bytes")
        (container / "C_livery").write_bytes(payload)
        (container / "bigThumb.webp").write_bytes(b"thumbnail")
        return LiveryRecord(
            container_name=name,
            container_path=container,
            kind=kind,
            header=HeaderInfo(
                name="Test Livery",
                creator=creator,
                car_id=123,
                guid=f"guid-{name}",
            ),
            thumbnail_path=container / "bigThumb.webp",
            livery_path=container / "C_livery",
        )

    def test_export_groups_by_kind_and_creator_and_deduplicates_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "game"
            backup = base / "backup"
            first = self._record(source, "Livery_123_20260829010000")
            second = self._record(source, "Livery_123_20260829010100")

            summary = export_records(backup, [first, second])

            self.assertEqual(len(summary.exported), 1)
            self.assertEqual(len(summary.skipped), 1)
            self.assertEqual(summary.failed, [])
            entry = summary.exported[0]
            exported_path = backup / entry["relative_path"]
            self.assertTrue(exported_path.is_dir())
            self.assertEqual(exported_path.parent.name, "Creator_A")
            self.assertEqual(exported_path.parent.parent.name, "Livery")
            self.assertTrue((exported_path / "C_livery").is_file())
            self.assertTrue(backup_contains_record(backup, second, hash_if_needed=True))

            index = json.loads((backup / INDEX_NAME).read_text(encoding="utf-8"))
            self.assertEqual(index["schema"], 1)
            self.assertEqual(len(index["entries"]), 1)
            restored = backup_records(backup)
            self.assertEqual(len(restored), 1)
            self.assertEqual(restored[0][1].header.creator, "Creator_A")

    def test_soulbound_uses_own_category_and_safe_creator_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "game"
            backup = base / "backup"
            record = self._record(
                source,
                "SoulBoundLivery_321_20260829010200",
                kind="SoulBoundLivery",
                creator="Painter/Name",
                payload=b"auction-livery",
            )

            summary = export_records(backup, [record])

            self.assertEqual(len(summary.exported), 1)
            self.assertEqual(summary.failed, [])
            exported_path = backup / summary.exported[0]["relative_path"]
            self.assertEqual(exported_path.parent.parent.name, "SoulBoundLivery")
            self.assertEqual(exported_path.parent.name, "Painter_Name")


class BackupExportPatchContractTests(unittest.TestCase):
    def test_patch_keeps_import_and_game_delete_read_only(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (root / "fh6garage" / "v1_3_4_backup_export_patch.py").read_text(encoding="utf-8")
        self.assertIn('delete.setEnabled(False)', source)
        self.assertIn('operation="import"', source)
        self.assertIn('"위치: 백업"', source)
        self.assertIn('"위치: 게임 + 백업"', source)
        self.assertIn('card_icon("import"', source)
        self.assertIn('card_icon("export"', source)
        self.assertNotIn("shutil.rmtree(record.container_path", source)

    def test_backup_patch_runs_before_final_thread_affinity_fix(self) -> None:
        app = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
        backup_call = app.index("apply_v1_3_4_backup_export_patch(MainWindow)")
        affinity_call = app.index("apply_v1_3_2_thread_affinity_fix(MainWindow)")
        self.assertLess(backup_call, affinity_call)


if __name__ == "__main__":
    unittest.main()
