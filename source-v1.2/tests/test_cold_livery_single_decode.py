from contextlib import ExitStack
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PIL import Image
from fh6garage.preview3d import kfps_render_backend as backend
from fh6garage.preview3d.cold_livery_render_fastpath_patch import install_cold_livery_render_fastpath_patch


class ColdLiverySingleDecodeTests(unittest.TestCase):
    def setUp(self):
        from fh6garage.app_options import _snapshot, AppOptions
        token = _snapshot.set(AppOptions(render_cache=True))
        self.addCleanup(_snapshot.reset, token)

    def render_fixture(self, layers, cache_roundtrip=False):
        with TemporaryDirectory() as td, ExitStack() as stack:
            root = Path(td)
            source = root / 'C_livery'
            source.write_bytes(b'fixture')
            payload = b'vlrc' + b'\0' * 12 + (1).to_bytes(4, 'little') + b'\0' * 6
            decoder = SimpleNamespace(
                unwrap_forza_container=Mock(return_value=payload),
                clivery_to_layers=Mock(return_value=(layers, {})),
                layers_to_kfps_json_layers=Mock(return_value=(layers, [])),
            )
            stream = io.BytesIO()
            Image.new('RGBA', (8, 4), (255, 0, 0, 255)).save(stream, format='PNG')
            renderer = SimpleNamespace(render_typecode_layers_canvas=Mock(return_value=stream.getvalue()))
            original = backend.render_clivery_sections
            sections = tuple(backend.SECTION_NAMES)
            stack.enter_context(patch.object(backend, 'ensure_runtime', return_value=root))
            stack.enter_context(patch.object(backend, '_load_backend', return_value=(decoder, renderer, None)))
            stack.enter_context(patch.object(backend, '_prepare_raster_layers', return_value=(layers, None, [], [], 0)))
            stack.enter_context(patch.object(backend, 'resolve_livery_resolution', return_value=SimpleNamespace(canvas_size=(8, 4), key='fixture')))
            stack.enter_context(patch.object(backend, 'render_clivery_sections', original))
            stack.enter_context(patch.object(backend, '_fh6_cold_livery_render_fastpath_patched', False, create=True))
            install_cold_livery_render_fastpath_patch()
            if cache_roundtrip:
                from fh6garage.preview3d.livery_render_cache_patch import install_livery_render_cache_patch
                stack.enter_context(patch.object(backend, '_app_root', return_value=root / 'cache'))
                stack.enter_context(patch.object(backend, '_fh6_livery_render_cache_patched', False, create=True))
                install_livery_render_cache_patch()
            result = backend.render_clivery_sections(source, output_root=root / 'render')
            if cache_roundtrip:
                import shutil
                shutil.rmtree(root / 'render')
                result = backend.render_clivery_sections(source, output_root=root / 'second-render')
                self.assertTrue(all(path.is_file() for path in result.png_paths.values()))
            self.assertEqual(decoder.unwrap_forza_container.call_count, 1)
            self.assertEqual(decoder.clivery_to_layers.call_count, 1)
            self.assertEqual(decoder.layers_to_kfps_json_layers.call_count, 1)
            self.assertEqual(tuple(backend.SECTION_NAMES), sections)
            self.assertEqual(set(result.section_counts), set(sections))
            expected = {layer['source_section'] for layer in layers}
            self.assertEqual(set(result.png_paths), expected)
            self.assertEqual(renderer.render_typecode_layers_canvas.call_count, len(expected))
            self.assertEqual({p.stem for p in result.output_dir.glob('*.png')}, expected)

    def test_sparse_livery_decoded_once(self):
        self.render_fixture([{'source_section': 'Left'}, {'source_section': 'Right'}])

    def test_empty_livery_enters_no_section_renderer(self):
        self.render_fixture([])

    def test_all_sections_still_decode_once(self):
        self.render_fixture([{'source_section': name} for name in backend.SECTION_NAMES])

    def test_persistent_hit_survives_intermediate_cleanup_and_skips_decode(self):
        self.render_fixture([{'source_section': 'Left'}], cache_roundtrip=True)


if __name__ == '__main__':
    unittest.main()
