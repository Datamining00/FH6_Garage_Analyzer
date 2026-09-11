import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
from PIL import Image
from fh6garage.thumbnail_marks import MarkStore
from fh6garage.thumbnail_marks_ui import plan, excluded_auction
from fh6garage.app_options import AppOptions


class RefinementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.file = self.root / 'one.webp'
        Image.new('RGB', (540, 300), 'white').save(self.file, 'WEBP', lossless=True)
        self.original = self.file.read_bytes()
        self.store = MarkStore(self.root / 'originals')

    def test_unchanged_skips_image_encoding_and_journal_write(self):
        self.store.apply({self.file: (True, True)})
        with patch('fh6garage.thumbnail_marks.draw_marks', side_effect=AssertionError('rendered unchanged')), patch.object(self.store, 'save', side_effect=AssertionError('saved unchanged')):
            result = self.store.apply({self.file: (True, True)})
        self.assertEqual(result['written'], 0)
        self.assertFalse(result['failures'])
        self.assertIn(str(self.file).casefold(), result['originals'])

    def test_partial_does_not_read_unrelated_images_or_originals(self):
        other = self.root / 'two.webp'
        other.write_bytes(self.original)
        self.store.apply({self.file: (True, True), other: (True, True)})
        read = Path.read_bytes
        def guarded(path):
            if path == other:
                raise AssertionError('unrelated image read')
            return read(path)
        with patch.object(Path, 'read_bytes', guarded):
            result = self.store.apply({self.file: (False, False)}, partial=True)
        self.assertFalse(result['failures'])
        self.assertEqual(result['restored'], 1)
        self.assertEqual(self.file.read_bytes(), self.original)
        self.assertNotEqual(other.read_bytes(), self.original)

    def test_partial_replacement_and_write_failure_preserve_original(self):
        self.store.apply({self.file: (True, False)})
        previous = self.file.read_bytes()
        from fh6garage.thumbnail_marks import atomic
        def fail(path, data):
            if Path(path) == self.file:
                raise OSError('in use')
            atomic(path, data)
        with patch('fh6garage.thumbnail_marks.atomic', side_effect=fail):
            result = self.store.apply({self.file: (True, True)}, partial=True)
        self.assertTrue(result['failures'])
        self.assertEqual(self.file.read_bytes(), previous)
        self.assertFalse(self.store.apply({}, restore_all=True)['failures'])
        self.assertEqual(self.file.read_bytes(), self.original)

    def test_shared_cache_not_allowed_for_single_record_delta(self):
        containers = self.root / 'containers'; containers.mkdir()
        cache = self.root / 'cache'; cache.mkdir()
        image = cache / 'shared.webp'; image.write_bytes(self.original)
        records=[]
        for name in ('one','two'):
            folder=containers/name;folder.mkdir()
            (folder/'bigThumb.webp').write_bytes(self.original)
            records.append(NS(kind='Livery',container_path=folder,container_name=name,car_id=1))
        rows=[NS(car_id=1,livery_token='same',path=image,logical_name='one')]
        with patch('fh6garage.auction_thumbnails._read_manifest_bytes',return_value=b''), patch('fh6garage.auction_manifest_registry.read_auction_manifest_registry',return_value=NS(logical_names={'one'})), patch('fh6garage.auction_thumbnails.read_thumbnail_manifest',return_value=rows), patch('fh6garage.auction_thumbnails._header_livery_token',return_value='same'):
            owners={}
            plan(records,containers,cache,AppOptions(),[True,True],ownership=owners)
            self.assertNotIn(str(image), owners)
            entries={str(p):{'active':True} for p in (image,records[0].container_path/'bigThumb.webp')}
            targets, failures=plan(records[:1],containers,cache,AppOptions(),[False],allowed_cache=owners,entries=entries)
            self.assertNotIn(str(image),targets)
            self.assertIn(str(records[0].container_path/'bigThumb.webp'),targets)
            self.assertTrue(failures)

    def test_known_unapplied_and_normal_livery_are_distinguished(self):
        window=NS(_fh6_memory_state_usable=lambda:True,_fh6_memory_livery_state_for_record=lambda r:'unapplied')
        self.assertTrue(excluded_auction(window,NS(kind='SoulBoundLivery')))
        self.assertFalse(excluded_auction(window,NS(kind='Livery')))
        window._fh6_memory_livery_state_for_record=lambda r:'review'
        self.assertFalse(excluded_auction(window,NS(kind='SoulBoundLivery')))

    def test_empty_filtered_records_do_not_read_manifest(self):
        with patch('fh6garage.auction_thumbnails.read_thumbnail_manifest',side_effect=AssertionError('manifest read')):
            self.assertEqual(plan([],self.root,self.root,AppOptions(),[]),({},[]))
