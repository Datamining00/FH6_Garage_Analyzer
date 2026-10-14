import os,sys,tempfile,json,time,faulthandler
faulthandler.dump_traceback_later(15)
from pathlib import Path
from unittest.mock import patch
source=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(source),str(source/'tests')]
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['FH6_ASSISTANT_SMOKE_TEST_MS']='60000'
with tempfile.TemporaryDirectory(prefix='fh6-navigation-ui-') as state:
 os.environ['LOCALAPPDATA']=state
 from PySide6.QtCore import QSettings,QTimer
 from PySide6.QtWidgets import QApplication,QPushButton,QDoubleSpinBox
 from PySide6.QtTest import QTest
 QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,state)
 q=QApplication([]);q.setQuitOnLastWindowClosed(False)
 def watchdog():
  d=q.activeModalWidget()
  print('WATCHDOG',d.windowTitle() if d else 'no modal',flush=True)
  os._exit(2)
 QTimer.singleShot(40000,watchdog)
 from fh6garage.app_options import AppOptions,save_options
 save_options(AppOptions(auto_livery_detection=False))
 import app;app._apply_runtime_patch_stack()
 from test_livery_watch import WatchTests
 from fh6garage.i18n import tr
 f=WatchTests();f.root=Path(state)/'save'/'ContainersRoot';f.root.mkdir(parents=True)
 a=f.record(1);b=f.record(2)
 print('construct',flush=True)
 w=app.MainWindow(project_root=source);w.path_edit.setText(str(f.root));w.start_scan(f.root)
 def wait_for(predicate,seconds=10):
  deadline=time.monotonic()+seconds
  while not predicate() and time.monotonic()<deadline:QTest.qWait(25)
  assert predicate(),'timeout'
 wait_for(lambda:w.result is not None and w._scan_thread is None)
 print('scan complete',flush=True)
 records=w.result.liveries;key=w._content_annotation_key('livery',records[0])
 calls=[]
 def choose():
  d=q.activeModalWidget();assert d is not None
  print('dialog',d.windowTitle(),flush=True)
  d.findChild(QDoubleSpinBox).setValue(.1)
  next(button for button in d.findChildren(QPushButton) if button.text()==tr('navigation.move_delete')).click()
 with patch('fh6garage.ui.send_arrow_keys_to_fh6',side_effect=lambda keys,**kw:(calls.append(keys) or 'mock game')):
  QTimer.singleShot(50,choose);w._request_game_navigation('livery',key)
  wait_for(lambda:bool(calls))
  watcher=w._fh6_navigation_watch;assert watcher.target.key==key
  original=w.result
  path=watcher.target.path
  for p in path.iterdir():p.unlink()
  path.rmdir()
  started=time.monotonic();wait_for(lambda:watcher.target is None)
  elapsed=time.monotonic()-started
  assert not w._game_navigation_sessions['livery'].contains(key)
  assert w.result is original
  # A detected addition triggers a real temporary-save scan, then the dialog.
  from types import SimpleNamespace as NS
  f.record(3);w._fh6_latest_livery_diff=NS(added=[object()])
  remaining=w.result.liveries[1];nextkey=w._content_annotation_key('livery',remaining)
  def choose_when_ready():
   if q.activeModalWidget() is None:QTimer.singleShot(25,choose_when_ready)
   else:choose()
  QTimer.singleShot(25,choose_when_ready);w._request_game_navigation('livery',nextkey)
  wait_for(lambda:len(calls)==2)
  assert w.result is not original
  assert len(w.result.liveries)==2
 w.close();q.processEvents()
 print(json.dumps({'mock_moves':len(calls),'target_deletion_detected_seconds':round(elapsed,3),'main_list_unchanged_after_target_deletion':True,'new_download_real_refresh_before_move':True,'game_input_sent':False}),flush=True)
