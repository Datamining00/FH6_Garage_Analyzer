from __future__ import annotations

import unittest

from PySide6.QtCore import QCoreApplication, QEventLoop, QObject, QThread, QTimer, Signal, Slot

from fh6garage.preview3d.integration import _start_worker


class _ProbeWorker(QObject):
    progress = Signal(str)
    finished = Signal(object)
    failed = Signal(str)

    @Slot()
    def run(self) -> None:
        self.progress.emit("probe-progress")
        self.finished.emit({"probe": True})


class _GuiReceiver(QObject):
    def __init__(self, owner: QObject, loop: QEventLoop) -> None:
        super().__init__(owner)
        self.owner = owner
        self.loop = loop
        self.called = False
        self.progress_called = False
        self.thread_finished = False
        self.on_owner_thread = False
        self.payload = None
        self.error = None

    @Slot(str)
    def progress(self, text: str) -> None:
        if text == "probe-progress":
            self.progress_called = True

    @Slot(object)
    def receive(self, payload: object) -> None:
        self.called = True
        self.payload = payload
        self.on_owner_thread = QThread.currentThread() is self.owner.thread()

    @Slot(str)
    def failed(self, text: str) -> None:
        self.error = text

    @Slot()
    def thread_done(self) -> None:
        self.thread_finished = True
        self.loop.quit()


class Preview3DThreadRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def test_production_worker_bridge_delivers_on_owner_thread(self) -> None:
        owner = QObject()
        loop = QEventLoop()
        receiver = _GuiReceiver(owner, loop)
        worker = _ProbeWorker()
        thread = _start_worker(
            owner,
            worker,
            finished_slot=receiver.receive,
            failed_slot=receiver.failed,
            progress_slot=receiver.progress,
        )
        thread.finished.connect(receiver.thread_done)
        timed_out = {"value": False}

        def timeout() -> None:
            timed_out["value"] = True
            loop.quit()

        QTimer.singleShot(2000, timeout)
        loop.exec()

        self.assertFalse(timed_out["value"], "3D worker bridge timed out")
        self.assertTrue(receiver.thread_finished)
        self.assertIsNone(receiver.error)
        self.assertTrue(receiver.progress_called)
        self.assertTrue(receiver.called)
        self.assertTrue(receiver.on_owner_thread)
        self.assertEqual(receiver.payload, {"probe": True})


if __name__ == "__main__":
    unittest.main()
