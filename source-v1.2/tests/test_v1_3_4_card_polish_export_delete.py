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
        livery = container / "C_livery"
        return LiveryRecord(
            container_name=container.name,
            container_path=container,
            kind=kind,
            header=HeaderInfo(name="Unit", creator="Tester", car_id=1),
            livery_path=livery,
        )

    def test_source_delete_requires_exact_containers_root_descendant(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            containers = root / "ContainersRoot"
            source = containers / "Livery_1"
            source.mkdir(parents=True)
            (source / "C_livery").write_bytes(b"unit")
            record = self._record(source)
            window = SimpleNamespace(result=SimpleNamespace(metadata=SimpleNamespace(containers_root=containers)))
            self.assertEqual(polish._safe_source_path(window, record), source.resolve())

            outside = root / "Outside"
            outside.mkdir()
            (outside / "C_livery").write_bytes(b"unit")
            self.assertIsNone(polish._safe_source_path(window, self._record(outside)))
            self.assertIsNone(polish._safe_source_path(window, self._record(source, kind="SoulBoundLivery")))

    def test_backup_verification_requires_digest_and_full_folder_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "save" / "ContainersRoot" / "Livery_1"
            backup_root = base / "backup"
            backup = backup_root / "Livery" / "Tester" / "Livery_1"
            source.mkdir(parents=True)
            backup.mkdir(parents=True)
            (source / "C_livery").write_bytes(b"payload")
            (source / "Thumb.png").write_bytes(b"thumb")
            (backup / "C_livery").write_bytes(b"payload")
            (backup / "Thumb.png").write_bytes(b"thumb")
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
