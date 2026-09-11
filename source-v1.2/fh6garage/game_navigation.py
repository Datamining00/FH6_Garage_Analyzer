from __future__ import annotations

from dataclasses import dataclass
import sys
import time
from typing import Iterable

from .i18n import tr


class GameNavigationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class NavigationItem:
    key: str
    car_id: int | None
    tie_breaker: str = ""


class GameGridSession:
    """Track a two-row, column-major, horizontally wrapping FH6 grid."""

    def __init__(self, items: Iterable[NavigationItem]):
        self.items = sorted(
            items,
            key=lambda item: (
                item.car_id is None,
                item.car_id if item.car_id is not None else 2**63 - 1,
                item.tie_breaker.casefold(),
                item.key,
            ),
        )
        self.current_key = self.items[0].key if self.items else ""

    def contains(self, key: str) -> bool:
        return any(item.key == key for item in self.items)

    def plan_from_first(self, target_key: str) -> list[str]:
        if self.items:
            self.current_key = self.items[0].key
        return self.plan_to(target_key)

    def plan_to(self, target_key: str) -> list[str]:
        if not self.items:
            raise GameNavigationError(tr("navigation.no_items"))
        keys = [item.key for item in self.items]
        if target_key not in keys:
            raise GameNavigationError(tr("navigation.target_missing"))
        if self.current_key not in keys:
            self.current_key = keys[0]

        current_index = keys.index(self.current_key)
        target_index = keys.index(target_key)
        current_row, target_row = current_index % 2, target_index % 2
        current_col, target_col = current_index // 2, target_index // 2
        top_length = (len(keys) + 1) // 2
        bottom_length = len(keys) // 2

        if current_row == target_row:
            row_length = top_length if current_row == 0 else bottom_length
            return self._horizontal(current_col, target_col, row_length)
        if current_row == 1:
            # Move to the complete top row first. This is also safe when the
            # final top column has no bottom-row item.
            return ["up"] + self._horizontal(current_col, target_col, top_length)
        # A bottom target always has a top item in the same column.
        return self._horizontal(current_col, target_col, top_length) + ["down"]

    @staticmethod
    def _horizontal(current: int, target: int, length: int) -> list[str]:
        if length <= 1 or current == target:
            return []
        right = (target - current) % length
        left = (current - target) % length
        if right <= left:
            return ["right"] * right
        return ["left"] * left

    def complete_move(
        self,
        target_key: str,
        *,
        deleted: bool,
    ) -> None:
        keys = [item.key for item in self.items]
        if target_key not in keys:
            return
        if deleted:
            self.items = [item for item in self.items if item.key != target_key]
        if not self.items:
            self.current_key = ""
            return
        # Applying leaves the grid and re-entry starts at the first item.
        # Deleting remains in the grid but FH6 also selects the first item.
        self.current_key = self.items[0].key


def _window_title(user32, ctypes, window_handle: int) -> str:
    length = user32.GetWindowTextLengthW(window_handle)
    buffer = ctypes.create_unicode_buffer(max(1, length + 1))
    user32.GetWindowTextW(window_handle, buffer, len(buffer))
    return buffer.value.strip()


def _configure_user32(user32, ctypes) -> None:
    """Declare pointer-sized Win32 signatures for 64-bit Python."""
    handle = ctypes.c_void_p
    dword = ctypes.c_ulong

    user32.GetForegroundWindow.restype = handle
    user32.GetWindowTextLengthW.argtypes = [handle]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [
        handle,
        ctypes.POINTER(ctypes.c_wchar),
        ctypes.c_int,
    ]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.IsWindowVisible.argtypes = [handle]
    user32.IsWindowVisible.restype = ctypes.c_bool
    user32.IsIconic.argtypes = [handle]
    user32.IsIconic.restype = ctypes.c_bool
    user32.ShowWindow.argtypes = [handle, ctypes.c_int]
    user32.ShowWindow.restype = ctypes.c_bool
    user32.BringWindowToTop.argtypes = [handle]
    user32.BringWindowToTop.restype = ctypes.c_bool
    user32.SetForegroundWindow.argtypes = [handle]
    user32.SetForegroundWindow.restype = ctypes.c_bool
    user32.SetActiveWindow.argtypes = [handle]
    user32.SetActiveWindow.restype = handle
    user32.SetFocus.argtypes = [handle]
    user32.SetFocus.restype = handle
    user32.GetWindowThreadProcessId.argtypes = [handle, ctypes.POINTER(dword)]
    user32.GetWindowThreadProcessId.restype = dword
    user32.AttachThreadInput.argtypes = [dword, dword, ctypes.c_bool]
    user32.AttachThreadInput.restype = ctypes.c_bool
    user32.keybd_event.argtypes = [
        ctypes.c_ubyte,
        ctypes.c_ubyte,
        ctypes.c_ulong,
        ctypes.c_size_t,
    ]


def _is_fh6_title(title: str) -> bool:
    return "forza horizon 6" in (title or "").casefold()


def _find_fh6_window(user32, ctypes) -> tuple[int, str]:
    matches: list[tuple[int, str]] = []
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def visit(window_handle, _parameter):
        if not user32.IsWindowVisible(window_handle):
            return True
        title = _window_title(user32, ctypes, window_handle)
        if _is_fh6_title(title):
            matches.append((int(window_handle), title))
        return True

    callback = callback_type(visit)
    user32.EnumWindows(callback, 0)
    if not matches:
        raise GameNavigationError(tr("navigation.window_not_found"))
    # Prefer the exact game title if auxiliary windows ever contain the same text.
    matches.sort(key=lambda item: (item[1].casefold() != "forza horizon 6", len(item[1])))
    return matches[0]


