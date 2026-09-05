from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fh6garage import v1_3_4_card_polish_export_delete_patch as polish
from fh6garage.backup_export import SCHEMA, content_sha256, folder_fingerprint
from fh6garage.models import HeaderInfo, LiveryRecord


class CardPolishExportDeleteTests(unittest.TestCase):
    def _record(self, container: Path, *, kind: str = "Livery") -> LiveryRecord:
        return LiveryRecord(
            container_name=container.name,
            container_path=container,
            kind=kind,
            header=HeaderInfo(name="Unit", creator="Tester", car_id=1),
            livery_path=container / "C_livery",
        )

    @staticmethod
    def _write_container(path: Path, payload: bytes = b"unit") -> None:
        path.mkdir(parents=True)
        (path / "C_livery").write_bytes(payload)
        (path / "Thumb.png").write_bytes(b"thumb")

    def test_source_delete_resolves_current_and_numbered_save_copies(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            save_root = Path(temp) / "save"
            current = save_root / "current" / "ContainersRoot" / "Livery_1"
            numbered = save_root / "7" / "ContainersRoot" / "Livery_1"
            self._write_container(current)
            self._write_container(numbered)
            record = self._record(current)
            window = SimpleNamespace(
                result=SimpleNamespace(
                    metadata=SimpleNamespace(save_root=save_root, active_version="7")
                )
            )
            targets, error = polish._game_source_targets(window, record)
            self.assertEqual(error, "")
            self.assertEqual({path.resolve() for path in targets}, {current.resolve(), numbered.resolve()})

    def test_source_delete_rejects_conflicting_peer_and_soulbound(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            save_root = Path(temp) / "save"
            current = save_root / "current" / "ContainersRoot" / "Livery_1"
            numbered = save_root / "7" / "ContainersRoot" / "Livery_1"
            self._write_container(current, b"same")
            self._write_container(numbered, b"different")
            window = SimpleNamespace(
                result=SimpleNamespace(
                    metadata=SimpleNamespace(save_root=save_root, active_version="7")
                )
            )
            targets, error = polish._game_source_targets(window, self._record(current))
            self.assertEqual(targets, [])
            self.assertIn("content conflict", error)
            targets, error = polish._game_source_targets(
                window, self._record(current, kind="SoulBoundLivery")
            )
            self.assertEqual(targets, [])
            self.assertIn("normal Livery", error)

    def test_parking_failure_rolls_back_already_parked_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            first = base / "one" / "Livery_1"
            second = base / "two" / "Livery_1"
            self._write_container(first)
            self._write_container(second)
            # Make the second staging path unusable by occupying it with a file.
            (second.parent / polish._DELETE_STAGING).write_bytes(b"block")
            success, _error = polish._park_and_delete_targets([first, second])
            self.assertFalse(success)
            self.assertTrue(first.is_dir())
            self.assertTrue(second.is_dir())

    def test_backup_verification_requires_digest_and_full_folder_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "save" / "current" / "ContainersRoot" / "Livery_1"
            backup_root = base / "backup"
            backup = backup_root / "Livery" / "Tester" / "Livery_1"
            self._write_container(source, b"payload")
            self._write_container(backup, b"payload")
            record = self._record(source)
            digest = content_sha256(record)
            fingerprint = folder_fingerprint(source)
            payload = {
                "schema": SCHEMA,
                "entries": [{
                    "kind": "Livery",
                    "content_sha256": digest,
                    "folder_fingerprint": fingerprint,
                    "relative_path": backup.relative_to(backup_root).as_posix(),
                }],
            }
            backup_root.mkdir(exist_ok=True)
            (backup_root / "backup_index.json").write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(polish._verified_backup_path(backup_root, record), backup.resolve())
            (backup / "Thumb.png").write_bytes(b"changed")
            self.assertIsNone(polish._verified_backup_path(backup_root, record))

    def test_source_contract_uses_equal_spacer_rows_and_chunked_metadata(self) -> None:
        source = Path(polish.__file__).read_text(encoding="utf-8")
        self.assertIn("grid.setRowStretch(row, 0 if row % 2 == 0 else 1)", source)
        self.assertIn("row = slot * 2", source)
        self.assertIn("_METADATA_CHUNK = 16", source)
        self.assertIn("QTimer.singleShot(0", source)
        self.assertIn("_fh6_metadata_toggle_generation", source)
        self.assertIn("resolve_import_targets", source)
        self.assertIn("_park_and_delete_targets", source)

    def test_action_wording_enables_delete_and_installs_polish_before_profiler(self) -> None:
        root = Path(__file__).resolve().parents[1]
        wording = (root / "fh6garage" / "v1_3_4_backup_action_wording_patch.py").read_text(encoding="utf-8")
        app = (root / "app.py").read_text(encoding="utf-8")
        self.assertNotIn("delete.setEnabled(False)", wording)
        self.assertIn("_fh6_export_delete_source_requested", wording)
        self.assertLess(
            wording.index("apply_v1_3_4_card_polish_export_delete_patch(MainWindow)"),
            wording.index("apply_v1_3_4_performance_probe_patch(MainWindow)"),
        )
        self.assertLess(
            app.index("apply_v1_3_4_backup_action_wording_patch(MainWindow)"),
            app.index("apply_v1_3_2_thread_affinity_fix(MainWindow)"),
        )


if __name__ == "__main__":
    unittest.main()
