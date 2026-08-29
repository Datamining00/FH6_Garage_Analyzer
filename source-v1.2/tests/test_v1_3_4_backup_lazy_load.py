from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fh6garage.backup_export import INDEX_NAME
from fh6garage.models import HeaderInfo, LiveryRecord
from fh6garage.v1_3_4_backup_lazy_load_patch import (
    BackupLoadCancelled,
    _CancelToken,
    _cached_perf_items,
    _load_repository_items,
    _repository_signature,
)


class BackupLazyLoadTests(unittest.TestCase):
    @staticmethod
    def _game_record(name: str, digest: str = "") -> LiveryRecord:
        return LiveryRecord(
            container_name=name,
            container_path=Path("C:/game") / name,
            kind="Livery",
            header=HeaderInfo(name=name, creator="Creator", car_id=10),
            content_sha256=digest,
        )

    @staticmethod
    def _entry(name: str, relative: str, digest: str = "") -> dict[str, object]:
        return {
            "kind": "Livery",
            "original_container_name": name,
            "relative_path": relative,
            "name": name,
            "creator": "Creator",
            "car_id": 10,
            "content_sha256": digest,
            "thumbnail_relative": "",
            "preview_relative": "",
        }

    def test_repository_loader_is_cancellable_before_io(self) -> None:
        token = _CancelToken()
        token.cancel()
        with self.assertRaises(BackupLoadCancelled):
            _load_repository_items(None, [], token)

    def test_repository_loader_matches_game_and_reports_game_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = root / "Livery" / "Creator" / "backup-a"
            second = root / "Livery" / "Creator" / "backup-b"
            first.mkdir(parents=True)
            second.mkdir(parents=True)
            (first / "C_livery").write_bytes(b"a")
            (second / "C_livery").write_bytes(b"b")
            entries = [
                self._entry("same", str(first.relative_to(root)), "abc"),
                self._entry("backup-only", str(second.relative_to(root)), "def"),
            ]
            (root / INDEX_NAME).write_text(
                json.dumps({"entries": entries}),
                encoding="utf-8",
            )
            game_same = self._game_record("same", "abc")
            game_only = self._game_record("game-only", "xyz")

            result = _load_repository_items(root, [game_same, game_only], _CancelToken())

            self.assertEqual(result.total_backup, 2)
            self.assertEqual(result.both, 1)
            self.assertEqual(result.game_only, 1)
            self.assertEqual([location for _entry, _record, location in result.items], ["both", "backup"])
            self.assertEqual(result.signature, _repository_signature(root))

    def test_cached_perf_items_never_reads_repository_before_first_tab_load(self) -> None:
        class Owner:
            _fh6_backup_lazy_loaded = False
            _fh6_backup_cache_dirty = True

        game = [self._game_record("game")]
        with patch(
            "fh6garage.v1_3_4_backup_lazy_load_patch._backup_ui._game_records",
            return_value=game,
        ), patch(
            "fh6garage.v1_3_4_backup_lazy_load_patch.load_index",
            side_effect=AssertionError("repository must not be read"),
        ):
            self.assertEqual(_cached_perf_items(Owner()), [(None, game[0], "game")])

    def test_patch_contract_suppresses_eager_rebuild_and_preserves_final_patch_order(self) -> None:
        root = Path(__file__).resolve().parents[1]
        lazy = (root / "fh6garage" / "v1_3_4_backup_lazy_load_patch.py").read_text(encoding="utf-8")
        wording = (root / "fh6garage" / "v1_3_4_backup_action_wording_patch.py").read_text(encoding="utf-8")
        app = (root / "app.py").read_text(encoding="utf-8")

        self.assertIn("_backup_ui._rebuild_backup_cards = _lazy_rebuild_request", lazy)
        self.assertIn("_ref._rebuild_backup_cards = _lazy_rebuild_request", lazy)
        self.assertIn("_toolbar._rebuild_backup_cards = _lazy_rebuild_request", lazy)
        self.assertIn("_backup_ui._open_backup_page = _open_backup_page", lazy)
        self.assertIn("dialog.canceled.connect(token.cancel)", lazy)
        self.assertIn("token.check()", lazy)
        self.assertIn("_fh6_backup_items_cache", lazy)
        self.assertIn("repository_read=0 card_create=0", lazy)
        self.assertLess(
            wording.index("apply_v1_3_4_backup_toolbar_followup_patch(MainWindow)"),
            wording.index("apply_v1_3_4_backup_lazy_load_patch(MainWindow)"),
        )
        self.assertLess(
            wording.index("apply_v1_3_4_backup_lazy_load_patch(MainWindow)"),
            wording.index("apply_v1_3_4_performance_probe_patch(MainWindow)"),
        )
        self.assertLess(
            app.index("apply_v1_3_4_backup_action_wording_patch(MainWindow)"),
            app.index("apply_v1_3_2_thread_affinity_fix(MainWindow)"),
        )


if __name__ == "__main__":
    unittest.main()
