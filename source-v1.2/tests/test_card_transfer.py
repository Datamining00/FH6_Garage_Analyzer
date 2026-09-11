import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace as NS
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget, QFrame, QVBoxLayout, QPushButton, QToolButton
from shiboken6 import delete, isValid

from fh6garage import app_options
from fh6garage.backup_export import load_index
from fh6garage.backup_delete import delete_backup
from fh6garage.backup_policies import record_locked
from fh6garage.models import HeaderInfo, LiveryRecord
from fh6garage.v1_3_4_backup_import_refinement_patch import _safe_export_records, import_backup_entry
from fh6garage.card_transfer import CardSelection, visible_items, execute_transfer


class CardTransferTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.patch = patch.object(app_options, 'options_path', return_value=self.root / 'options.json')
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.widgets = []

    def tearDown(self):
        for widget in reversed(self.widgets):
            if isValid(widget):
                delete(widget)
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def record(self, name, data=None):
        folder = self.root / name
        folder.mkdir(exist_ok=True)
        (folder / 'C_livery').write_bytes(data or name.encode())
        (folder / 'header').write_bytes(name.encode())
        return LiveryRecord(container_name=name, container_path=folder, kind='Livery',
                            header=HeaderInfo(name=name, creator='Tester', car_id=1), livery_path=folder/'C_livery')

    def window(self):
        window = QWidget()
        self.widgets.append(window)
        layout = QVBoxLayout(window)
        window.livery_export_visible_button = QPushButton('내보내기')
        window.backup_export_button = QPushButton('내보내기')
        layout.addWidget(window.livery_export_visible_button)
        layout.addWidget(window.backup_export_button)
        records = [self.record('One'), self.record('Two')]
        window._livery_grid_cards = []
        for i, record in enumerate(records):
            card = QFrame()
            card.setMinimumSize(200, 100)
            card.setProperty('annotationKey', str(i))
            card.setProperty('backupRecord', record)
            card._fh6_backup_entry = {'relative_path': str(i)}
            layout.addWidget(card)
            window._livery_grid_cards.append(card)
        window._fh6_backup_cards = window._livery_grid_cards
        window._record_for_content_key = lambda kind, key: records[int(key)]
        window._content_annotation_key = lambda kind, record: record.container_name
        window.local_preferences = NS(get_bool=lambda key, default=False: False)
        window.show()
        self.app.processEvents()
        return window

    def test_concurrent_exports_keep_both_index_entries(self):
        records = [self.record('One'), self.record('Two')]
        barrier = Barrier(2)
        root = self.root / 'backup'
        def run(record):
            barrier.wait(timeout=5)
            return _safe_export_records(root, [record])
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(run, records))
        self.assertEqual(sum(len(r.exported) for r in results), 2)
        self.assertEqual(len(load_index(root)['entries']), 2)

    def test_concurrent_delete_and_export_keep_surviving_entry(self):
        root = self.root / 'backup'
        first = _safe_export_records(root, [self.record('One')]).exported[0]
        second = self.record('Two')
        barrier = Barrier(2)
        def remove():
            barrier.wait(timeout=5)
            delete_backup(root, first['relative_path'])
        def export():
            barrier.wait(timeout=5)
            return _safe_export_records(root, [second])
        with ThreadPoolExecutor(2) as pool:
            a, b = pool.submit(remove), pool.submit(export)
            a.result(timeout=10)
            self.assertEqual(len(b.result(timeout=10).exported), 1)
        self.assertEqual([e['name'] for e in load_index(root)['entries']], ['Two'])

    def test_same_content_sibling_does_not_inherit_lock(self):
        window = self.window()
        first, second = [window._record_for_content_key('livery', str(i)) for i in range(2)]
        first.content_sha256 = second.content_sha256 = 'same'
        window._livery_grid_cards[0].setProperty('fh6MoveLocked', True)
        self.assertTrue(record_locked(window, first))
        self.assertFalse(record_locked(window, second))

    def test_backup_lock_is_independent_of_game_key(self):
        window = self.window()
        record = window._record_for_content_key('livery', '0')
        window._fh6_backup_lock_paths = {str(record.container_path.resolve()).casefold()}
        window.local_preferences = NS(get_bool=lambda key, default=False: key.endswith('One'))
        self.assertFalse(record_locked(window, record))
        window.local_preferences = NS(get_bool=lambda key, default=False: 'backup-path::' in key)
        self.assertTrue(record_locked(window, record))

    def test_visible_items_respect_hidden_cards_both_directions(self):
        window = self.window()
        window._livery_grid_cards[1].hide()
        for direction in ('game', 'backup'):
            self.assertEqual(len(visible_items(window, direction)), 1)

    def test_card_click_border_and_cancel_restore_ui(self):
        window = self.window()
        selection = CardSelection(window, 'game', visible_items(window, 'game'))
        self.app.processEvents()
        QTest.mouseClick(selection.overlays[1], Qt.MouseButton.LeftButton)
        self.assertEqual(selection.selected, {1})
        self.assertIn('#7048f5', selection.overlays[1].styleSheet())
        self.assertTrue(selection.done.isEnabled())
        selection.cancel()
        self.assertIsNone(window._fh6_card_selection)
        self.assertTrue(window.livery_export_visible_button.isEnabled())

    def test_selection_finish_dispatches_only_selected_card(self):
        window = self.window()
        selection = CardSelection(window, 'backup', visible_items(window, 'backup'))
        QTest.mouseClick(selection.overlays[0], Qt.MouseButton.LeftButton)
        with patch('fh6garage.card_transfer.choose_policy', return_value='copy'), patch('fh6garage.card_transfer.execute_transfer') as run:
            selection.finish()
        self.assertEqual(len(run.call_args.args[2]), 1)
        self.assertEqual(run.call_args.args[2][0][1].container_name, 'One')

    def test_filter_change_cancels_selection(self):
        window = self.window()
        selection = CardSelection(window, 'game', visible_items(window, 'game'))
        window._livery_grid_cards[0].hide()
        selection.validate()
        self.assertIsNone(window._fh6_card_selection)

    def test_cut_disabled_prevents_dispatch(self):
        window = self.window()
        app_options.save_options(app_options.AppOptions(disable_export_cut=True))
        with patch('fh6garage.v1_3_4_backup_export_patch._request_export') as run:
            execute_transfer(window, 'game', visible_items(window, 'game'), 'cut')
        run.assert_not_called()

    def test_backend_cut_disabled_restores_but_preserves_backup(self):
        root = self.root / 'backup'
        entry = _safe_export_records(root, [self.record('One')]).exported[0]
        save = self.root/'save'
        for version in ('current','1'):
            (save/version/'ContainersRoot').mkdir(parents=True)
        app_options.save_options(app_options.AppOptions(disable_export_cut=True))
        result = import_backup_entry(root, entry, save, '1', delete_source=True)
        self.assertEqual(len(result.published), 2)
        self.assertFalse(result.source_deleted)
        self.assertTrue((root/entry['relative_path']).exists())

    def test_auction_lock_works_without_move_button(self):
        from fh6garage.v1_3_4_card_features_patch import _install_livery_lock
        window = self.window()
        card = QFrame(window)
        card._fh6_lock_placeholder_button = QToolButton(card)
        card._fh6_lock_placeholder_button.setCheckable(True)
        saved = {}
        window.local_preferences = NS(get_bool=lambda key, default=False: saved.get(key, default), set_bool=lambda k,v: saved.update({k:v}))
        _install_livery_lock(window, card, 'auction')
        card._fh6_lock_placeholder_button.setChecked(True)
        self.assertTrue(card.property('fh6MoveLocked'))
        self.assertTrue(saved['livery_move_locked::auction'])

    def test_header_only_change_triggers_automatic_scan(self):
        from fh6garage.application_controls import ApplicationController
        window = self.window()
        record = self.record('Livery_123')
        window.result = NS(metadata=NS(containers_root=self.root), liveries=[record])
        calls = []
        window.refresh_scan = lambda: calls.append(True)
        controller = ApplicationController(window)
        controller.timer.stop()
        controller.poll()
        (record.container_path/'header').write_bytes(b'changed name only')
        controller.poll()
        self.assertEqual(calls, [True])

    def test_auto_backup_does_not_start_during_external_import(self):
        from fh6garage.application_controls import ApplicationController
        window = self.window()
        window._fh6_external_import_running = True
        window.result = NS(liveries=[])
        app_options.save_options(app_options.AppOptions(auto_backup=True))
        controller = ApplicationController(window)
        controller.timer.stop()
        with patch.object(controller, 'start_backup') as start:
            controller.poll()
        start.assert_not_called()

    def test_single_import_rechecks_lock_after_confirmation(self):
        from fh6garage import v1_3_4_backup_import_refinement_patch as ref
        window = self.window()
        window._show_status = lambda *args: None
        record = window._record_for_content_key('livery', '0')
        def confirm(*args):
            window._livery_grid_cards[0].setProperty('fh6MoveLocked', True)
            return 'delete'
        with patch.object(ref._backup_ui, '_backup_root', return_value=self.root), patch.object(ref, '_import_context', return_value=(self.root, '1')), patch.object(ref, '_confirm_import_policy', side_effect=confirm), patch.object(ref, '_ImportWorker') as worker:
            ref._request_import(window, record, {})
        worker.assert_not_called()

    def test_batch_cut_keeps_locked_source_in_payload(self):
        from fh6garage import card_transfer as transfer
        window = self.window()
        window._begin_busy = lambda *args: None
        window._livery_grid_cards[0].setProperty('fh6MoveLocked', True)
        with patch('fh6garage.v1_3_4_backup_export_patch._backup_root', return_value=self.root), patch('fh6garage.v1_3_4_backup_export_patch._backup_path_is_safe', return_value=True), patch('fh6garage.v1_3_4_backup_import_refinement_patch._import_context', return_value=(self.root, '1')), patch('fh6garage.v1_3_4_backup_import_refinement_patch.resolve_import_targets'), patch.object(transfer.ImportBatch, 'start'):
            execute_transfer(window, 'backup', visible_items(window, 'backup'), 'cut')
        self.assertEqual([item[2] for item in window._fh6_import_batch.worker.items], [False, True])

    def test_backup_rebinding_persists_new_identity(self):
        from fh6garage.v1_3_4_card_features_patch import _install_livery_lock
        window = self.window()
        card = QFrame(window)
        card._fh6_lock_placeholder_button = QToolButton(card)
        card._fh6_lock_placeholder_button.setCheckable(True)
        saved = {}
        window.local_preferences = NS(get_bool=lambda key, default=False: saved.get(key, default), set_bool=lambda k,v: saved.update({k:v}))
        _install_livery_lock(window, card, 'temporary-card-key')
        _install_livery_lock(window, card, 'backup-path::unique')
        card._fh6_lock_placeholder_button.setChecked(True)
        self.assertEqual(saved, {'livery_move_locked::backup-path::unique': True})
