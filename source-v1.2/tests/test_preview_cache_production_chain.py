from __future__ import annotations

from pathlib import Path
import json
import os
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from fh6garage.preview3d import chassis_converter as chassis
from fh6garage.preview3d import geometry_cache_patch as geometry
from fh6garage.preview3d import native_transform_chain_patch as transform
from fh6garage.preview3d import tire_preview_integration as tire


class ProductionCacheChainTests(unittest.TestCase):
    def setUp(self):
        from fh6garage.app_options import _snapshot, AppOptions
        token = _snapshot.set(AppOptions(render_cache=True))
        self.addCleanup(_snapshot.reset, token)

    def test_full_installer_reuses_final_glb_across_processes(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            results = []
            for _ in range(2):
                completed = subprocess.run(
                    [sys.executable, str(Path(__file__).resolve()), '--probe', str(root)],
                    env={**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1]),
                         'LOCALAPPDATA': str(root), 'QT_QPA_PLATFORM': 'offscreen'},
                    capture_output=True, text=True, check=True,
                )
                results.append(json.loads(completed.stdout))
            self.assertEqual(results[0]['calls'], ['convert', 'build', 'attach', 'merge', 'bake'])
            self.assertEqual(results[1]['calls'], [])
            self.assertEqual(results[0]['output'], results[1]['output'])
            self.assertEqual(results[1]['status'], 'stock_native_tire_preview_cache_hit')
            self.assertTrue(Path(results[1]['output']).is_file())

    def test_geometry_hit_preserves_transform_inventory(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            archive = root / 'vehicle.zip'
            archive.write_bytes(b'archive')
            asset = SimpleNamespace(car_id=1, model_code='TEST', archive_path=archive,
                                    carbin_entries=('test.carbin',))
            diagnostics = {'wheel_style_anchors': [{'instance_identity': 'wheel'}],
                           'transform_audit': [{'instance_identity': 'wheel', 'vertex_count': 3}]}

            def convert(asset, progress=None, *, work_root=None, **kwargs):
                output = Path(work_root) / 'car_1_TEST.glb'
                output.write_bytes(b'glTF' + b'\0' * 32)
                return chassis.ConversionResult(str(output), 'fixture', diagnostics)

            original = Mock(side_effect=convert)
            with patch.object(chassis, 'convert_vehicle', original), \
                 patch.object(chassis, '_fh6_geometry_cache_patched', False, create=True), \
                 patch.object(chassis, 'app_data_root', return_value=root), \
                 patch('fh6garage.preview3d.wheel_morph_auto.resolve_automatic_stock_rim_morph',
                       return_value=SimpleNamespace(weights=None, status='fixture')):
                geometry.install_geometry_cache_patch()
                first = chassis.convert_vehicle(asset)
                second = chassis.convert_vehicle(asset)
                self.assertEqual(original.call_count, 1)
                self.assertEqual(second.output_path, first.output_path)
                self.assertEqual(second.diagnostics.get('wheel_style_anchors'), diagnostics['wheel_style_anchors'])
                self.assertEqual(second.diagnostics.get('transform_audit'), diagnostics['transform_audit'])

    def test_production_transform_wrapper_calls_cache_visible_entrypoint(self):
        asset = SimpleNamespace(car_id=1, archive_path=Path('vehicle.zip'),
                                carbin_entries=('test.carbin',))
        converted = chassis.ConversionResult('base.glb', 'fixture', {'wheel_style_anchors': ['wheel']})
        applied = tire.TirePreviewIntegrationResult('stock_native_tire_preview_cache_hit',
            'fixture', 1, 'TEST', 'base.glb', 'final.glb', True, False, False, 'fixture', None)
        with patch.object(tire, 'try_apply_stock_native_tire_preview', return_value=applied) as cached, \
             patch.object(transform, '_try_apply_v5', return_value=applied):
            result = transform._make_v5_convert_wrapper(Mock(return_value=converted))(asset)
            cached.assert_called_once()
            self.assertEqual(cached.call_args.kwargs['converter_diagnostics'], converted.diagnostics)
            self.assertEqual(Path(result.output_path), Path('final.glb').resolve())


def _probe(root):
    from fh6garage.app_options import _snapshot, AppOptions
    _snapshot.set(AppOptions(render_cache=True))
    from contextlib import ExitStack
    from fh6garage import preview3d
    from fh6garage.preview3d import integration
    calls = []
    for name in ('vehicle.zip', 'wheel.db', 'tire.zip'):
        path = root / name
        if not path.exists():
            path.write_bytes(b'fixture')
    asset = SimpleNamespace(car_id=1, model_code='TEST', archive_path=root / 'vehicle.zip',
                            carbin_entries=('test.carbin',))
    diagnostics = {'wheel_style_anchors': [{'instance_identity': 'wheel'}],
                   'transform_audit': [{'instance_identity': 'wheel', 'vertex_count': 3}]}
    def convert(asset, progress=None, *, work_root=None, **kwargs):
        calls.append('convert')
        path = Path(work_root) / 'car_1_TEST.glb'
        path.write_bytes(b'glTF' + b'\0' * 32)
        return chassis.ConversionResult(str(path), 'fixture', diagnostics)
    def build(*args):
        calls.append('build')
        return {}
    def attach(*args):
        calls.append('attach')
        return {'attachment_count': 1}
    def merge(source, contract, output):
        calls.append('merge')
        output.write_bytes(b'glTF' + b'\0' * 64)
        return {}
    def bake(*args):
        calls.append('bake')
        return {'node_count': 1, 'vertex_count': 3, 'triangle_winding_reversed_count': 1}
    spec = SimpleNamespace(tire_model_name='Test', as_dict=lambda: {'tire_model_name': 'Test'})
    with ExitStack() as stack:
        stack.enter_context(patch.object(chassis, 'convert_vehicle', convert))
        stack.enter_context(patch.object(integration, 'convert_vehicle', convert))
        stack.enter_context(patch('fh6garage.preview3d.wheel_morph_auto.resolve_automatic_stock_rim_morph',
                                 return_value=SimpleNamespace(weights=None, status='fixture')))
        preview3d._install_native_transform_chain_preview()
        # Verify the real idempotent installer leaves the same active chain.
        preview3d._install_native_transform_chain_preview()
        for module in (tire, transform):
            stack.enter_context(patch.object(module, 'ensure_stock_wheel_database', return_value=root / 'wheel.db'))
            stack.enter_context(patch.object(module, 'FH6WheelSpecResolver', return_value=SimpleNamespace(resolve=lambda _: spec)))
            stack.enter_context(patch.object(module, 'resolve_tire_archive', return_value=root / 'tire.zip'))
        for name, func in (('_build_native_tire_geometry_report', build),
                           ('_build_dynamic_attachment_contract', attach),
                           ('_merge_dynamic_tires', merge), ('_bake_dynamic_tire_nodes', bake)):
            stack.enter_context(patch.object(transform, name, func))
        with TemporaryDirectory() as caller:
            result = integration.convert_vehicle(asset, work_root=caller)
        print(json.dumps({'calls': calls, 'output': result.output_path,
                          'status': result.diagnostics['native_tire_preview']['status']}))


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--probe':
        _probe(Path(sys.argv[2]))
    else:
        unittest.main()
