from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch

from fh6garage.preview3d.pipeline_diagnostics import preview_trace, record, timed


class PreviewPipelineDiagnosticsTests(unittest.TestCase):
    def test_threads_keep_separate_provenance_and_timing(self):
        @timed('parse')
        def parse(value):
            record('selected_glb', path=value)
            return value
        def worker(value):
            with preview_trace('fixture') as trace:
                self.assertEqual(parse(value), value)
            return trace
        with patch('fh6garage.preview3d.pipeline_diagnostics._persist'), \
             patch('fh6garage.preview3d.pipeline_diagnostics.log_event'), \
             ThreadPoolExecutor(max_workers=2) as pool:
            traces = list(pool.map(worker, ['first.glb', 'second.glb']))
        self.assertNotEqual(traces[0]['run_id'], traces[1]['run_id'])
        for trace, path in zip(traces, ['first.glb', 'second.glb']):
            self.assertEqual(trace['events'][0]['path'], path)
            self.assertEqual(trace['events'][1]['event'], 'parse')
            self.assertGreaterEqual(trace['events'][1]['elapsed_ms'], 0)

    def test_failure_is_timed_and_original_exception_preserved(self):
        @timed('decode')
        def fail():
            raise ValueError('fixture')
        with patch('fh6garage.preview3d.pipeline_diagnostics._persist'), \
             patch('fh6garage.preview3d.pipeline_diagnostics.log_event'):
            with self.assertRaisesRegex(ValueError, 'fixture'):
                with preview_trace('fixture') as trace:
                    fail()
        self.assertEqual(trace['events'][0]['outcome'], 'error')


if __name__ == '__main__':
    unittest.main()
