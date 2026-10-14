import sys,json
from pathlib import Path
from unittest.mock import patch
source=Path(__file__).resolve().parents[1];sys.path[:0]=[str(source),str(source/'tests')]
from test_thumbnail_owner_resolution import OwnerResolutionTests
from fh6garage.thumbnail_marks_ui import Worker
from fh6garage.app_options import AppOptions
fixture=OwnerResolutionTests();fixture.setUp()
try:
 results=[]
 with patch('fh6garage.thumbnail_marks_ui.store_root',return_value=fixture.root/'originals'):
  for locked in (True,False):
   worker=Worker(None,[fixture.record],fixture.containers,fixture.cache,AppOptions(write_thumbnail_marks=True),[locked],partial=True,allowed_cache={},scope_records=[fixture.record])
   worker.completed.connect(results.append);worker.run()
 assert len(results)==2
 assert all(not result['failures'] for result in results),results
 assert results[0]['written']==2,results[0]
 assert results[1]['restored']==2,results[1]
 print(json.dumps({'partial_worker_without_owner_cache':True,'written':2,'restored':2,'failures':[],'temporary_files_only':True}),flush=True)
finally:
 fixture.doCleanups()
