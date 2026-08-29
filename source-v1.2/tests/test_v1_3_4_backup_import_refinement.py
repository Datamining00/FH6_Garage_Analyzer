from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fh6garage.backup_export import INDEX_NAME, export_records
from fh6garage.models import HeaderInfo, LiveryRecord
from fh6garage import v1_3_4_backup_import_refinement_patch as refine


class BackupImportBackendTests(unittest.TestCase):
    def _record(
        self,
        root: Path,
        name: str,
        *,
        kind: str = "Livery",
        creator: str = "Creator",
        payload: bytes = b"payload",
    ) -> LiveryRecord:
        container = root / name
        container.mkdir(parents=True)
        (container / "header").write_bytes(b"header")
        (container / "C_livery").write_bytes(payload)
        (container / "bigThumb.webp").write_bytes(b"thumb")
        return LiveryRecord(
            container_name=name,
            container_path=container,
            kind=kind,
            header=HeaderInfo(
                name="Example",
                creator=creator,
                car_id=123,
                guid=f"guid-{name}",
            ),
            thumbnail_path=container / "bigThumb.webp",
            livery_path=container / "C_livery",
        )

    def _save_layout(self, base: Path, version: str = "101") -> Path:
        save = base / "save"
        (save / "current" / "ContainersRoot").mkdir(parents=True)
        (save / version / "ContainersRoot").mkdir(parents=True)
        return save

    def _backup_entry(self, base: Path, record: LiveryRecord) -> tuple[Path, dict]:
        backup = base / "backup"
        summary = export_records(backup, [record])
        self.assertEqual(summary.failed, [])
        self.assertEqual(len(summary.exported), 1)
        return backup, summary.exported[0]

    def test_resolve_import_targets_uses_current_and_latest_numbered(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            save = self._save_layout(base, "101")
            (save / "205" / "ContainersRoot").mkdir(parents=True)
            current, numbered = refine.resolve_import_targets(save, "current")
            self.assertEqual(current, (save / "current" / "ContainersRoot").resolve())
            self.assertEqual(numbered, (save / "205" / "ContainersRoot").resolve())

    def test_resolve_import_targets_honors_active_numeric_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            save = self._save_layout(base, "101")
            (save / "205" / "ContainersRoot").mkdir(parents=True)
            _current, numbered = refine.resolve_import_targets(save, "101")
            self.assertEqual(numbered, (save / "101" / "ContainersRoot").resolve())

    def test_import_restores_exact_container_to_both_save_trees(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source_root = base / "game_source"
            record = self._record(source_root, "Livery_123_20260829010000")
            backup, entry = self._backup_entry(base, record)
            save = self._save_layout(base, "900")

            result = refine.import_backup_entry(backup, entry, save, "current")

            expected = record.container_name
            current = save / "current" / "ContainersRoot" / expected
            numbered = save / "900" / "ContainersRoot" / expected
            self.assertTrue((current / "C_livery").is_file())
            self.assertTrue((numbered / "C_livery").is_file())
            self.assertEqual((current / "C_livery").read_bytes(), b"payload")
            self.assertEqual((numbered / "C_livery").read_bytes(), b"payload")
            self.assertEqual(len(result.published), 2)
            self.assertEqual(result.already_present, [])
            self.assertFalse(result.source_deleted)

    def test_import_accepts_identical_existing_target_and_fills_missing_peer(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source_root = base / "game_source"
            record = self._record(source_root, "Livery_123_20260829010100")
            backup, entry = self._backup_entry(base, record)
            save = self._save_layout(base, "901")
            current = save / "current" / "ContainersRoot" / record.container_name
            current.mkdir()
            for item in record.container_path.iterdir():
                current.joinpath(item.name).write_bytes(item.read_bytes())

            result = refine.import_backup_entry(backup, entry, save, "current")

            numbered = save / "901" / "ContainersRoot" / record.container_name
            self.assertTrue(numbered.is_dir())
            self.assertEqual(len(result.already_present), 1)
            self.assertEqual(len(result.published), 1)

    def test_import_refuses_conflicting_existing_container_before_writing_peer(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source_root = base / "game_source"
            record = self._record(source_root, "Livery_123_20260829010200")
            backup, entry = self._backup_entry(base, record)
            save = self._save_layout(base, "902")
            current = save / "current" / "ContainersRoot" / record.container_name
            current.mkdir()
            (current / "header").write_bytes(b"different")
            (current / "C_livery").write_bytes(b"different")

            with self.assertRaises(refine.BackupRepositoryError):
                refine.import_backup_entry(backup, entry, save, "current")

            numbered = save / "902" / "ContainersRoot" / record.container_name
            self.assertFalse(numbered.exists())

    def test_import_refuses_tampered_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source_root = base / "game_source"
            record = self._record(source_root, "Livery_123_20260829010300")
            backup, entry = self._backup_entry(base, record)
            save = self._save_layout(base, "903")
            exported = backup / entry["relative_path"] / "C_livery"
            exported.write_bytes(b"tampered")

            with self.assertRaises(refine.BackupRepositoryError):
                refine.import_backup_entry(backup, entry, save, "current")

            self.assertFalse((save / "current" / "ContainersRoot" / record.container_name).exists())
            self.assertFalse((save / "903" / "ContainersRoot" / record.container_name).exists())

    def test_delete_source_occurs_only_after_successful_dual_restore(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source_root = base / "game_source"
            record = self._record(source_root, "SoulBoundLivery_123_20260829010400", kind="SoulBoundLivery")
            backup, entry = self._backup_entry(base, record)
            backup_container = backup / entry["relative_path"]
            save = self._save_layout(base, "904")

            result = refine.import_backup_entry(
                backup,
                entry,
                save,
                "current",
                delete_source=True,
            )

            self.assertTrue(result.source_deleted)
            self.assertFalse(backup_container.exists())
            index = json.loads((backup / INDEX_NAME).read_text(encoding="utf-8"))
            self.assertEqual(index["entries"], [])
            self.assertTrue((save / "current" / "ContainersRoot" / record.container_name).is_dir())
            self.assertTrue((save / "904" / "ContainersRoot" / record.container_name).is_dir())


class BackupExportReliabilityTests(unittest.TestCase):
    def _record(self, root: Path, name: str, payload: bytes) -> LiveryRecord:
        container = root / name
        container.mkdir(parents=True)
        (container / "header").write_bytes(b"header")
        (container / "C_livery").write_bytes(payload)
        return LiveryRecord(
            container_name=name,
            container_path=container,
            kind="Livery",
            header=HeaderInfo(name="Example", creator="Creator", car_id=1),
            livery_path=container / "C_livery",
        )

    def test_stale_index_entry_does_not_block_rebackup(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            record = self._record(base / "game", "Livery_1_1", b"same")
            backup = base / "backup"
            backup.mkdir()
            digest = refine.content_sha256(record)
            (backup / INDEX_NAME).write_text(
                json.dumps(
                    {
                        "schema": 1,
                        "entries": [
                            {
                                "kind": "Livery",
                                "content_sha256": digest,
                                "relative_path": "Livery/Creator/missing",
                                "original_container_name": record.container_name,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            summary = refine._safe_export_records(backup, [record])

            self.assertEqual(len(summary.exported), 1)
            self.assertEqual(summary.skipped, [])
            self.assertEqual(summary.failed, [])

    def test_batch_export_commits_index_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            first = self._record(base / "game", "Livery_1_1", b"one")
            second = self._record(base / "game", "Livery_1_2", b"two")
            backup = base / "backup"
            with patch.object(refine, "save_index", wraps=refine.save_index) as saver:
                summary = refine._safe_export_records(backup, [first, second])
            self.assertEqual(len(summary.exported), 2)
            self.assertEqual(summary.failed, [])
            self.assertEqual(saver.call_count, 1)


class BackupViewContractTests(unittest.TestCase):
    def test_backup_sort_reuses_cards_without_repository_rebuild(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (
            root / "fh6garage" / "v1_3_4_backup_import_refinement_patch.py"
        ).read_text(encoding="utf-8")
        body = source[source.index("def _set_backup_sort_cached"):source.index("def _backup_filter_allows")]
        self.assertIn("window._fh6_backup_cards.sort", body)
        self.assertIn("_relayout_backup(window)", body)
        self.assertNotIn("_rebuild_backup_cards", body)
        self.assertNotIn("backup_records", body)
        self.assertIn("_backup_ui._set_backup_sort = _set_backup_sort_cached", source)

    def test_backup_view_constructs_only_repository_records(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (
            root / "fh6garage" / "v1_3_4_backup_import_refinement_patch.py"
        ).read_text(encoding="utf-8")
        backup_items_body = source[source.index("def _backup_items"):source.index("def _status_counts")]
        self.assertIn("for entry, record in backup_records(root):", backup_items_body)
        self.assertNotIn("for record in game:", backup_items_body)
        self.assertIn('location = "both"', backup_items_body)

    def test_backup_toolbar_has_livery_style_show_row(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (
            root / "fh6garage" / "v1_3_4_backup_import_refinement_patch.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"표시:"', source)
        self.assertIn('"내 디자인 리버리"', source)
        self.assertIn('"경매장 리버리"', source)
        self.assertIn('"백업만"', source)
        self.assertIn('"게임 + 백업"', source)
        self.assertIn('button.setObjectName("secondary")', source)
        self.assertIn("_sync_backup_toolbar", source)

    def test_refinement_is_installed_from_existing_final_backup_layer(self) -> None:
        root = Path(__file__).resolve().parents[1]
        wording = (
            root / "fh6garage" / "v1_3_4_backup_action_wording_patch.py"
        ).read_text(encoding="utf-8")
        app = (root / "app.py").read_text(encoding="utf-8")
        self.assertIn("apply_v1_3_4_backup_import_refinement_patch(MainWindow)", wording)
        wording_call = app.index("apply_v1_3_4_backup_action_wording_patch(MainWindow)")
        affinity = app.index("apply_v1_3_2_thread_affinity_fix(MainWindow)")
        self.assertLess(wording_call, affinity)


if __name__ == "__main__":
    unittest.main()
