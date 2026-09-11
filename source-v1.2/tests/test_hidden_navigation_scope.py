import unittest
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace as NS, MethodType
from unittest.mock import patch

from fh6garage.game_navigation import GameGridSession, NavigationItem


class HiddenNavigationScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if __name__ != '__main__':
            return
        import app
        app._apply_runtime_patch_stack()
        from fh6garage.ui import MainWindow
        cls.window_class = MainWindow

    def window(self, count, hidden=(), removed=()):
        records = [NS(kind='Livery', container_name=f'Livery_{i:04d}_20260912000000',
                      car_id=i, header=NS(guid=f'guid{i}', name=f'name{i}'),
                      content_sha256=f'hash{i}') for i in range(count)]
        names = {records[i].container_name for i in hidden}
        window = NS(result=NS(liveries=records, tunings=[]), _game_navigation_generation=0,
                    _custom_liveries=lambda: records,
                    _content_annotation_key=lambda kind, r: r.container_name,
                    local_preferences=NS(get_bool=lambda key, default=False:
                                         any(key.endswith(name) for name in names)),
                    _fh6_navigation_watch=NS(removed={records[i].container_name for i in removed}),
                    path_edit=NS(text=lambda: 'test'), _fh6_change_dialog=None)
        window._saved_content_records = MethodType(self.window_class._saved_content_records, window)
        return window, records

    def observe(self, window, records):
        from fh6garage.application_controls import ApplicationController
        controller = NS(window=window, generation=1, last_result=window.result,
                        observed_path='test', busy=lambda: False)
        with patch('fh6garage.application_controls.load_options', return_value=NS(auto_livery_detection=True)), patch('fh6garage.v1_4_ui_completion_patch._update_recent_change_banner'):
            ApplicationController.observation_done(controller, (1, (NS(added=[], removed=[], changed=[]), records)))
        return window._game_navigation_sessions['livery']

    def test_hiding_any_position_preserves_all_other_routes(self):
        for count in (5, 6):
            for hidden in range(count):
                with self.subTest(count=count, hidden=hidden):
                    window, records = self.window(count, [hidden])
                    self.window_class._reset_game_navigation_sessions(window)
                    actual = window._game_navigation_sessions['livery']
                    expected = GameGridSession([NavigationItem(r.container_name, r.car_id) for r in records])
                    self.assertEqual(len(actual.items), count)
                    self.assertTrue(self.window_class._fh6_v132_is_livery_hidden(window, records[hidden].container_name))
                    for index, record in enumerate(records):
                        if index != hidden:
                            self.assertEqual(actual.plan_from_first(record.container_name), expected.plan_from_first(record.container_name))

    def test_manual_and_automatic_scopes_and_routes_match_with_multiple_hidden(self):
        window, records = self.window(8, [0, 2, 5, 7])
        self.window_class._reset_game_navigation_sessions(window)
        manual = window._game_navigation_sessions['livery']
        automatic = self.observe(window, records)
        self.assertEqual(manual.items, automatic.items)
        for record in records:
            self.assertEqual(manual.plan_from_first(record.container_name), automatic.plan_from_first(record.container_name))

    def test_confirmed_deletion_still_excluded_in_both_paths(self):
        window, records = self.window(6, [1, 3], [2])
        self.window_class._reset_game_navigation_sessions(window)
        manual = window._game_navigation_sessions['livery']
        automatic = self.observe(window, records)
        self.assertEqual(manual.items, automatic.items)
        self.assertFalse(manual.contains(records[2].container_name))
        self.assertTrue(manual.contains(records[1].container_name))
        self.assertTrue(manual.contains(records[3].container_name))


def isolated_test(name):
    def run(self):
        # Installing the complete runtime stack changes shared Qt classes.
        # Keep those changes out of other unit tests in the discovery process.
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                                 'HiddenNavigationScopeTests.' + name],
                                cwd=Path(__file__).resolve().parents[1],
                                env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]),
                                         QT_QPA_PLATFORM='offscreen'),
                                capture_output=True, text=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    return run


if __name__ == '__main__':
    unittest.main()
else:
    for name in tuple(vars(HiddenNavigationScopeTests)):
        if name.startswith('test_'):
            setattr(HiddenNavigationScopeTests, name, isolated_test(name))
