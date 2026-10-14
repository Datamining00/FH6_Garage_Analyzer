import unittest
from types import SimpleNamespace as NS
from PySide6.QtCore import QThread, QTimer, QSemaphore
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget
from PySide6.QtTest import QTest
from fh6garage.deferred_close import active_work, closing, prepare, wait_for_close


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setCentralWidget(QWidget())
        self._fh6_application_controller=NS(timer=QTimer(self),worker=None,observer_worker=None,pending_scan='pending')
        self._fh6_application_controller.timer.start(3000)
        self.messages=[]
    def _show_status(self,message,*args):
        self.messages.append(message)
    def closeEvent(self,event):
        if active_work(self):
            event.ignore();wait_for_close(self)
        else:
            prepare(self);event.accept()


class CloseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.w=Window();self.w.show();self.app.processEvents()
    def tearDown(self):
        self.w.hide();self.w.deleteLater();self.app.processEvents()
    def test_idle_closes_immediately(self):
        self.assertTrue(self.w.close())
        self.assertTrue(closing(self.w))
        self.assertFalse(self.w.isVisible())
    def test_waits_for_all_flags_then_closes_without_second_click(self):
        self.w._fh6_auto_backup_running=True
        self.w._fh6_thumbnail_write_running=True
        self.assertFalse(self.w.close())
        self.assertFalse(self.w.centralWidget().isEnabled())
        self.assertFalse(self.w._fh6_application_controller.timer.isActive())
        self.assertIsNone(self.w._fh6_application_controller.pending_scan)
        self.w._fh6_auto_backup_running=False
        QTest.qWait(230);self.assertTrue(self.w.isVisible())
        self.w._fh6_thumbnail_write_running=False
        QTest.qWait(250);self.assertFalse(self.w.isVisible())
    def test_repeated_close_reuses_one_timer(self):
        self.w._busy_depth=1;self.w.close()
        timer=self.w._fh6_close_wait_timer
        self.w.close();self.assertIs(timer,self.w._fh6_close_wait_timer)
        self.w._busy_depth=0;QTest.qWait(250)
        self.assertFalse(self.w.isVisible())
    def test_waits_for_real_thread_and_completion_cleanup(self):
        gate=QSemaphore(0)
        class Worker(QThread):
            def run(self):gate.acquire()
        worker=Worker(self.w)
        self.w._fh6_application_controller.observer_worker=worker
        worker.start()
        try:
            self.w.close();QTest.qWait(230)
            self.assertTrue(self.w.isVisible())
            gate.release();self.assertTrue(worker.wait(2000))
            QTest.qWait(230);self.assertTrue(self.w.isVisible())
            # A finished thread alone is not enough: its UI cleanup must finish.
            self.w._fh6_application_controller.observer_worker=None
            QTest.qWait(250);self.assertFalse(self.w.isVisible())
        finally:
            gate.release();worker.wait(2000)
    def test_new_automation_is_ignored_after_close_request(self):
        from fh6garage.application_controls import ApplicationController
        from fh6garage.thumbnail_marks_ui import Controller
        from fh6garage.completion_refresh import request_refresh
        window=NS(_fh6_close_requested=True)
        # No other attributes: reaching an old start path makes these fail.
        owner=NS(window=window)
        ApplicationController.poll(owner)
        ApplicationController.start_backup(owner,[])
        ApplicationController.main_scan_committed(owner)
        Controller.request(owner)
        Controller.start(owner)
        request_refresh(window)
