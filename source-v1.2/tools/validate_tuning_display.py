import os,sys,tempfile,json
from pathlib import Path
source=Path(__file__).resolve().parents[1];sys.path.insert(0,str(source))
os.environ['QT_QPA_PLATFORM']='offscreen';os.environ['FH6_ASSISTANT_SMOKE_TEST_MS']='60000'
with tempfile.TemporaryDirectory(prefix='fh6-tuning-display-') as state:
 os.environ['LOCALAPPDATA']=state
 from PySide6.QtCore import QSettings
 from PySide6.QtWidgets import QApplication
 QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,state)
 q=QApplication([])
 from fh6garage.app_options import AppOptions,save_options
 save_options(AppOptions(auto_livery_detection=False,auto_backup=False,write_thumbnail_marks=False))
 import app;app._apply_runtime_patch_stack()
 from fh6garage.models import HeaderInfo,LiveryRecord,TuningRecord,ScanResult,SaveMetadata
 root=Path(state)/'ContainersRoot';root.mkdir()
 records=[]
 for kind in ('Livery','SoulBoundLivery'):
  folder=root/(kind+'_0269_20260912000000');folder.mkdir()
  records.append(LiveryRecord(folder.name,folder,kind,HeaderInfo(name=kind,car_id=269,guid=kind)))
 count=int(sys.argv[1]) if len(sys.argv)>1 else 1
 tunings=[]
 for i in range(count):
  folder=root/f'Tuning_0269_{20260912000000+i}';folder.mkdir()
  tunings.append(TuningRecord(folder.name,folder,HeaderInfo(name=f'test tuning {i}',car_id=269,guid=f'tuning-{i}')))
 w=app.MainWindow(project_root=source);w.path_edit.setText(str(root))
 result=ScanResult(SaveMetadata(root,root,root),records,tunings)
 w._scan_finished(result);q.processEvents()
 assert len(w._tuning_grid_cards)==count
 w._populate_saved_content_table('tuning')
 assert w.tuning_table.rowCount()==count
 assert w.card_tuning.value.text()==str(count)
 assert w.card_livery.value.text().endswith('/ 1'),w.card_livery.value.text()
 assert w.card_auction.value.text().endswith('/ 1'),w.card_auction.value.text()
 from fh6garage.v1_3_2_dashboard_change_group_patch import _update_dashboard_summary
 w._fh6_memory_state_usable=lambda:True
 w._fh6_memory_livery_state_for_record=lambda record:'applied' if record.kind=='Livery' else 'unapplied'
 _update_dashboard_summary(w)
 assert w.card_livery.value.text()=='1 / 1',w.card_livery.value.text()
 assert w.card_auction.value.text()=='0 / 1',w.card_auction.value.text()
 print(json.dumps({'tuning_cards':count,'tuning_table_rows':count,'regular_applied_total':w.card_livery.value.text(),'auction_applied_total':w.card_auction.value.text(),'mixed_population_complete':True,'synthetic_data':True}),flush=True)
 w.close();q.processEvents()
