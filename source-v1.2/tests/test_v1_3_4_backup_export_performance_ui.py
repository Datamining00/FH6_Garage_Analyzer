from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fh6garage.models import HeaderInfo, LiveryRecord
from fh6garage import v1_3_4_backup_export_performance_ui_patch as perf


class BackupExportPerformanceTests(unittest.TestCase):
    def _record(self, root: Path, name: str, payload: bytes = b"payload") -> LiveryRecord:
        container = root / name
        container.mkdir(parents=True)
        (container / "header").write_bytes(b"header")
        (container / "C_livery").write_bytes(payload)
        (container / "bigThumb.webp").write_bytes(b"thumb")
        return LiveryRecord(
            container_name=name,
            container_path=container,
            kind="Livery",
            header=HeaderInfo(
                name="Example",
                creator="Creator",
                car_id=123,
                guid=f"guid-{name}",
            ),
            thumbnail_path=container / "bigThumb.webp",
            livery_path=container / "C_livery",
        )

    def test_fast_export_verifies_source_and_staging_without_third_full_reread(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "game"
            backup = base / "backup"
            record = self._record(source, "Livery_123_1")
            original = perf.folder_fingerprint
            calls: list[Path] = []

            def counted(path: Path) -> str:
                calls.append(Path(path))
                return original(Path(path))

            with patch.object(perf, "folder_fingerprint", side_effect=counted):
                summary = perf._fast_export_records(backup, [record])

            self.assertEqual(len(summary.exported), 1)
            self.assertEqual(summary.failed, [])
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[0], record.container_path)
            self.assertEqual(calls[1].parent.name, ".staging")

    def test_presence_snapshot_reuses_one_loaded_index(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            backup = base / "backup"
            backup.mkdir()

            class Settings:
                def value(self, *_args):
                    return str(backup)

            class Window:
                backup_path_edit = None
                settings = Settings()
                _fh6_backup_presence_cache = ("", set(), set())

            window = Window()
            with patch.object(perf, "load_index", wraps=perf.load_index) as loader:
                perf._presence_snapshot(window)
                perf._presence_snapshot(window)
            self.assertEqual(loader.call_count, 1)


class BackupExportUiContractTests(unittest.TestCase):
    def test_game_only_backup_action_is_named_backup(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (
            root / "fh6garage" / "v1_3_4_backup_export_performance_ui_patch.py"
        ).read_text(encoding="utf-8")
        self.assertIn('if location == "game":', source)
        self.assertIn('"백업하기"', source)
        self.assertIn('card_icon("export"', source)
        self.assertIn('button.setEnabled(True)', source)

    def test_backup_filter_uses_same_active_style_contract_as_livery(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (
            root / "fh6garage" / "v1_3_4_backup_export_performance_ui_patch.py"
        ).read_text(encoding="utf-8")
        self.assertIn("_FILTER_BUTTON_STYLE", source)
        self.assertIn('setProperty("fh6FilterActive", mode != "all")', source)
        self.assertIn("_connect_debounced_search", source)

    def test_followup_stays_before_final_thread_affinity_fix(self) -> None:
        app = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
        thread_fix = app.index("apply_v1_3_4_backup_export_thread_fix_patch(MainWindow)")
        followup = app.index("apply_v1_3_4_backup_export_performance_ui_patch(MainWindow)")
        affinity = app.index("apply_v1_3_2_thread_affinity_fix(MainWindow)")
        self.assertLess(thread_fix, followup)
        self.assertLess(followup, affinity)


if __name__ == "__main__":
    unittest.main()
