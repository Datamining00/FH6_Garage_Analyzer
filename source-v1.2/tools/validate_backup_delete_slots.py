import os,sys,tempfile,faulthandler,time,gc
from pathlib import Path
from unittest.mock import patch
faulthandler.enable();faulthandler.dump_traceback_later(60,exit=True)
source=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(source),str(source/'tests')]
os.environ['QT_QPA_PLATFORM']='offscreen';os.environ['FH6_ASSISTANT_SMOKE_TEST_MS']='60000'
with tempfile.TemporaryDirectory(prefix='fh6-delete-crash-') as state:
 os.environ['LOCALAPPDATA']=state
 from PySide6.QtCore import QSettings,QTimer,QCoreApplication,QEvent
 from PySide6.QtWidgets import QApplication,QMessageBox
 from PySide6.QtTest import QTest
 QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,state)
 q=QApplication([])
 import app;app._apply_runtime_patch_stack()
 from fh6garage.app_options import AppOptions,save_options
 save_options(AppOptions(auto_livery_detection=False,auto_backup=False))
 from test_livery_watch import WatchTests
 from fh6garage.models import ScanResult,SaveMetadata
 from fh6garage.backup_export import export_records,backup_records
 from fh6garage import v1_3_4_backup_export_patch as backup
 from fh6garage import v1_3_4_backup_lazy_load_patch as lazy
 from fh6garage.v1_3_4_backup_import_refinement_patch import _configure_backup_card
 f=WatchTests();f.root=Path(state)/'save'/'ContainersRoot';f.root.mkdir(parents=True)
 records=[f.record(i) for i in range(1,7)]
 root=Path(state)/'backups';print('EXPORT',flush=True);export_records(root,records);print('EXPORTED',flush=True)
 print('CREATE WINDOW',flush=True);w=app.MainWindow(project_root=source);w.path_edit.setText(str(f.root));w._fh6_application_controller.timer.stop()
 w.result=ScanResult(SaveMetadata(f.root,f.root.parent,f.root),liveries=records)
 print('POPULATE',flush=True);w._populate_all();w.resize(1100,760);w.show();q.processEvents()
 with patch.object(backup,'_backup_root',return_value=root):
  result=lazy._load_repository_items(root,records,lazy._CancelToken())
  cards=[]
  for i,(entry,record,location) in enumerate(result.items):
   card=w._fh6_backup_original_make_saved_content_card('livery',record,f'backup-test-{i}')
   _configure_backup_card(w,card,record,entry,location);card.setProperty('backupRecord',record);cards.append(card)
  lazy._commit_cards(w,result,cards,set());del cards,card
  w.pages.setCurrentWidget(w.backup_page)
  QTest.qWait(1200)
  while w._fh6_backup_cards:
   c=w._fh6_backup_cards[0]
   print('BEFORE DELETE',len(w._fh6_backup_cards),flush=True)
   before=[(item,item.geometry()) for item in w._fh6_backup_cards[1:]]
   def accept_delete():
    dialog=q.activeModalWidget()
    button=dialog.button(QMessageBox.StandardButton.Yes)
    c.resize(c.width()-1,c.height())
    button.click()
   QTimer.singleShot(50,accept_delete)
   c._fh6_game_move_button.click()
   print('AFTER CLICK',len(w._fh6_backup_cards),flush=True);assert c not in w._fh6_backup_cards;QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);del c;gc.collect()
   QTest.qWait(500)
   assert all(item.geometry()==geometry for item,geometry in before), 'Surviving card moved'
   assert all(item.isHidden() and not item.isEnabled() for item in w._fh6_backup_deleted_slots)
   print('EVENT LOOP SURVIVED; POSITIONS UNCHANGED',flush=True)
  assert len(w._fh6_backup_deleted_slots)==6
  empty=lazy._load_repository_items(root,records,lazy._CancelToken())
  lazy._commit_cards(w,empty,[],set())
  QTest.qWait(300)
  assert not w._fh6_backup_deleted_slots
  w.close();QTest.qWait(300)
 print('PASS',flush=True)
