import os,sys,tempfile,json,faulthandler
faulthandler.dump_traceback_later(15, exit=True)
from pathlib import Path
source=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(source))
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['FH6_ASSISTANT_SMOKE_TEST_MS']='60000'
with tempfile.TemporaryDirectory() as state:
    os.environ['LOCALAPPDATA']=state
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,state)
    q=QApplication([]);q.setQuitOnLastWindowClosed(False)
    from fh6garage.app_options import AppOptions,save_options
    save_options(AppOptions(auto_livery_detection=False))
    import app
    app._apply_runtime_patch_stack()
    print('Creating main window',flush=True)
    w=app.MainWindow(project_root=source);w.show();q.processEvents()
    print('Requesting close',flush=True)
    w._fh6_auto_backup_running=True
    assert not w.close()
    assert w._fh6_close_requested and w.isVisible()
    assert not w._fh6_application_controller.timer.isActive()
    assert not w.centralWidget().isEnabled()
    w._fh6_auto_backup_running=False
    print('Draining work',flush=True)
    QTest.qWait(350)
    assert not w.isVisible()
    print(json.dumps({'real_main_window_deferred_close':'passed','temporary_settings':True}))
    faulthandler.cancel_dump_traceback_later()
