import tempfile, unittest, struct, uuid
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
from PIL import Image
from fh6garage.thumbnail_marks_ui import plan
from fh6garage.thumbnail_marks import MarkStore
from fh6garage.app_options import AppOptions
from fh6garage.game_navigation import GameGridSession, NavigationItem

class RegisteredThumbnailTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.cache=self.root/'cache';self.cache.mkdir()
        self.containers=self.root/'containers';self.containers.mkdir()
        folder=self.containers/'Livery_1';folder.mkdir()
        self.record=NS(kind='Livery',container_name=folder.name,container_path=folder,car_id=1)
        self.folder=folder/'bigThumb.webp';Image.new('RGB',(32,32),'white').save(self.folder,'WEBP')
        self.images=[self.cache/(str(uuid.uuid4())+'.webp') for _ in range(2)]
        for p in self.images:p.write_bytes(self.folder.read_bytes())
        self.names=['0001_'+str(i)*16+'u'+'a'*26+'_bigThumb.webp' for i in range(2)]
        self.manifest([0])
        self.addCleanup(patch.stopall)
        patch('fh6garage.auction_thumbnails._header_livery_token',return_value='a'*26).start()
    def manifest(self,active):
        def name(s):
            b=s.encode();return struct.pack('<I',len(b))+b
        b=struct.pack('<II',2,2)
        for s,p in zip(self.names,self.images):b+=name(s)+uuid.UUID(p.stem).bytes_le
        b+=struct.pack('<IQI',1,1,len(active))+b''.join(name(self.names[i]) for i in active)
        (self.cache/'.manifest').write_bytes(b)
    def run_plan(self,lock,entries=None):
        return plan([self.record],self.containers,self.cache,AppOptions(),[lock],entries=entries)
    def test_unmarked_untracked_skips_manifest_and_header(self):
        with patch('fh6garage.auction_thumbnails._read_manifest_bytes',side_effect=AssertionError),patch('fh6garage.auction_thumbnails._header_livery_token',side_effect=AssertionError):
            self.assertEqual(self.run_plan(False),({},[]))
    def test_only_registered_cache_plus_folder(self):
        targets,errors=self.run_plan(True)
        self.assertEqual(set(targets),{str(self.folder),str(self.images[0])});self.assertFalse(errors)
    def test_no_registered_cache_only_folder_without_warning(self):
        self.manifest([]);targets,errors=self.run_plan(True)
        self.assertEqual(set(targets),{str(self.folder)});self.assertFalse(errors)
    def test_two_registered_remain_ambiguous(self):
        self.manifest([0,1]);targets,errors=self.run_plan(True)
        self.assertEqual(set(targets),{str(self.folder)});self.assertEqual(len(errors),1)
    def test_unlock_restores_previously_marked_folder_and_two_caches(self):
        store=MarkStore(self.root/'originals');paths=[self.folder,*self.images]
        originals={str(p):p.read_bytes() for p in paths}
        store.apply({p:(False,True) for p in paths});self.manifest([])
        targets,errors=self.run_plan(False,store.load());self.assertFalse(errors)
        result=store.apply(targets);self.assertEqual(result['restored'],3)
        self.assertFalse(result['failures'])
        for p in paths:self.assertEqual(p.read_bytes(),originals[str(p)])
    def test_shared_unmarked_record_cannot_be_overwritten(self):
        other=NS(kind='Livery',container_name='other',container_path=self.containers/'other',car_id=1)
        other.container_path.mkdir()
        targets,errors=plan([self.record,other],self.containers,self.cache,AppOptions(),[True,False])
        self.assertNotIn(str(self.images[0]),targets);self.assertTrue(errors)

class NavigationStalenessEvidence(unittest.TestCase):
    def test_unobserved_deletion_changes_required_arrows(self):
        records=[NavigationItem(str(i),i) for i in range(8)]
        stale=GameGridSession(records)
        current=GameGridSession(records[1:])
        self.assertNotEqual(stale.plan_from_first('4'),current.plan_from_first('4'))
        self.assertEqual(stale.plan_from_first('4'),['right','right'])
        self.assertEqual(current.plan_from_first('4'),['right','down'])
