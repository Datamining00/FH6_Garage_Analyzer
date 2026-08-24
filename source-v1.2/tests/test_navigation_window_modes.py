from __future__ import annotations

import inspect
import unittest

from fh6garage import game_navigation


class NavigationWindowModeRegressionTests(unittest.TestCase):
    def test_activation_does_not_inject_alt_or_mouse_input(self) -> None:
        source = inspect.getsource(game_navigation._activate_fh6_window)
        self.assertNotIn("virtual_alt", source)
        self.assertNotIn("keybd_event", source)
        self.assertNotIn("mouse_event", source)
        self.assertIn("AttachThreadInput", source)

    def test_restore_is_guarded_by_minimized_state(self) -> None:
        source = inspect.getsource(game_navigation._activate_fh6_window)
        self.assertIn("IsIconic(target)", source)
        self.assertIn("ShowWindow(target, 9)", source)
        self.assertLess(
            source.index("IsIconic(target)"),
            source.index("ShowWindow(target, 9)"),
        )

    def test_window_title_matching_is_mode_independent(self) -> None:
        self.assertTrue(game_navigation._is_fh6_title("Forza Horizon 6"))
        self.assertTrue(game_navigation._is_fh6_title("FORZA HORIZON 6"))
        self.assertFalse(game_navigation._is_fh6_title("FH6 Assistant v1.3"))


if __name__ == "__main__":
    unittest.main()
