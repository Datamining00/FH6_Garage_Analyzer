from __future__ import annotations

import unittest
from pathlib import Path


class V14BackupWatchStabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = Path("fh6garage/v1_4_backup_watch_stability_patch.py").read_text(encoding="utf-8")

    def test_duplicate_signature_does_not_start_another_reload(self):
        self.assertIn("_same_signature_as_cache(window, signature)", self.text)
        self.assertIn("signature == cached", self.text)
        self.assertIn("external_duplicate_ignored", self.text)
        start = self.text.index("def stable_external_changed")
        end = self.text.index("def commit_cards", start)
        body = self.text[start:end]
        duplicate = body.index("if _same_signature_as_cache(window, signature):")
        original = body.index("original_external_changed(window, path)")
        self.assertLess(duplicate, original)

    def test_repeated_pending_or_running_event_is_suppressed(self):
        self.assertIn("signature == previous_event_signature and (pending or running)", self.text)
        self.assertIn("timer.isActive()", self.text)
        self.assertIn('_fh6_backup_load_running', self.text)

    def test_successful_commit_updates_watch_signature(self):
        self.assertIn('signature = getattr(window, "_fh6_backup_cache_signature", None)', self.text)
        self.assertIn("window._fh6_backup_last_watch_event_signature = signature", self.text)

    def test_patch_is_before_interaction_and_profiler(self):
        chain = Path("fh6garage/v1_3_4_backup_action_wording_patch.py").read_text(encoding="utf-8")
        watch = chain.rindex("apply_v1_4_backup_watch_stability_patch(MainWindow)")
        interaction = chain.rindex("apply_v1_4_interaction_render_completion_patch(MainWindow)")
        profiler = chain.rindex("apply_v1_3_4_performance_probe_patch(MainWindow)")
        self.assertLess(watch, interaction)
        self.assertLess(interaction, profiler)


if __name__ == "__main__":
    unittest.main()
