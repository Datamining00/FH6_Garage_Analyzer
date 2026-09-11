"""Target-only deletion observation. Never edits the save or main cards."""
from pathlib import Path
from time import monotonic
import stat
from PySide6.QtCore import QObject, QTimer
from .deferred_close import closing


def probe(path):
    path = Path(path)
    try:
        # Missing save root is not evidence that an individual livery was deleted.
        root = path.parent.stat()
        if not stat.S_ISDIR(root.st_mode):
            return 'unknown'
        try:
            directory = path.stat()
        except FileNotFoundError:
            return 'absent'
        if not stat.S_ISDIR(directory.st_mode):
            return 'unknown'
        for name in ('header', 'C_livery'):
            item = (path / name).stat()
            if not stat.S_ISREG(item.st_mode) or item.st_size <= 0:
                return 'unknown'
        return 'present'
    except OSError:
        return 'unknown'


class TargetWatch:
    def __init__(self, key, path, now=None):
        self.key, self.path = key, Path(path)
        self.started = monotonic() if now is None else now
        self.absent_since = None

    def check(self, now=None):
        now = monotonic() if now is None else now
        state = probe(self.path)
        if state != 'absent':
            self.absent_since = None
            return state
        if self.absent_since is None:
            self.absent_since = now
        return 'deleted' if now - self.absent_since >= .25 else 'unknown'


class NavigationWatch(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.target = None
        self.removed = set()
        self.waiting = False
        self.refresh_requested = False
        self.serial = 0
        self.path = window.path_edit.text().strip()
        self.timer = QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.tick)
        window.path_edit.textChanged.connect(self.clear)

    def clear(self, *_):
        self.timer.stop()
        self.target = None
        self.removed.clear()
        self.serial += 1
        self.window._game_navigation_generation = getattr(self.window, '_game_navigation_generation', 0) + 1
        if self.waiting:
            self.window._game_navigation_pending = False
        self.waiting = False
        self.refresh_requested = False
        self.path = self.window.path_edit.text().strip()

    def scan_completed(self):
        if self.refresh_requested:
            self.timer.stop()
            self.target = None
            self.removed.clear()
        else:
            self.clear()

    def start(self, key, record):
        self.target = TargetWatch(key, record.container_path)
        self.timer.start()

    def tick(self):
        if closing(self.window) or self.path != self.window.path_edit.text().strip():
            self.clear()
            return 'unknown'
        if self.target is None:
            return 'present'
        state = self.target.check()
        if state == 'deleted':
            self.removed.add(self.target.key)
            session = self.window._game_navigation_sessions.get('livery')
            if session:
                session.complete_move(self.target.key, deleted=True)
            self.target = None
            self.timer.stop()
        elif monotonic() - self.target.started >= 30:
            # Retain the target for a fresh probe at the next navigation.
            self.timer.stop()
        return state

    def guard(self, callback):
        """Resolve previous target and refresh detected additions before moving."""
        if self.waiting:
            return
        self.waiting = True
        self.window._game_navigation_pending = True
        serial = self.serial
        started = monotonic()
        old_result = None
        refreshing = False
        def finish(message=None):
            self.waiting = False
            self.refresh_requested = False
            self.window._game_navigation_pending = False
            if message:
                self.window._show_status(message, 5000)
            else:
                callback()
        def check():
            nonlocal old_result, refreshing, serial
            if closing(self.window):
                self.clear()
                return
            if serial != self.serial:
                return
            if monotonic() - started > 30:
                finish('저장 상태 확인이 지연되어 이동을 취소했습니다. 다시 시도해 주세요.')
                return
            if refreshing:
                thread = getattr(self.window, '_scan_thread', None)
                app = getattr(self.window, '_fh6_application_controller', None)
                if (thread is not None and thread.isRunning()) or getattr(app, 'pending_scan', None) is not None or getattr(self.window, '_fh6_thumbnail_write_running', False):
                    QTimer.singleShot(250, self, check)
                    return
                if self.window.result is old_result:
                    finish('새로고침이 완료되지 않아 이동을 취소했습니다.')
                    return
                finish()
                return
            state = self.tick()
            if state == 'unknown':
                self.window._show_status('이전 리버리의 삭제 여부를 확인하고 있습니다.', 1000)
                QTimer.singleShot(250, self, check)
                return
            diff = getattr(self.window, '_fh6_latest_livery_diff', None)
            if diff and diff.added:
                self.timer.stop()
                self.target = None
                self.removed.clear()
                old_result = self.window.result
                refreshing = True
                self.refresh_requested = True
                # start_scan may defer for an active observation worker.
                self.window._game_navigation_pending = False
                self.window.refresh_scan()
                self.window._game_navigation_pending = True
                QTimer.singleShot(250, self, check)
                return
            # Keep a present target until successful movement supersedes it;
            # this also allows a second check after the navigation delay.
            finish()
        check()


def controller(window):
    value = getattr(window, '_fh6_navigation_watch', None)
    if value is None:
        value = NavigationWatch(window)
        window._fh6_navigation_watch = value
    return value
