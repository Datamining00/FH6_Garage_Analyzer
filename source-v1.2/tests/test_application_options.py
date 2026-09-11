import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QDialog, QWidget

from fh6garage import app_options as options
from fh6garage.backup_export import load_index
from fh6garage.backup_delete import delete_backup
from fh6garage.models import HeaderInfo, LiveryRecord
from fh6garage.v1_3_4_backup_import_refinement_patch import _safe_export_records


class ApplicationOptionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path_patch = patch.object(options, 'options_path', return_value=self.root / 'options.json')
        self.path_patch.start()
        self.addCleanup(self.path_patch.stop)

    def record(self, name='First'):
        source = self.root / name
        source.mkdir(exist_ok=True)
        (source / 'C_livery').write_bytes(b'identical livery')
        return LiveryRecord(container_name=name, container_path=source, kind='Livery',
            header=HeaderInfo(name=name, creator='Tester', car_id=1), livery_path=source / 'C_livery')

    def test_options_persist_validate_and_snapshot(self):
        configured = options.AppOptions(render_cache=False, render_workers=3, auto_backup=True)
        self.assertTrue(options.save_options(configured))
        self.assertEqual(options.load_options(), configured)
        with options.options_snapshot():
            options.save_options(options.AppOptions())
            self.assertEqual(options.load_options(), configured)
        self.assertEqual(options.load_options(), options.AppOptions())
        options.options_path().write_text(json.dumps({'render_workers': -1, 'render_cache': 'false'}))
        self.assertEqual(options.load_options(), options.AppOptions())

    def test_duplicate_policy_and_delete_leave_source_intact(self):
        first, second = self.record(), self.record('Different')
        backup = self.root / 'backup'
        self.assertEqual(len(_safe_export_records(backup, [first]).exported), 1)
        self.assertEqual(len(_safe_export_records(backup, [second]).exported), 0)
        options.save_options(options.AppOptions(backup_allow_different_name=True))
        self.assertEqual(len(_safe_export_records(backup, [second]).exported), 1)
        self.assertEqual(len(_safe_export_records(backup, [second]).exported), 0)
        options.save_options(options.AppOptions(backup_allow_duplicates=True))
        duplicate = _safe_export_records(backup, [second]).exported[0]
        self.assertEqual(len(load_index(backup)['entries']), 3)
        delete_backup(backup, duplicate['relative_path'])
        self.assertEqual(len(load_index(backup)['entries']), 2)
        self.assertTrue(second.livery_path.is_file())

    def test_delete_rolls_back_on_index_failure(self):
        backup = self.root / 'backup'
        entry = _safe_export_records(backup, [self.record()]).exported[0]
        with patch('fh6garage.backup_delete.save_index', side_effect=OSError('full')):
            with self.assertRaises(OSError):
                delete_backup(backup, entry['relative_path'])
        self.assertTrue((backup / entry['relative_path']).is_dir())
        self.assertEqual(len(load_index(backup)['entries']), 1)

    def test_delete_rejects_outside_repository(self):
        from fh6garage.backup_export import save_index, BackupRepositoryError
        backup = self.root / 'backup'
        backup.mkdir()
        source = self.record()
        save_index(backup, {'entries': [{'relative_path': '../First'}]})
        with self.assertRaises(BackupRepositoryError):
            delete_backup(backup, '../First')
        self.assertTrue(source.livery_path.exists())

    def test_selection_subset_and_empty(self):
        from fh6garage.application_controls import ExportSelectionDialog
        records = [self.record(), self.record('Second')]
        dialog = ExportSelectionDialog(records)
        dialog.set_all(Qt.CheckState.Unchecked)
        self.assertEqual(dialog.selected_records(), [])
        dialog.items.item(1).setCheckState(Qt.CheckState.Checked)
        self.assertEqual(dialog.selected_records(), [records[1]])
        dialog.close()

    def test_2d_switch_preserves_zoom_item(self):
        from fh6garage.livery_2d_view import Livery2DController
        window, dialog = QWidget(), QDialog()
        controller = Livery2DController(window, dialog, self.record())
        pixmap = QPixmap(64, 32)
        pixmap.fill(Qt.GlobalColor.red)
        image = self.root / 'part.png'
        pixmap.save(str(image))
        controller.completed(SimpleNamespace(png_paths={'Front': image}, section_counts={'Front': 2}))
        controller.viewer.actual_size()
        self.assertEqual(controller.viewer._pixmap_item.pixmap().width(), 64)
        controller.section.setCurrentIndex(1)
        controller.viewer.fit_image()
        self.assertTrue(controller.viewer._pixmap_item.pixmap().isNull())
        controller.closed()
        window.close()

    def test_cut_disabled_before_source_resolution(self):
        from fh6garage import v1_3_4_card_polish_export_delete_patch as polish
        options.save_options(options.AppOptions(disable_export_cut=True))
        with patch.object(polish._backup_ui, '_backup_root', return_value=self.root), patch.object(polish, '_game_source_targets') as targets:
            deleted, kept = polish._delete_verified_sources(SimpleNamespace(), [self.record()])
        self.assertEqual(deleted, 0)
        self.assertEqual(len(kept), 1)
        targets.assert_not_called()

    def test_cpu_override_clamped_to_machine(self):
        from fh6garage.preview3d.native_material_textures import _native_texture_worker_limit
        options.save_options(options.AppOptions(render_workers=8))
        with patch('os.cpu_count', return_value=4):
            self.assertEqual(_native_texture_worker_limit(), 4)

    def test_locked_cut_never_reaches_delete(self):
        from fh6garage import v1_3_4_card_polish_export_delete_patch as polish
        window = SimpleNamespace(local_preferences=SimpleNamespace(get_bool=lambda key, default: True),
                                 _content_annotation_key=lambda *args: 'locked')
        with patch.object(polish._backup_ui, '_backup_root', return_value=self.root), patch.object(polish, '_park_and_delete_targets') as delete:
            deleted, kept = polish._delete_verified_sources(window, [self.record()])
        self.assertEqual(deleted, 0)
        self.assertTrue(kept)
        delete.assert_not_called()

    def test_auto_backup_deduplicates_missing_record_hash(self):
        from fh6garage.application_controls import _AutoBackupWorker
        options.save_options(options.AppOptions(backup_allow_duplicates=True))
        record = self.record()
        backup = self.root / 'backup'
        worker = _AutoBackupWorker(backup, [record], None)
        errors = []
        worker.error.connect(errors.append)
        worker.run()
        worker.run()
        self.assertEqual(errors, [])
        self.assertEqual(len(load_index(backup)['entries']), 1)
        delete_backup(backup, load_index(backup)['entries'][0]['relative_path'])
        worker.run()
        self.assertEqual(len(load_index(backup)['entries']), 1)

    def test_geometry_cache_off_passes_transient_root(self):
        from fh6garage.preview3d import chassis_converter as chassis, geometry_cache_patch as geometry
        options.save_options(options.AppOptions(render_cache=False))
        with patch.object(chassis, 'convert_vehicle') as original, patch.object(chassis, '_fh6_geometry_cache_patched', False, create=True), patch.object(geometry, '_cache_paths') as paths:
            geometry.install_geometry_cache_patch()
            chassis.convert_vehicle('asset', work_root=self.root)
            self.assertEqual(original.call_args.kwargs['work_root'], self.root)
            paths.assert_not_called()

    def test_livery_cache_off_does_not_lookup_or_save(self):
        from fh6garage.preview3d import kfps_render_backend as backend, livery_render_cache_patch as cache
        options.save_options(options.AppOptions(render_cache=False))
        with patch.object(backend, 'render_clivery_sections') as original, patch.object(backend, '_fh6_livery_render_cache_patched', False, create=True), patch.object(cache, '_cache_key') as key:
            cache.install_livery_render_cache_patch()
            backend.render_clivery_sections('source', output_root=self.root)
            self.assertEqual(original.call_args.kwargs['output_root'], self.root)
            key.assert_not_called()
