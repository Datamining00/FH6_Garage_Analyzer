import tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace as NS
from PySide6.QtWidgets import QApplication, QWidget, QLineEdit
from PySide6.QtGui import QPixmap
from fh6garage.navigation_watch import TargetWatch, NavigationWatch, probe
from fh6garage.game_navigation import GameGridSession, NavigationItem

app = QApplication.instance() or QApplication([])

class TargetTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.path=self.root/'A';self.path.mkdir()
        for name in ('header','C_livery'):(self.path/name).write_bytes(b'valid')
    def remove(self):
        for p in self.path.iterdir():p.unlink()
        self.path.rmdir()
    def test_present_and_two_absent_samples(self):
        w=TargetWatch('A',self.path,0);self.assertEqual(w.check(0),'present')
        self.remove();self.assertEqual(w.check(1),'unknown')
        self.assertEqual(w.check(1.24),'unknown');self.assertEqual(w.check(1.25),'deleted')
    def test_partial_deletion_never_confirmed(self):
        (self.path/'header').unlink();w=TargetWatch('A',self.path,0)
        self.assertEqual(w.check(0),'unknown');self.assertEqual(w.check(100),'unknown')
    def test_missing_root_not_deleted(self):
        self.assertEqual(probe(self.root/'missing'/'A'),'unknown')
    def test_access_error_not_deleted(self):
        with patch.object(Path,'stat',side_effect=PermissionError):self.assertEqual(probe(self.path),'unknown')
    def test_disappearance_then_return_resets_confirmation(self):
        w=TargetWatch('A',self.path,0)
        with patch('fh6garage.navigation_watch.probe',side_effect=['absent','present','absent','absent']):
            self.assertEqual([w.check(t) for t in (0,.3,.4,.5)],['unknown','present','unknown','unknown'])

class ControllerTests(TargetTests):
    def setUp(self):
        super().setUp()
        self.window=QWidget();self.addCleanup(self.window.close)
        self.window.path_edit=QLineEdit(str(self.root),self.window)
        self.window._game_navigation_pending=False
        self.window._game_navigation_sessions={'livery':GameGridSession([NavigationItem('A',1),NavigationItem('B',2)])}
        self.window.result=object();self.window._show_status=lambda *a:None
        self.window._fh6_latest_livery_diff=NS(added=[])
        self.w=NavigationWatch(self.window);self.addCleanup(self.w.clear)
    def test_deletion_updates_session_only(self):
        original=self.window.result;self.w.start('A',NS(container_path=self.path));self.remove()
        with patch('fh6garage.navigation_watch.monotonic',return_value=100):self.w.tick()
        with patch('fh6garage.navigation_watch.monotonic',return_value=100.3):self.w.tick()
        self.assertFalse(self.window._game_navigation_sessions['livery'].contains('A'))
        self.assertIs(self.window.result,original);self.assertFalse(self.w.timer.isActive())
    def test_timeout_retains_target_and_next_move_rechecks(self):
        with patch('fh6garage.navigation_watch.monotonic',return_value=0):self.w.start('A',NS(container_path=self.path))
        with patch('fh6garage.navigation_watch.monotonic',return_value=31):self.w.tick()
        self.assertFalse(self.w.timer.isActive());self.assertIsNotNone(self.w.target)
        called=[];self.w.guard(lambda:called.append(True))
        self.assertEqual(called,[True]);self.assertTrue(self.window._game_navigation_sessions['livery'].contains('A'))
    def test_path_change_cancels(self):
        self.w.start('A',NS(container_path=self.path))
        previous = getattr(self.window, '_game_navigation_generation', 0)
        self.window.path_edit.setText('different')
        self.assertIsNone(self.w.target);self.assertFalse(self.w.timer.isActive())
        self.assertGreater(self.window._game_navigation_generation, previous)
    def test_new_download_refreshes_before_continuation(self):
        queue=[];called=[];old=self.window.result
        self.window._fh6_latest_livery_diff=NS(added=[object()])
        def refresh():
            called.append('refresh');self.window.result=object();self.w.scan_completed()
            self.window._fh6_latest_livery_diff=NS(added=[])
        self.window.refresh_scan=refresh
        with patch('fh6garage.navigation_watch.QTimer.singleShot',side_effect=lambda *args:queue.append(args[-1])):
            self.w.guard(lambda:called.append('move'))
            self.assertEqual(called,['refresh']);queue.pop()()
        self.assertEqual(called,['refresh','move']);self.assertIsNot(self.window.result,old)
    def test_failed_refresh_never_moves(self):
        queue=[];called=[];self.window._fh6_latest_livery_diff=NS(added=[object()])
        self.window.refresh_scan=lambda:None
        with patch('fh6garage.navigation_watch.QTimer.singleShot',side_effect=lambda *args:queue.append(args[-1])):
            self.w.guard(lambda:called.append(True));queue.pop()()
        self.assertFalse(called);self.assertFalse(self.window._game_navigation_pending)
    def test_close_releases_pending_guard(self):
        queue=[];called=[];(self.path/'header').unlink();self.w.start('A',NS(container_path=self.path))
        with patch('fh6garage.navigation_watch.QTimer.singleShot',side_effect=lambda *args:queue.append(args[-1])):
            self.w.guard(lambda:called.append(True))
        with patch('fh6garage.navigation_watch.closing',return_value=True):queue.pop()()
        self.assertFalse(called);self.assertFalse(self.window._game_navigation_pending)

class PreviewDefaults(unittest.TestCase):
    def test_stale_navigation_callback_preserves_new_pending_move(self):
        from fh6garage.ui import MainWindow
        window=NS(_game_navigation_pending=True,_game_navigation_generation=2,_show_status=lambda *args:None)
        with patch('fh6garage.ui.send_arrow_keys_to_fh6',side_effect=AssertionError('stale input sent')):
            MainWindow._execute_game_navigation(window,'livery','old',[],'delete',1,True,70)
        self.assertTrue(window._game_navigation_pending)

    def test_image_initial_scale_remains_one_after_events(self):
        from fh6garage.ui import ZoomableImageView
        p=QPixmap(1600,1200);p.fill()
        viewer=ZoomableImageView(p);viewer.resize(400,300)
        app.processEvents();self.assertEqual(viewer.current_scale(),1.0);viewer.close()
    def test_camera_reset_uses_shared_thumbnail_preset(self):
        from fh6garage.preview3d.glb_viewer import CarOpenGLWidget
        from fh6garage.preview3d.preview_presentation_patch import HOME_YAW_DEG,HOME_PITCH_DEG,HOME_DISTANCE_RADIUS
        import numpy as np
        fake=NS(_radius=2.,_home_target=np.array([0.,0.,0.]),update=lambda:None,update_zoom_label=lambda:None)
        CarOpenGLWidget.reset_camera(fake)
        self.assertEqual((fake._yaw,fake._pitch,fake._distance),(HOME_YAW_DEG,HOME_PITCH_DEG,2*HOME_DISTANCE_RADIUS))
