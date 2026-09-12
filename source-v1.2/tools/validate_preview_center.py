import os,sys,tempfile,json
from pathlib import Path
from types import SimpleNamespace as NS
source=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(source),str(source/'tests')]
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['FH6_ASSISTANT_SMOKE_TEST_MS']='60000'
with tempfile.TemporaryDirectory() as state:
 os.environ['LOCALAPPDATA']=state
 from PySide6.QtCore import QSettings,QTimer,QRect
 from PySide6.QtWidgets import QApplication,QDialog
 from PySide6.QtTest import QTest
 from PIL import Image
 QSettings.setDefaultFormat(QSettings.IniFormat)
 QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,state)
 q=QApplication([]);q.setQuitOnLastWindowClosed(False)
 from fh6garage.app_options import AppOptions,save_options
 save_options(AppOptions(auto_livery_detection=False))
 import app;app._apply_runtime_patch_stack()
 from test_livery_watch import WatchTests
 fixture=WatchTests();fixture.root=Path(state)/'save';fixture.root.mkdir()
 record=fixture.record(1);record.thumbnail_path=record.container_path/'bigThumb.webp'
 Image.new('RGB',(540,300),'white').save(record.thumbnail_path,'WEBP')
 window=app.MainWindow(project_root=source);window.show();window.move(35,55);q.processEvents()
 from PySide6.QtWidgets import QLabel
 assert window.windowTitle()=='FH6 Assistant v1.5.1'
 assert q.applicationVersion()=='1.5.1'
 assert any(label.text()=='v1.5.1\nLIVERY & TUNING' for label in window.findChildren(QLabel))
 import runpy
 identity_checks=runpy.run_path(str(source/'tests/test_v1_4_rc1_identity_contract.py'))
 identity_checks['test_v1_4_rc1_identity_is_explicit_and_consistent']()
 identity_checks['test_performance_snapshot_uses_rc1_version']()
 result=[]
 for item in (record,NS(header=record.header,thumbnail_path=record.thumbnail_path)):
  def inspect():
   dialog=q.activeModalWidget()
   if dialog is None:result.append({'error':'no modal'});return
   area=window.screen().availableGeometry();frame=dialog.frameGeometry()
   result.append({'kind':'livery' if item is record else 'image fallback',
       'delta':[frame.center().x()-area.center().x(),frame.center().y()-area.center().y()],
       'inside':area.contains(frame),'frame':[frame.x(),frame.y(),frame.width(),frame.height()],
       'minimum':[dialog.minimumWidth(),dialog.minimumHeight()]})
   dialog.accept()
  QTimer.singleShot(100,inspect)
  window._show_livery_image(item)
 assert all(max(map(abs,r['delta']))<=1 for r in result),result
 from fh6garage.preview_position import center_in_area
 dialog=QDialog();dialog.resize(600,400);dialog.show();q.processEvents()
 for area in (QRect(-1920,0,1920,1040),QRect(1920,-200,1280,720)):
  center_in_area(dialog,area);q.processEvents()
  center_in_area(dialog,area);q.processEvents()
  frame=dialog.frameGeometry()
  assert (frame.center()-area.center()).manhattanLength()<=2,(frame,area)
  assert area.contains(frame)
 dialog.close();window.close()
 print(json.dumps({'preview_paths':result,'negative_and_offset_monitor_geometry':'passed'}),flush=True)
