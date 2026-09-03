from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, QEventLoop, QThread, QTimer, Slot
from PySide6.QtWidgets import QApplication

from fh6garage.preview3d.integration import _SceneReloadThread


class _ProbeReloadThread(_SceneReloadThread):
    """Use the production signal/QThread class without touching FH6 files."""

    def __init__(self, parent=None) -> None:
        QThread.__init__(self, parent)

    def run(self) -> None:
        self.completed.emit({"probe": True})


class _GuiReceiver(QObject):
    def __init__(self, loop: QEventLoop) -> None:
        super().__init__()
        self.loop = loop
        self.called = False
        self.on_gui_thread = False
        self.payload = None

    @Slot(object)
    def receive(self, payload: object) -> None:
        app = QApplication.instance()
        self.called = True
        self.payload = payload
        self.on_gui_thread = bool(app is not None and QThread.currentThread() == app.thread())
        self.loop.quit()


class Preview3DThreadRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_production_qthread_signal_reaches_gui_qobject_slot(self):
        loop = QEventLoop()
        receiver = _GuiReceiver(loop)
        worker = _ProbeReloadThread()
        worker.completed.connect(receiver.receive)
        worker.start()
        QTimer.singleShot(5000, loop.quit)
        loop.exec()
        worker.wait(5000)

        self.assertTrue(receiver.called, "3D worker result never reached the GUI receiver")
        self.assertTrue(receiver.on_gui_thread, "3D worker callback ran outside QApplication GUI thread")
        self.assertEqual(receiver.payload, {"probe": True})
        self.assertFalse(worker.isRunning())
        worker.deleteLater()


if __name__ == "__main__":
    unittest.main()
