"""Temporary-save production UI and metadata polling benchmark. No game access."""
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['FH6_ASSISTANT_SMOKE_TEST_MS'] = '60000'


def main():
    import faulthandler
    faulthandler.dump_traceback_later(15)
    output = Path(sys.argv[1]).resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='fh6-watch-') as temporary:
        os.environ['LOCALAPPDATA'] = temporary
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QFont, QFontDatabase
        from shiboken6 import delete
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, temporary)
        q = QApplication([])
        QFontDatabase.addApplicationFont('C:/Windows/Fonts/malgun.ttf')
        q.setFont(QFont('Malgun Gothic', 10))
        import app
        app._apply_runtime_patch_stack()
        from fh6garage.app_options import AppOptions, save_options
        save_options(AppOptions(auto_livery_detection=False))
        from test_livery_watch import WatchTests
        fixture = WatchTests()
        fixture.root = Path(temporary) / 'save' / 'current' / 'ContainersRoot'
        fixture.root.mkdir(parents=True)
        records = [fixture.record(i + 1) for i in range(36)]
        from fh6garage.models import ScanResult, SaveMetadata
        result = ScanResult(SaveMetadata(fixture.root, fixture.root.parent.parent, fixture.root), liveries=records)
        w = app.MainWindow(project_root=ROOT)
        c = w._fh6_application_controller
        c.timer.stop()
        w.path_edit.setText(str(fixture.root))
        w.result = result
        w._reset_game_navigation_sessions()
        w._populate_all()
        w.pages.setCurrentIndex(1)
        w.resize(1100, 760)
        w.show()
        for _ in range(5):
            q.processEvents()
        from fh6garage.livery_watch import Observation, fingerprint
        watch = Observation(fixture.root, records)
        fixture.record(100)
        watch.check(0)
        value = watch.check(3)
        assert value and len(value[0].added) == 1
        cards = list(w._livery_grid_cards)
        scroll = w.livery_grid_scroll.verticalScrollBar()
        scroll.setValue(scroll.maximum() // 2)
        scroll_before = scroll.value()
        from fh6garage.card_transfer import CardSelection, visible_items
        selection = CardSelection(w, 'game', visible_items(w, 'game'))
        selection.selected.add(0)
        c.last_result = result
        c.observed_path = w.path_edit.text().strip()
        save_options(AppOptions(auto_livery_detection=True))
        c.observation_done((c.generation, value))
        q.processEvents()
        assert w.result is result and list(w._livery_grid_cards) == cards
        assert scroll.value() == scroll_before
        assert w._fh6_card_selection is selection and selection.selected == {0}
        from fh6garage.v1_4_ui_completion_patch import _recent_change_counts
        assert _recent_change_counts(w) == (1, 0, 0)
        w.grab().save(str(output / 'main-preserved.png'))
        selection.cancel()
        from fh6garage.v1_3_2_dashboard_change_group_patch import _open_grouped_change_dialog
        _open_grouped_change_dialog(w)
        q.processEvents()
        dialog = w._fh6_change_dialog
        assert len(dialog._fh6_change_groups['added']) == 1
        dialog.grab().save(str(output / 'change-cards.png'))
        # Update an already open change window without rebuilding main cards.
        fixture.record(101)
        watch.check(6)
        c.observation_done((c.generation, watch.check(9)))
        assert len(dialog._fh6_change_groups['added']) == 2
        assert _recent_change_counts(w) == (2, 0, 0)
        assert list(w._livery_grid_cards) == cards
        dialog.close()
        key = w._content_annotation_key('livery', records[0])
        with patch('fh6garage.ui.send_arrow_keys_to_fh6', return_value='test game') as send:
            for _ in range(2):
                w._execute_game_navigation('livery', key, [], 'delete', w._game_navigation_generation, False, 70)
                assert w._game_navigation_sessions['livery'].contains(key)
            assert send.call_count == 2
            from fh6garage.v1_3_4_card_features_patch import _lock_pref_key
            w.local_preferences.set_bool(_lock_pref_key(key), True)
            w._execute_game_navigation('livery', key, [], 'delete', w._game_navigation_generation, False, 70)
            assert send.call_count == 2
        # A real scan waits for a cancelled observer, then advances the baseline.
        from threading import Event
        from fh6garage.application_controls import _ObservationWorker
        gate = Event()
        c.observation = Observation(fixture.root, records)
        c.observation.check = lambda: (gate.wait(5), value)[1]
        worker = _ObservationWorker(c.observation, c.generation, c)
        worker.result_ready.connect(c.observation_done)
        worker.finished.connect(c.observation_finished)
        c.observer_worker = worker
        worker.start()
        w.start_scan(fixture.root)
        assert c.pending_scan is not None and w._scan_thread is None
        gate.set()
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            q.processEvents()
            if w.result is not result and c.observer_worker is None and w._scan_thread is None:
                break
            time.sleep(.01)
        assert w.result is not result and w._scan_thread is None
        assert _recent_change_counts(w) == (0, 0, 0)
        w.close()
        q.processEvents()
        delete(w)
        for i in range(102, 3001):
            fixture.record(i)
        count = len(fingerprint(fixture.root)[2])
        times, cpu = [], []
        for _ in range(12):
            begin, processor = time.perf_counter(), time.process_time()
            fingerprint(fixture.root)
            times.append((time.perf_counter() - begin) * 1000)
            cpu.append((time.process_time() - processor) * 1000)
        report = dict(containers=count, files_per_poll=count*2,
                      poll_median_ms=statistics.median(times), poll_max_ms=max(times),
                      cpu_median_ms=statistics.median(cpu), payload_bytes_read_per_idle_poll=0,
                      ui='main cards, scroll, selection, live counts/cards, repeated navigation and lock passed')
        (output/'validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report, indent=2))
        faulthandler.cancel_dump_traceback_later()


if __name__ == '__main__':
    main()
