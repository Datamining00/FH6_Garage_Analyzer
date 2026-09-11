import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from fh6garage.license_notices import install_kfps_notices, resources_root
from fh6garage.preview3d.kfps_render_backend import _safe_extract_subset


class LicenseNoticesTests(unittest.TestCase):
    def test_existing_runtime_backfill_preserves_render_data_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / 'preview.png'
            image.write_bytes(b'original render data')
            install_kfps_notices(root)
            license_path = root / 'LICENSE'
            before = license_path.stat().st_mtime_ns
            with patch('fh6garage.license_notices.os.replace', side_effect=AssertionError('unnecessary write')):
                install_kfps_notices(root)
            self.assertEqual(license_path.stat().st_mtime_ns, before)
            self.assertEqual(image.read_bytes(), b'original render data')
            self.assertEqual(license_path.read_bytes(), (resources_root() / 'licenses/KFPS-LICENSE.txt').read_bytes())

    def test_failed_atomic_update_preserves_old_notice_and_cleans_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'LICENSE').write_bytes(b'previous notice')
            with patch('fh6garage.license_notices.os.replace', side_effect=PermissionError('in use')):
                with self.assertRaises(PermissionError): install_kfps_notices(root)
            self.assertEqual((root / 'LICENSE').read_bytes(), b'previous notice')
            self.assertEqual({p.name for p in root.iterdir()}, {'LICENSE'})

    def test_renderer_subset_keeps_upstream_notices_and_excludes_unrelated_files(self):
        archive = io.BytesIO()
        with ZipFile(archive, 'w') as z:
            z.writestr('upstream/LICENSE', 'MIT original')
            z.writestr('upstream/LICENSE.custom-importer', 'MIT custom')
            for i in range(8):
                z.writestr(f'upstream/kfps_shapes/shape_{i}.py', '# fixture')
            z.writestr('upstream/unrelated.txt', 'not needed')
        with tempfile.TemporaryDirectory() as directory, ZipFile(archive) as z:
            _safe_extract_subset(z, Path(directory))
            self.assertEqual((Path(directory) / 'LICENSE').read_text(), 'MIT original')
            self.assertFalse((Path(directory) / 'unrelated.txt').exists())
