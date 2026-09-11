import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
from PIL import Image

from fh6garage.thumbnail_marks import MarkStore, digest
from fh6garage.thumbnail_marks_ui import plan
from fh6garage.app_options import AppOptions


class ThumbnailMarkTests(unittest.TestCase):
    def test_folder_lock_survives_cache_lookup_error(self):
        containers = self.root / 'containers'; containers.mkdir()
        folder = containers / 'Livery_1'; folder.mkdir()
        thumb = folder / 'bigThumb.webp'; thumb.write_bytes(self.original)
        record = NS(kind='Livery', container_path=folder, container_name=folder.name)
        with patch('fh6garage.auction_thumbnails._header_livery_token', side_effect=ValueError('bad cache link')):
            targets, failures = plan([record], containers, None, AppOptions(), [True])
        self.assertEqual(targets, {str(thumb): (False, True)})
        self.assertTrue(failures)
        self.assertEqual(self.store.apply(targets)['written'], 1)

    def test_unapplied_auction_folder_lock_and_unlock_without_cache_work(self):
        containers = self.root / 'containers'; containers.mkdir()
        folder = containers / 'SoulBoundLivery_1'; folder.mkdir()
        thumb = folder / 'bigThumb.webp'; thumb.write_bytes(self.original)
        record = NS(kind='SoulBoundLivery', container_path=folder, container_name=folder.name)
        with patch('fh6garage.auction_thumbnails._read_manifest_bytes') as manifest, patch('fh6garage.auction_thumbnails._header_livery_token') as token:
            for lock in (True, False):
                targets, failures = plan([record], containers, self.root / 'cache', AppOptions(show_auction_badge=True), [lock], entries=self.store.load(), folder_only=[folder])
                self.assertEqual(targets, {str(thumb): (False, lock)})
                self.assertFalse(failures)
                result = self.store.apply(targets, partial=True)
                self.assertFalse(result['failures'])
            manifest.assert_not_called()
            token.assert_not_called()
        self.assertEqual(thumb.read_bytes(), self.original)

    def test_both_kinds_write_folder_and_exact_cache_and_skip_multiple_cache(self):
        containers = self.root/'containers'; containers.mkdir()
        cache = self.root/'cache'; cache.mkdir()
        records, rows = [], []
        for i, kind in enumerate(('Livery','SoulBoundLivery'), 1):
            folder = containers/f'{kind}_{i}'; folder.mkdir()
            (folder/'bigThumb.webp').write_bytes(self.original)
            cached = cache/f'{i}.webp'; cached.write_bytes(self.original)
            records.append(NS(kind=kind, container_path=folder, container_name=folder.name, car_id=i))
            rows.append(NS(car_id=i, livery_token='token', path=cached, logical_name=str(i)))
        with patch('fh6garage.auction_thumbnails._read_manifest_bytes',return_value=b''), patch('fh6garage.auction_manifest_registry.read_auction_manifest_registry',return_value=NS(logical_names={'1','2','duplicate'})), patch('fh6garage.auction_thumbnails.read_thumbnail_manifest', return_value=rows), patch('fh6garage.auction_thumbnails._header_livery_token', return_value='token'):
            targets, failures = plan(records, containers, cache, AppOptions(show_auction_badge=True), [True,True])
            self.assertEqual(len(targets), 4)
            self.assertFalse(failures)
            self.assertEqual(targets[str(cache/'1.webp')], (False,True))
            self.assertEqual(targets[str(cache/'2.webp')], (True,True))
            duplicate = cache/'duplicate.webp'; duplicate.write_bytes(self.original)
            rows.append(NS(car_id=1,livery_token='token',path=duplicate,logical_name='duplicate'))
            targets, failures = plan(records, containers, cache, AppOptions(show_auction_badge=True), [True,True])
            self.assertNotIn(str(cache/'1.webp'), targets)
            self.assertIn(str(records[0].container_path/'bigThumb.webp'), targets)
            self.assertTrue(failures)

    def test_marks_only_change_bottom_region(self):
        from fh6garage.thumbnail_marks import draw_marks
        from PIL import ImageChops
        data = draw_marks(self.original, True, True)
        before = Image.open(io.BytesIO(self.original)).convert('RGB')
        after = Image.open(io.BytesIO(data)).convert('RGB')
        bbox = ImageChops.difference(before,after).getbbox()
        self.assertIsNotNone(bbox)
        self.assertGreater(bbox[1], 250)

    def test_reapply_adopts_replacement_then_deletes_previous_backup(self):
        self.store.apply({self.file: (True, False)})
        old = next(self.store.root.glob('*.bin'))
        Image.new('RGB', (540, 300), 'red').save(self.file, 'WEBP', lossless=True)
        replacement = self.file.read_bytes()
        result = self.store.apply({self.file: (True, True)}, reapply=True)
        self.assertFalse(result['failures'])
        self.assertEqual(result['deleted_backups'], 1)
        self.assertFalse(old.exists())
        self.store.apply({}, restore_all=True)
        self.assertEqual(self.file.read_bytes(), replacement)

    def test_reapply_failure_keeps_previous_backup(self):
        self.store.apply({self.file: (True, False)})
        old = next(self.store.root.glob('*.bin'))
        self.file.unlink()
        result = self.store.apply({self.file: (True, True)}, reapply=True)
        self.assertTrue(result['failures'])
        self.assertTrue(old.exists())
        self.assertEqual(result['deleted_backups'], 0)

    def test_reapply_does_not_delete_backup_shared_by_another_thumbnail(self):
        second = self.root / 'second.webp'
        second.write_bytes(self.original)
        self.store.apply({self.file: (True, False), second: (True, False)})
        old = next(self.store.root.glob('*.bin'))
        Image.new('RGB', (540, 300), 'red').save(self.file, 'WEBP', lossless=True)
        result = self.store.apply({self.file: (True, False)}, reapply=True)
        self.assertEqual(result['deleted_backups'], 0)
        self.assertTrue(old.exists())
        self.store.apply({}, restore_all=True)
        self.assertEqual(second.read_bytes(), self.original)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = MarkStore(self.root / 'originals')
        self.file = self.root / 'image.webp'
        Image.new('RGB', (540, 300), '#dce4ed').save(self.file, 'WEBP', lossless=True)
        self.original = self.file.read_bytes()

    def test_write_preserves_name_format_dimensions_and_exact_restore(self):
        result = self.store.apply({self.file: (True, True)})
        self.assertEqual(result['written'], 1)
        self.assertFalse(result['failures'])
        with Image.open(self.file) as image:
            self.assertEqual((image.format, image.size), ('WEBP', (540, 300)))
        self.assertNotEqual(self.file.read_bytes(), self.original)
        self.assertEqual(self.store.apply({}, restore_all=True)['restored'], 1)
        self.assertEqual(self.file.read_bytes(), self.original)

    def test_repeated_write_is_stable_and_removing_one_mark_reuses_original(self):
        self.store.apply({self.file: (True, True)})
        first = self.file.read_bytes()
        self.assertEqual(self.store.apply({self.file: (True, True)})['written'], 0)
        self.assertEqual(self.file.read_bytes(), first)
        self.store.apply({self.file: (False, True)})
        lock_only = self.file.read_bytes()
        self.store.apply({}, restore_all=True)
        self.store.apply({self.file: (False, True)})
        self.assertEqual(self.file.read_bytes(), lock_only)
        self.assertEqual(len(list(self.store.root.glob('*.bin'))), 1)

    def test_game_replacement_is_never_overwritten_on_apply_or_restore(self):
        self.store.apply({self.file: (True, False)})
        Image.new('RGB', (540, 300), 'red').save(self.file, 'WEBP')
        replacement = self.file.read_bytes()
        for restore in (False, True):
            result = self.store.apply({self.file: (False, True)}, restore_all=restore)
            self.assertEqual(len(result['failures']), 1)
            self.assertEqual(self.file.read_bytes(), replacement)
        self.assertEqual(self.store.original(next(iter(self.store.load().values()))), self.original)

    def test_backup_failure_leaves_target_untouched(self):
        with patch.object(self.store, 'save', side_effect=OSError('disk full')):
            result = self.store.apply({self.file: (True, False)})
        self.assertTrue(result['failures'])
        self.assertEqual(self.file.read_bytes(), self.original)

    def test_target_failure_preserves_original_and_retry_works(self):
        from fh6garage import thumbnail_marks as marks
        original_atomic = marks.atomic
        def fail(path, data):
            if Path(path) == self.file:
                raise PermissionError('in use')
            original_atomic(path, data)
        with patch.object(marks, 'atomic', side_effect=fail):
            result = self.store.apply({self.file: (True, False)})
        self.assertTrue(result['failures'])
        self.assertEqual(self.file.read_bytes(), self.original)
        self.assertEqual(self.store.apply({self.file: (True, False)})['written'], 1)

    def test_journal_recovers_interrupted_mark_transition(self):
        self.store.apply({self.file: (True, False)})
        entries = self.store.load()
        entry = entries[str(self.file)]
        entry['previous_output'] = entry['output']
        entry['output'] = '0' * 64  # planned next output was never published
        self.store.save(entries)
        self.assertEqual(self.store.apply({}, restore_all=True)['restored'], 1)
        self.assertEqual(self.file.read_bytes(), self.original)

    def test_corrupt_backup_does_not_touch_image(self):
        self.store.apply({self.file: (True, False)})
        before = self.file.read_bytes()
        next(self.store.root.glob('*.bin')).write_bytes(b'broken')
        self.assertTrue(self.store.apply({}, restore_all=True)['failures'])
        self.assertEqual(self.file.read_bytes(), before)

    def test_unsupported_target_never_written(self):
        path = self.root / 'C_livery'
        path.write_bytes(self.original)
        self.assertTrue(self.store.apply({path: (True, False)})['failures'])
        self.assertEqual(path.read_bytes(), self.original)

    def test_png_jpeg_extensions_preserved(self):
        for fmt, suffix in (('PNG', '.png'), ('JPEG', '.jpg')):
            path = self.root / ('thumb' + suffix)
            Image.new('RGB', (540, 300), 'white').save(path, fmt)
            original = path.read_bytes()
            self.assertFalse(self.store.apply({path: (False, True)})['failures'])
            with Image.open(path) as image:
                self.assertEqual(image.format, fmt)
            self.store.apply({path: (False, False)})
            self.assertEqual(path.read_bytes(), original)

    def test_mapping_regular_and_exact_soulbound_only_shared_conflict_skipped(self):
        containers = self.root / 'ContainersRoot'
        cache = self.root / 'CacheThumbnails'
        containers.mkdir(); cache.mkdir()
        regular_dir = containers / 'Livery_1'
        regular_dir.mkdir()
        regular_thumb = regular_dir / 'bigThumb.webp'
        regular_thumb.write_bytes(self.original)
        auction_thumb = cache / 'id.webp'
        auction_thumb.write_bytes(self.original)
        regular = NS(kind='Livery', container_path=regular_dir, container_name=regular_dir.name, thumbnail_path=regular_thumb)
        soul_dir = containers / 'SoulBoundLivery_1'
        soul_dir.mkdir()
        soul = NS(kind='SoulBoundLivery', container_path=soul_dir, container_name=soul_dir.name, car_id=1)
        rows = [NS(car_id=1, livery_token='token', path=auction_thumb, logical_name='one')]
        with patch('fh6garage.auction_thumbnails._read_manifest_bytes',return_value=b''), patch('fh6garage.auction_manifest_registry.read_auction_manifest_registry',return_value=NS(logical_names={'one'})), patch('fh6garage.auction_thumbnails.read_thumbnail_manifest', return_value=rows), patch('fh6garage.auction_thumbnails._header_livery_token', return_value='token'):
            targets, failures = plan([regular, soul], containers, cache, AppOptions(show_auction_badge=True), [True, False])
            self.assertFalse(failures)
            self.assertEqual(targets[str(regular_thumb)], (False, True))
            self.assertEqual(targets[str(auction_thumb)], (True, False))
            targets, failures = plan([soul, soul], containers, cache, AppOptions(show_auction_badge=True), [True, False])
            self.assertFalse(targets)
            self.assertTrue(failures)
            soul.car_id = 2
            targets, failures = plan([soul], containers, cache, AppOptions(show_auction_badge=True), [False])
            self.assertFalse(targets)  # no cross-car fallback for writes

    def test_off_restores_independent_files_after_restart(self):
        second = self.root / 'second.webp'
        second.write_bytes(self.original)
        self.store.apply({self.file: (True, False), second: (False, True)})
        result = MarkStore(self.store.root).apply({}, restore_all=True)
        self.assertEqual(result['restored'], 2)
        self.assertEqual(second.read_bytes(), self.original)
