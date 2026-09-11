import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QWidget, QLabel, QToolButton, QLineEdit
from shiboken6 import delete

from fh6garage.app_options import AppOptions
from fh6garage.application_controls import apply_card_options
from fh6garage.completion_refresh import request_refresh
from fh6garage.livery_watch import Observation
from fh6garage.refresh_history import process_livery_refresh, _snapshot_entry
import test_livery_watch


class RequestedUpdateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.fixture = test_livery_watch.WatchTests()
        self.fixture.root = self.root

    def test_soulbound_add_change_partial_delete_ignored_regular_add_detected(self):
        regular = self.fixture.record(1)
        soul = replace(regular, kind='SoulBoundLivery', container_name='SoulBoundLivery_123_2')
        watch = Observation(self.root, [regular, soul])
        path = self.root / soul.container_name
        path.mkdir()
        (path / 'header').write_bytes(b'partial')
        watch.check(0)
        self.assertEqual(watch.check(3)[0].total, 0)
        (path / 'header').unlink()
        self.fixture.record(2)
        watch.check(6)
        diff, records = watch.check(9)
        self.assertEqual((len(diff.added), len(diff.removed)), (1, 0))
        self.assertTrue(all(r.kind == 'Livery' for r in records))

    def test_legacy_soulbound_snapshot_not_reported_deleted(self):
        from dataclasses import asdict
        regular = self.fixture.record(1)
        soul = replace(regular, kind='SoulBoundLivery', container_name='SoulBoundLivery_123_2')
        history = self.root / 'history'
        history.mkdir()
        (history / 'snapshot.json').write_text(json.dumps({
            'schema': 1, 'scope': str(self.root.resolve()).casefold(),
            'entries': [asdict(_snapshot_entry(r, history)) for r in (regular, soul)]}), encoding='utf8')
        result = NS(metadata=NS(save_root=self.root), liveries=[regular, soul])
        self.assertEqual(process_livery_refresh(result, history).total, 0)

    def test_defaults_match_requested_settings(self):
        options = AppOptions()
        for name in ('auto_livery_detection', 'show_download_date', 'show_hide_button',
                     'disable_export_cut', 'warn_applied_delete_move'):
            self.assertTrue(getattr(options, name), name)
        for name in ('auto_backup', 'render_cache', 'skip_vehicle_materials',
                     'show_auction_badge', 'backup_allow_different_name', 'backup_allow_duplicates'):
            self.assertFalse(getattr(options, name), name)
        self.assertEqual(options.render_workers, 0)

    def test_hide_disabled_keeps_position_and_auction_centered_after_resize(self):
        card = QWidget()
        self.addCleanup(lambda: delete(card))
        host = QWidget(card)
        host.resize(500, 300)
        card._fh6_image_label = QLabel(host)
        card._fh6_hide_button = QToolButton(host)
        card._fh6_auction_badge = QLabel(host)
        record = self.fixture.record(1)
        with patch('fh6garage.application_controls.load_options', return_value=AppOptions(
                show_hide_button=False, show_auction_badge=True)):
            apply_card_options(card, record)
        self.assertFalse(card._fh6_hide_button.isHidden())
        self.assertFalse(card._fh6_hide_button.isEnabled())
        badge = card._fh6_auction_badge
        self.assertEqual(badge.text(), 'Auction')
        self.assertEqual(badge.y(), host.height() - badge.height() - 6)
        self.assertLessEqual(abs(badge.geometry().center().x() - host.rect().center().x()), 1)
        host.resize(700, 350)
        card._fh6_auction_positioner.position()
        self.assertLessEqual(abs(badge.geometry().center().x() - host.rect().center().x()), 1)
        with patch('fh6garage.application_controls.load_options', return_value=AppOptions()):
            apply_card_options(card, record)
        self.assertTrue(card._fh6_hide_button.isEnabled())
        self.assertTrue(badge.isHidden())

    def window(self):
        window = QWidget()
        self.addCleanup(lambda: delete(window))
        window.path_edit = QLineEdit(str(self.root), window)
        window.calls = 0
        def refresh():
            window.calls += 1
        window.refresh_scan = refresh
        return window

    def test_completion_coalesces_and_waits_for_busy_work(self):
        window = self.window()
        window._fh6_export_running = True
        request_refresh(window)
        request_refresh(window)
        self.app.processEvents()
        self.assertEqual(window.calls, 0)
        window._fh6_export_running = False
        window._fh6_completion_refresh_timer.start(0)
        self.app.processEvents()
        self.assertEqual(window.calls, 1)
        self.assertFalse(window._fh6_completion_refresh_timer.isActive())

    def test_completion_cancels_after_path_change(self):
        window = self.window()
        request_refresh(window)
        window.path_edit.setText('')
        self.app.processEvents()
        self.assertEqual(window.calls, 0)
