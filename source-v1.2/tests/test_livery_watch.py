import hashlib
import shutil
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

from fh6garage.livery_watch import Observation, fingerprint
from fh6garage.models import LiveryRecord
from fh6garage.parsers import read_header_file
from test_header_marker_independent import _creator_relative_header


class WatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def record(self, number, payload=None):
        path = self.root / f'Livery_123_{number}'
        path.mkdir(exist_ok=True)
        (path / 'header').write_bytes(_creator_relative_header('Livery', 123, number, b'\1\0'))
        data = payload or str(number).encode()
        compressed = zlib.compress(data)
        raw = struct.pack('<II', len(compressed), len(data)) + compressed
        (path / 'C_livery').write_bytes(raw)
        return LiveryRecord(path.name, path, 'Livery', read_header_file(path/'header', 'Livery'),
                            livery_path=path/'C_livery', content_sha256=hashlib.sha256(raw).hexdigest())

    def settle(self, watch, start=0):
        self.assertIsNone(watch.check(start))
        return watch.check(start+3)

    def test_same_count_replace_and_no_repeated_counts(self):
        a = self.record(1)
        watch = Observation(self.root, [a])
        shutil.rmtree(a.container_path)
        self.record(2)
        diff, records = self.settle(watch)
        self.assertEqual((len(diff.added), len(diff.removed)), (1, 1))
        self.assertIsNone(watch.check(6))
        self.assertEqual(len(records), 1)

    def test_add_then_remove_returns_to_zero(self):
        a = self.record(1)
        watch = Observation(self.root, [a])
        b = self.record(2)
        self.assertEqual(len(self.settle(watch)[0].added), 1)
        shutil.rmtree(b.container_path)
        diff, _ = self.settle(watch, 6)
        self.assertEqual(diff.total, 0)

    def test_partial_download_and_partial_delete_are_unknown(self):
        a = self.record(1)
        watch = Observation(self.root, [a])
        self.settle(watch)
        (a.container_path/'header').unlink()
        self.assertIsNone(watch.check(6))
        self.assertIsNone(watch.check(9))
        self.record(1)
        b = self.record(2)
        b.livery_path.write_bytes(b'truncated')
        self.assertIsNone(self.settle(watch, 12))
        self.record(2)
        self.assertEqual(len(self.settle(watch, 18)[0].added), 1)

    def test_replacement_gap_does_not_report_deletion(self):
        a = self.record(1)
        watch = Observation(self.root, [a])
        self.settle(watch)
        shutil.rmtree(a.container_path)
        self.assertIsNone(watch.check(6))
        self.record(1)
        self.assertEqual(self.settle(watch, 9)[0].total, 0)

    def test_access_error_never_becomes_empty(self):
        a = self.record(1)
        watch = Observation(self.root, [a])
        with patch('fh6garage.livery_watch.os.scandir', side_effect=PermissionError):
            self.assertIsNone(watch.check(0))
            self.assertIsNone(watch.check(3))
        self.assertEqual(self.settle(watch, 6)[0].total, 0)

    def test_modification_during_analysis_discards_result(self):
        a = self.record(1)
        watch = Observation(self.root, [a])
        watch.check(0)
        original = read_header_file
        def read(*args):
            value = original(*args)
            self.record(2)
            return value
        with patch('fh6garage.livery_watch.read_header_file', side_effect=read):
            self.assertIsNone(watch.check(3))
        self.assertEqual(len(self.settle(watch, 6)[0].added), 1)

    def test_idle_metadata_check_never_reads_payload_or_hashes(self):
        a = self.record(1)
        watch = Observation(self.root, [a])
        self.settle(watch)
        with patch.object(Path, 'read_bytes', side_effect=AssertionError), patch('hashlib.sha256', side_effect=AssertionError):
            self.assertIsNone(watch.check(6))
            self.assertEqual(len(fingerprint(self.root)[2]), 1)

    def test_only_changed_payload_is_analyzed(self):
        a = self.record(1)
        watch = Observation(self.root, [a])
        self.settle(watch)
        self.record(2)
        with patch('fh6garage.livery_watch.read_header_file', wraps=read_header_file) as read:
            self.settle(watch, 6)
            self.assertEqual(read.call_count, 1)

    def test_relocation_is_not_deletion(self):
        a = self.record(1)
        watch = Observation(self.root, [a])
        a.container_path.rename(self.root/'Livery_123_relocated')
        self.assertEqual(self.settle(watch)[0].total, 0)

    def test_duplicate_categories_use_current_observation(self):
        from fh6garage.v1_3_2_dashboard_change_group_patch import _categorized_changes
        a = self.record(1, b'same')
        watch = Observation(self.root, [a])
        self.record(2, b'same')
        diff, records = self.settle(watch)
        groups = _categorized_changes(NS(result=NS(liveries=[a]), _fh6_observed_liveries=records), diff)
        self.assertEqual(tuple(map(len, groups.values())), (0, 0, 1))

    def test_new_baseline_clears_pending_delta(self):
        a = self.record(1)
        b = self.record(2)
        watch = Observation(self.root, [a, b])
        self.assertEqual(self.settle(watch)[0].total, 0)


class ControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from PySide6.QtWidgets import QWidget, QLineEdit
        from fh6garage.application_controls import ApplicationController
        from fh6garage.app_options import AppOptions
        self.window = QWidget()
        self.window.path_edit = QLineEdit('/temporary', self.window)
        self.window.result = NS(metadata=NS(containers_root=Path('/temporary')), liveries=[])
        self.window._game_navigation_sessions = {}
        self.window._content_annotation_key = lambda kind, r: r.container_name
        self.controller = ApplicationController(self.window)
        self.controller.timer.stop()
        self.controller.last_result = self.window.result
        self.controller.observed_path = '/temporary'
        self.options = AppOptions(auto_backup=False)
        self.mock = patch('fh6garage.application_controls.load_options', return_value=self.options)
        self.load_options = self.mock.start()
        self.addCleanup(self.mock.stop)
        from shiboken6 import delete
        self.addCleanup(delete, self.window)

    def payload(self):
        from fh6garage.refresh_history import LiveryRefreshDiff
        return self.controller.generation, (LiveryRefreshDiff(False, '', [], [], []), [])

    def test_old_result_discarded_after_invalidation(self):
        value = self.payload()
        self.controller.invalidate()
        self.controller.observation_done(value)
        self.assertFalse(hasattr(self.window, '_fh6_latest_livery_diff'))

    def test_old_result_discarded_after_main_refresh(self):
        value = self.payload()
        self.window.result = NS(liveries=[])
        self.controller.observation_done(value)
        self.assertFalse(hasattr(self.window, '_fh6_latest_livery_diff'))

    def test_old_result_discarded_after_path_change(self):
        value = self.payload()
        self.window.path_edit.setText('/different')
        self.controller.observation_done(value)
        self.assertFalse(hasattr(self.window, '_fh6_latest_livery_diff'))

    def test_off_discards_inflight_result(self):
        value = self.payload()
        from dataclasses import replace
        self.load_options.return_value = replace(self.options, auto_livery_detection=False)
        self.controller.observation_done(value)
        self.assertFalse(hasattr(self.window, '_fh6_latest_livery_diff'))

    def test_single_worker_and_no_automatic_refresh(self):
        self.controller.observer_worker = NS()
        self.window.refresh_scan = lambda: self.fail('automatic main refresh')
        with patch('fh6garage.application_controls._ObservationWorker') as worker:
            for _ in range(20):
                self.controller.poll()
        worker.assert_not_called()
        self.controller.observer_worker = None

    def test_off_does_not_start_filesystem_check(self):
        from dataclasses import replace
        self.load_options.return_value = replace(self.options, auto_livery_detection=False)
        with patch('fh6garage.application_controls._ObservationWorker') as worker:
            self.controller.poll()
        worker.assert_not_called()

    def test_busy_result_is_retried(self):
        self.controller.observation = NS(accepted='sample')
        self.window._fh6_import_running = True
        self.controller.observation_done(self.payload())
        self.assertIsNone(self.controller.observation.accepted)
        self.assertFalse(hasattr(self.window, '_fh6_latest_livery_diff'))

    def test_publish_keeps_main_list_and_selection(self):
        cards = self.window._livery_grid_cards = [object(), object()]
        selection = self.window._fh6_card_selection = object()
        result = self.window.result
        self.controller.observation_done(self.payload())
        self.assertIs(self.window.result, result)
        self.assertIs(self.window._livery_grid_cards, cards)
        self.assertIs(self.window._fh6_card_selection, selection)
        self.assertEqual(self.window._fh6_latest_livery_diff.total, 0)
