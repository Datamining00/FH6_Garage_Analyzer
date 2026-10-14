import tempfile,unittest,struct,uuid
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from fh6garage.models import LiveryRecord
from fh6garage.parsers import read_header_file
from fh6garage.auction_thumbnails import _header_livery_token
from fh6garage.thumbnail_marks_ui import plan
from fh6garage.thumbnail_marks import MarkStore
from fh6garage.app_options import AppOptions
from test_header_marker_independent import _creator_relative_header

class OwnerResolutionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name);self.containers=self.root/'ContainersRoot';self.containers.mkdir()
  self.cache=self.root/'CacheThumbnails';self.cache.mkdir()
  self.record=self.make_record(1,1);self.token=_header_livery_token(self.record)
  self.image=self.cache/(str(uuid.uuid4())+'.webp');self.image.write_bytes(self.record.thumbnail_path.read_bytes())
  name=('0001_'+'a'*16+'u'+self.token+'_bigThumb.webp').encode()
  entry=struct.pack('<I',len(name))+name
  (self.cache/'.manifest').write_bytes(struct.pack('<II',2,1)+entry+uuid.UUID(self.image.stem).bytes_le+struct.pack('<IQI',1,1,1)+entry)
 def make_record(self,car,number,token_bytes=None):
  folder=self.containers/f'Livery_{car:04}_{number:014}';folder.mkdir()
  raw=_creator_relative_header('Livery',car,number,b'\1\0')
  raw=raw[:-16]+(token_bytes or number.to_bytes(16,'big'))
  (folder/'header').write_bytes(raw)
  thumb=folder/'bigThumb.webp';Image.new('RGB',(40,30),'white').save(thumb,'WEBP')
  return LiveryRecord(folder.name,folder,'Livery',read_header_file(folder/'header','Livery'),thumbnail_path=thumb)
 def planned(self,locked=True,scope=None,entries=None,allowed=None):
  return plan([self.record],self.containers,self.cache,AppOptions(),[locked],allowed_cache=allowed or {},scope_records=scope or [self.record],entries=entries)
 def test_first_lock_without_owner_cache_writes_and_unlock_restores(self):
  original=self.image.read_bytes();store=MarkStore(self.root/'originals')
  targets,errors=self.planned();self.assertFalse(errors);self.assertIn(str(self.image),targets)
  self.assertFalse(store.apply(targets,partial=True)['failures']);self.assertNotEqual(self.image.read_bytes(),original)
  targets,errors=self.planned(False,entries=store.load());self.assertFalse(errors)
  self.assertFalse(store.apply(targets,partial=True)['failures']);self.assertEqual(self.image.read_bytes(),original)
 def test_stale_owner_mapping_is_revalidated(self):
  targets,errors=self.planned(allowed={str(self.image):str(self.containers/'old')})
  self.assertFalse(errors);self.assertIn(str(self.image),targets)
 def test_unindexed_same_design_peer_blocks_cache(self):
  self.make_record(1,2,(1).to_bytes(16,'big'))
  targets,errors=self.planned();self.assertTrue(errors);self.assertNotIn(str(self.image),targets)
  self.assertIn(str(self.record.thumbnail_path),targets)
 def test_distinct_design_same_car_is_allowed_without_reading_its_image(self):
  other=self.make_record(1,2)
  read=Path.read_bytes
  def guarded(p):
   if p==other.thumbnail_path:raise AssertionError('unrelated image read')
   return read(p)
  with patch.object(Path,'read_bytes',guarded):targets,errors=self.planned()
  self.assertFalse(errors);self.assertIn(str(self.image),targets)
 def test_other_car_header_is_not_read(self):
  other=self.make_record(2,2);read=Path.read_bytes
  def guarded(p):
   if p.parent==other.container_path:raise AssertionError('other car read')
   return read(p)
  with patch.object(Path,'read_bytes',guarded):targets,errors=self.planned(scope=[self.record,other])
  self.assertFalse(errors);self.assertIn(str(self.image),targets)
 def test_incomplete_peer_blocks_cache_only(self):
  other=self.make_record(1,2);(other.container_path/'header').write_bytes(b'bad')
  targets,errors=self.planned();self.assertTrue(errors);self.assertNotIn(str(self.image),targets)
  self.assertIn(str(self.record.thumbnail_path),targets)
 def test_peer_change_during_verification_blocks_cache(self):
  other=self.make_record(1,2)
  from fh6garage import thumbnail_ownership as ownership
  read=ownership.read_header_file
  def changing(path,kind):
   result=read(path,kind)
   if Path(path).parent==other.container_path:
    with Path(path).open('ab') as f:f.write(b'x')
   return result
  with patch.object(ownership,'read_header_file',side_effect=changing):targets,errors=self.planned()
  self.assertTrue(errors);self.assertNotIn(str(self.image),targets)