def _window_thread_id(user32, ctypes, window_handle: int) -> int:
    process_id = ctypes.c_ulong(0)
    return int(
        user32.GetWindowThreadProcessId(
            window_handle,
            ctypes.byref(process_id),
        )
        or 0
    )


def _activate_fh6_window(
    user32,
    ctypes,
    window_handle: int,
    timeout: float = 2.5,
) -> None:
    """Activate FH6 without injecting Alt or changing its window mode.

    The previous implementation briefly synthesized the Alt key to satisfy
    SetForegroundWindow restrictions.  In a normal bordered window that can
    interact with the Windows system menu (Move/Size/Minimize/Maximize/Close).

    Instead, temporarily attach the input queues of this GUI thread, the
    current foreground thread, and the FH6 window thread.  This works for
    windowed, borderless-fullscreen, and fullscreen windows while preserving
    the game's existing size/maximized state.  SW_RESTORE is used only when
    the game is actually minimized.
    """
    target = int(window_handle or 0)
    if not target:
        raise GameNavigationError(tr("navigation.no_active_window"))

    if int(user32.GetForegroundWindow() or 0) == target:
        time.sleep(0.08)
        return

    # Exclusive fullscreen can be minimized when another application receives
    # focus. Restore only in that case; never restore a normal/maximized
    # window because doing so changes the user's chosen window mode/geometry.
    if bool(user32.IsIconic(target)):
        user32.ShowWindow(target, 9)  # SW_RESTORE
        time.sleep(0.10)

    kernel32 = ctypes.windll.kernel32
    kernel32.GetCurrentThreadId.restype = ctypes.c_ulong
    current_thread = int(kernel32.GetCurrentThreadId() or 0)

    foreground = int(user32.GetForegroundWindow() or 0)
    foreground_thread = (
        _window_thread_id(user32, ctypes, foreground)
        if foreground
        else 0
    )
    target_thread = _window_thread_id(user32, ctypes, target)

    attached_pairs: list[tuple[int, int]] = []

    def attach(first: int, second: int) -> None:
        if not first or not second or first == second:
            return
        pair = (first, second)
        reverse_pair = (second, first)
        if pair in attached_pairs or reverse_pair in attached_pairs:
            return
        if user32.AttachThreadInput(first, second, True):
            attached_pairs.append(pair)

    # Joining the queues removes the need for synthetic modifier keys and lets
    # Windows perform a normal foreground transition regardless of whether FH6
    # is bordered, borderless, or exclusive fullscreen.
    attach(current_thread, foreground_thread)
    attach(current_thread, target_thread)

    try:
        user32.BringWindowToTop(target)
        user32.SetForegroundWindow(target)
        user32.SetActiveWindow(target)
        user32.SetFocus(target)
    finally:
        for first, second in reversed(attached_pairs):
            user32.AttachThreadInput(first, second, False)

    deadline = time.monotonic() + max(0.5, timeout)
    while time.monotonic() < deadline:
        if int(user32.GetForegroundWindow() or 0) == target:
            # Give DirectInput/XInput-style game loops a short frame window to
            # observe the focus transition before keyboard navigation begins.
            time.sleep(0.18)
            return
        # A harmless retry is useful after exclusive fullscreen restoration.
        user32.SetForegroundWindow(target)
        time.sleep(0.05)

    title = _window_title(user32, ctypes, target)
    raise GameNavigationError(
        tr("navigation.activation_failed", title=title or tr("detail.no_title"))
    )


def send_arrow_keys_to_fh6(
    keys: list[str],
    interval: float = 0.07,
    *,
    auto_activate: bool = True,
) -> str:
    """Activate FH6 when requested, verify focus, then send arrow keys.

    The same path is used for normal windowed, borderless fullscreen, and
    fullscreen modes. No mouse clicks or synthetic Alt input are generated.
    """
    if sys.platform != "win32":
        raise GameNavigationError(tr("navigation.windows_only"))

    import ctypes

    user32 = ctypes.windll.user32
    _configure_user32(user32, ctypes)
    if auto_activate:
        target_window, title = _find_fh6_window(user32, ctypes)
        _activate_fh6_window(user32, ctypes, target_window)
    else:
        target_window = int(user32.GetForegroundWindow() or 0)
        title = _window_title(user32, ctypes, target_window) if target_window else ""

    if not target_window:
        raise GameNavigationError(tr("navigation.no_active_window"))
    if not _is_fh6_title(title):
        raise GameNavigationError(
            tr("navigation.wrong_window", title=title or tr("detail.no_title"))
        )

    virtual_keys = {
        "left": 0x25,
        "up": 0x26,
        "right": 0x27,
        "down": 0x28,
    }
    key_up = 0x0002

    def ensure_focus() -> None:
        if int(user32.GetForegroundWindow() or 0) != int(target_window):
            raise GameNavigationError(tr("navigation.focus_changed"))

    def press_arrow(name: str) -> None:
        ensure_focus()
        vk = virtual_keys.get(name)
        if vk is None:
            raise GameNavigationError(tr("navigation.unsupported_key", key=name))
        hold_time = min(0.015, max(0.005, interval / 3))
        user32.keybd_event(vk, 0, 0, 0)
        time.sleep(hold_time)
        user32.keybd_event(vk, 0, key_up, 0)
        time.sleep(max(0.001, interval - hold_time))

    for name in keys:
        press_arrow(name)
    return title
