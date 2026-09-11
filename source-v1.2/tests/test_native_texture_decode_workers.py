import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from fh6garage.preview3d import native_material_textures as native
from fh6garage.preview3d.pipeline_diagnostics import preview_trace


class NativeDecodeWorkersTest(unittest.TestCase):
    def test_worker_limit_scales_with_cpu_and_keeps_a_hard_cap(self):
        for logical, expected in ((None, 3), (1, 1), (2, 1), (4, 3), (8, 6), (16, 12), (64, 12)):
            with self.subTest(logical=logical), patch.object(native.os, 'cpu_count', return_value=logical):
                self.assertEqual(native._native_texture_worker_limit(), expected)

    def make_items(self, root, names):
        items = []
        for index, name in enumerate(names):
            payload = name.encode()
            digest = hashlib.sha256(payload).hexdigest()
            path = root / f'{digest}.swatchbin'
            path.write_bytes(payload)
            items.append(native.NativeTexturePayload(
                texture_path=f'reference-{index}', normalized_path=f'reference-{index}',
                status='resolved_payload', resolution_mode='test',
                payload_sha256=digest, cache_path=str(path)))
        return tuple(items)

    def test_disjoint_outputs_overlap_duplicates_serialize_and_trace_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            helper = root / 'helper.exe'
            helper.touch()
            items = self.make_items(root, ['a', 'b', 'a', 'c', 'd', 'e'])
            barrier = threading.Barrier(4, timeout=10)
            lock = threading.Lock()
            active = set()
            calls = []
            peak = 0

            def run(args, **kwargs):
                nonlocal peak
                output = Path(args[3])
                with lock:
                    self.assertNotIn(output, active)
                    active.add(output)
                    calls.append(output)
                    ordinal = len(calls)
                    peak = max(peak, len(active))
                if ordinal <= 4:
                    barrier.wait()
                data = b'DDS ' + bytes(144) + Path(args[2]).read_bytes()
                output.write_bytes(data)
                with lock:
                    active.remove(output)
                return subprocess.CompletedProcess(args, 0, json.dumps({
                    'ddsSha256': hashlib.sha256(data).hexdigest()}), '')

            with patch.object(native, '_NATIVE_TEXTURE_DECODE_WORKERS', 4), \
                 patch.object(native.os, 'cpu_count', return_value=16), \
                 patch.object(native.subprocess, 'run', side_effect=run), \
                 patch('fh6garage.preview3d.pipeline_diagnostics._persist'), \
                 patch('fh6garage.preview3d.pipeline_diagnostics.log_event'), \
                 preview_trace('workers') as trace:
                results = native._decode_resolved_payloads(items, helper, root)
            self.assertEqual(peak, 4)
            self.assertEqual(len(calls), 5)
            self.assertEqual([x.texture_path for x in results], [x.texture_path for x in items])
            self.assertEqual(results[2].decode_status, 'decoded_dds_cached')
            self.assertEqual(results[0].dds_sha256, results[2].dds_sha256)
            self.assertEqual(sum(e['event'] == 'native_texture_decoder_subprocess'
                                 for e in trace['events']), 5)
            with patch.object(native.subprocess, 'run') as run_cached:
                cached = native._decode_resolved_payloads(items, helper, root)
            run_cached.assert_not_called()
            self.assertTrue(all(x.decode_status == 'decoded_dds_cached' for x in cached))

    def test_failure_is_isolated_and_successful_outputs_survive(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            helper = root / 'helper.exe'
            helper.touch()
            items = self.make_items(root, ['ok', 'timeout', 'failed', 'bad-sha'])

            def run(args, **kwargs):
                name = Path(args[2]).read_text()
                if name == 'timeout':
                    raise subprocess.TimeoutExpired(args, 120)
                if name == 'failed':
                    return subprocess.CompletedProcess(args, 1, '', 'decoder rejected payload')
                Path(args[3]).write_bytes(b'DDS ' + bytes(144) + b'payload')
                return subprocess.CompletedProcess(args, 0,
                    json.dumps({'ddsSha256': 'incorrect'}) if name == 'bad-sha' else '{}', '')

            with patch.object(native.subprocess, 'run', side_effect=run):
                results = native._decode_resolved_payloads(items, helper, root)
            self.assertEqual([x.decode_status for x in results],
                             ['decoded_dds', 'decode_failed', 'decode_failed', 'decode_failed'])
            self.assertTrue(Path(results[0].dds_path).is_file())
            self.assertFalse((root / 'native_material_textures' / f'{items[3].payload_sha256}.dds').exists())

    def test_unavailable_helper_does_not_start_workers(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            items = self.make_items(root, ['a', 'b'])
            with patch.object(native, 'ThreadPoolExecutor') as pool:
                results = native._decode_resolved_payloads(items, None, root)
            pool.assert_not_called()
            self.assertTrue(all(x.decode_status == 'decoder_unavailable' for x in results))
