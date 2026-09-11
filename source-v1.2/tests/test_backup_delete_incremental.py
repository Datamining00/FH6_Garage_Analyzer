import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from PySide6.QtWidgets import QApplication, QWidget, QLabel, QGridLayout, QScrollArea, QMessageBox
from shiboken6 import delete
from fh6garage.models import HeaderInfo, LiveryRecord
from fh6garage.backup_export import save_index, load_index
from fh6garage import application_controls as controls
from fh6garage import v1_3_4_backup_lazy_load_patch as lazy
from fh6garage import v1_3_4_backup_export_patch as backup


class BackupDeleteIncrementalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.window = QWidget()
        self.addCleanup(lambda: delete(self.window))
        w = self.window
        w._show_status = Mock()
        w.backup_grid_layout = QGridLayout(w)
        w.backup_status_label = QLabel(w)
        w.backup_grid_scroll = QScrollArea(w)
        w.backup_grid_scroll.verticalScrollBar().setRange(0, 1000)
        w.backup_grid_scroll.verticalScrollBar().setValue(350)
        w._fh6_backup_cards = []
        w._fh6_backup_items_cache = []
        for i in range(3):
            name = f'backup-{i}'
            folder = self.root / name
            folder.mkdir()
            (folder / 'C_livery').write_bytes(b'data')
            record = LiveryRecord(container_name=name, container_path=folder, kind='Livery',
                                  header=HeaderInfo(name=name, creator='Tester', car_id=1),
                                  livery_path=folder / 'C_livery', content_sha256='same')
            entry = dict(relative_path=name, kind='Livery', original_container_name=name, content_sha256='same')
            card = QWidget(w)
            card._fh6_backup_entry = entry
            card.setProperty('backupRecord', record)
            card.setProperty('selected', i == 2)
            w.backup_grid_layout.addWidget(card, i, 0)
            w._fh6_backup_cards.append(card)
            w._fh6_backup_items_cache.append((entry, record, 'both'))
        save_index(self.root, {**load_index(self.root), 'entries': [x[0] for x in w._fh6_backup_items_cache]})
        w._fh6_backup_cache_signature = lazy._repository_signature(self.root)
        w._fh6_backup_lazy_loaded = True
        w._fh6_backup_cache_dirty = False
        self.game = [w._fh6_backup_items_cache[0][1]]
        for target, name, value in [
            (backup, '_backup_root', self.root), (backup, '_backup_path_is_safe', True),
            (backup, '_game_records', self.game), (controls, 'record_locked', False),
            (backup, '_relayout_backup', None), (backup, '_backup_columns', 2), (backup, '_refresh_backup_thumbnails', None), (backup, '_refresh_main_export_states', None),
            (QMessageBox, 'warning', None), (QMessageBox, 'question', QMessageBox.StandardButton.Yes),
        ]:
            mocked = patch.object(target, name, return_value=value)
            result = mocked.start()
            self.addCleanup(mocked.stop)
            if name == 'question': self.question = result
        self.rebuild = patch.object(backup, '_rebuild_backup_cards', side_effect=AssertionError('Full reload'))
        self.rebuild.start()
        self.addCleanup(self.rebuild.stop)

    def remove_first(self):
        controls._delete_card_backup(self.window, self.window._fh6_backup_cards[0])

    def test_success_reuses_survivors_and_preserves_selection_scroll_and_duplicate_presence(self):
        survivors = self.window._fh6_backup_cards[1:]
        with patch.object(lazy, '_record_from_entry', side_effect=AssertionError('Re-decode')):
            self.remove_first()
        self.assertEqual(self.window._fh6_backup_cards, survivors)
        self.assertEqual(self.window.backup_grid_layout.count(), 3)
        self.assertEqual(self.window.backup_grid_layout.getItemPosition(0)[:2], (0, 0))
        self.assertTrue(survivors[-1].property('selected'))
        self.assertEqual(self.window.backup_grid_scroll.verticalScrollBar().value(), 350)
        self.assertEqual(self.window._fh6_backup_cached_status, (2, 0, 2))
        self.assertIn(('livery', 'same'), self.window._fh6_backup_presence_cache[2])
        self.assertEqual(self.window._fh6_backup_cache_signature, lazy._repository_signature(self.root))
        self.assertFalse(self.window._fh6_backup_cache_dirty)
        self.assertEqual(len(load_index(self.root)['entries']), 2)

    def test_cancel_does_not_mutate_or_reload(self):
        self.question.return_value = QMessageBox.StandardButton.No
        self.remove_first()
        self.assertEqual(len(self.window._fh6_backup_cards), 3)
        self.assertEqual(len(load_index(self.root)['entries']), 3)

    def test_index_failure_preserves_cards_and_original(self):
        with patch('fh6garage.backup_delete.save_index', side_effect=OSError('full')):
            self.remove_first()
        self.assertEqual(len(self.window._fh6_backup_cards), 3)
        self.assertTrue((self.root / 'backup-0/C_livery').is_file())

    def test_cleanup_failure_reflects_committed_deletion_without_reload(self):
        with patch('fh6garage.backup_delete.shutil.rmtree', side_effect=OSError('busy')):
            self.remove_first()
        self.assertEqual(len(self.window._fh6_backup_cards), 2)
        self.assertEqual(len(load_index(self.root)['entries']), 2)
        self.assertTrue(list((self.root / '.delete_staging').iterdir()))

    def test_active_load_blocks_delete(self):
        self.window._fh6_backup_load_running = True
        self.remove_first()
        self.question.assert_not_called()
        self.assertEqual(len(load_index(self.root)['entries']), 3)

    def test_load_started_during_confirmation_blocks_delete(self):
        def confirm(*args):
            self.window._fh6_backup_load_running = True
            return QMessageBox.StandardButton.Yes
        self.question.side_effect = confirm
        self.remove_first()
        self.assertEqual(len(load_index(self.root)['entries']), 3)

    def test_last_deletion_clears_presence_and_updates_game_only_count(self):
        for _ in range(3): self.remove_first()
        self.assertEqual(self.window._fh6_backup_cards, [])
        self.assertEqual(self.window._fh6_backup_cached_status, (0, 1, 0))
        self.assertEqual(self.window._fh6_backup_presence_cache[2], set())

    def test_group_headers_and_cells_remain_in_place_until_refresh(self):
        w = self.window
        first, second = QLabel('first', w), QLabel('second', w)
        w._fh6_backup_headers = {'first': first, 'second': second}
        w._fh6_backup_group_mode = 'vehicle'
        w.backup_grid_layout.addWidget(first, 0, 0, 1, 2)
        w.backup_grid_layout.addWidget(w._fh6_backup_cards[0], 1, 0)
        w.backup_grid_layout.addWidget(second, 2, 0, 1, 2)
        for i, card in enumerate(w._fh6_backup_cards[1:]):
            card.setProperty('vehicleGroupLabel', 'Car')
            w.backup_grid_layout.addWidget(card, 3, i)
        self.remove_first()
        self.assertGreaterEqual(w.backup_grid_layout.indexOf(first), 0)
        self.assertEqual(second.text(), 'second')
        self.assertEqual(w.backup_grid_layout.count(), 5)

    def test_filtered_card_is_not_reintroduced(self):
        hidden = self.window._fh6_backup_cards[2]
        self.window.backup_grid_layout.removeWidget(hidden)
        hidden.hide()
        self.remove_first()
        self.assertIn(hidden, self.window._fh6_backup_cards)
        self.assertEqual(self.window.backup_grid_layout.indexOf(hidden), -1)
        self.assertTrue(hidden.isHidden())

    def test_active_layout_blocks_delete(self):
        self.window._fh6_backup_relayout_active = True
        self.remove_first()
        self.question.assert_not_called()
        self.assertEqual(len(load_index(self.root)['entries']), 3)

    def test_deleted_slot_is_hidden_disabled_and_alive_after_deferred_events(self):
        from PySide6.QtCore import QCoreApplication, QEvent
        from shiboken6 import isValid
        deleted = self.window._fh6_backup_cards[0]
        position = self.window.backup_grid_layout.getItemPosition(0)
        self.remove_first()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.assertTrue(isValid(deleted))
        self.assertTrue(deleted.isHidden())
        self.assertFalse(deleted.isEnabled())
        self.assertTrue(deleted.sizePolicy().retainSizeWhenHidden())
        self.assertEqual(self.window.backup_grid_layout.getItemPosition(0), position)
        self.assertIn(deleted, self.window._fh6_backup_deleted_slots)
        self.assertNotIn(deleted, self.window._fh6_backup_cards)

    def test_refresh_releases_deleted_slots(self):
        from PySide6.QtCore import QCoreApplication, QEvent
        from shiboken6 import isValid
        deleted = self.window._fh6_backup_cards[0]
        self.remove_first()
        items = self.window._fh6_backup_items_cache
        survivors = list(self.window._fh6_backup_cards)
        result = lazy._LoadResult(items, 2, 0, 2, lazy._repository_signature(self.root))
        with patch.object(backup, '_sync_backup_widths'), patch.object(lazy.QTimer, 'singleShot'):
            lazy._commit_cards(self.window, result, survivors, {id(c) for c in survivors})
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.assertFalse(isValid(deleted))
        self.assertEqual(self.window._fh6_backup_deleted_slots, [])