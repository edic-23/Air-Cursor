"""Drive the real Windows mouse via the win32 API.

Using SendInput-style mouse_event is lower latency than PyAutoGUI and has no
artificial fail-safe pauses. We track button state so a held fist never sends
duplicate LEFTDOWN events, and we always release on shutdown.
"""

from __future__ import annotations

import ctypes

import win32api
import win32con

# Hidden ("blank") cursor support: we swap every system cursor for an invisible
# one while active, then restore. OCR_* ids cover the standard system cursors.
_OCR_IDS = [32512, 32513, 32514, 32515, 32516, 32640, 32641, 32642, 32643,
            32644, 32645, 32646, 32648, 32649, 32650, 32651]
_user32 = ctypes.windll.user32


class MouseController:
    def __init__(self) -> None:
        self._pressed = False
        self._cursor_hidden = False

    # --- movement ---
    def move(self, x: int, y: int) -> None:
        win32api.SetCursorPos((int(x), int(y)))

    # --- buttons (hold-to-hold) ---
    def press(self) -> None:
        if not self._pressed:
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            self._pressed = True

    def release(self) -> None:
        if self._pressed:
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            self._pressed = False

    def set_pressed(self, want: bool) -> None:
        if want:
            self.press()
        else:
            self.release()

    @property
    def is_pressed(self) -> bool:
        return self._pressed

    # --- right click + scroll ---
    def right_click(self) -> None:
        win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
        win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)

    def scroll(self, notches: int) -> None:
        # One wheel notch = WHEEL_DELTA (120). Positive scrolls up.
        win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, notches * 120, 0)

    # --- alt-tab (window switch) ---
    def alt_tab(self, forward: bool = True) -> None:
        """Press Alt(+Shift)+Tab once to switch windows.

        Hold Alt, tap Tab (Shift too for reverse), brief pause so the Windows
        switcher commits, then release.
        """
        import time

        VK_MENU = 0x12   # Alt
        VK_TAB = 0x09
        VK_SHIFT = 0x10
        KEYUP = win32con.KEYEVENTF_KEYUP

        win32api.keybd_event(VK_MENU, 0, 0, 0)
        if not forward:
            win32api.keybd_event(VK_SHIFT, 0, 0, 0)
        win32api.keybd_event(VK_TAB, 0, 0, 0)
        win32api.keybd_event(VK_TAB, 0, KEYUP, 0)
        time.sleep(0.04)
        if not forward:
            win32api.keybd_event(VK_SHIFT, 0, KEYUP, 0)
        win32api.keybd_event(VK_MENU, 0, KEYUP, 0)

    def win_tab(self) -> None:
        """Press Win+Tab once to open Task View."""
        import time

        VK_LWIN = 0x5B
        VK_TAB = 0x09
        KEYUP = win32con.KEYEVENTF_KEYUP

        win32api.keybd_event(VK_LWIN, 0, 0, 0)
        win32api.keybd_event(VK_TAB, 0, 0, 0)
        win32api.keybd_event(VK_TAB, 0, KEYUP, 0)
        time.sleep(0.04)
        win32api.keybd_event(VK_LWIN, 0, KEYUP, 0)

    # --- OS cursor visibility ---
    def hide_os_cursor(self) -> None:
        if self._cursor_hidden:
            return
        for ocr in _OCR_IDS:
            # Replace each system cursor with a fully transparent one.
            cur = _make_blank_cursor()
            if cur:
                _user32.SetSystemCursor(cur, ocr)
        self._cursor_hidden = True

    def restore_os_cursor(self) -> None:
        if not self._cursor_hidden:
            return
        # SPI_SETCURSORS reloads the system default cursor set.
        _user32.SystemParametersInfoW(0x0057, 0, None, 0)
        self._cursor_hidden = False

    def shutdown(self) -> None:
        self.release()
        self.restore_os_cursor()


def _make_blank_cursor():
    """Create a 1x1 fully transparent cursor handle."""
    and_mask = (ctypes.c_ubyte * 4)(0xFF, 0xFF, 0xFF, 0xFF)
    xor_mask = (ctypes.c_ubyte * 4)(0x00, 0x00, 0x00, 0x00)
    return _user32.CreateCursor(0, 0, 0, 1, 1, and_mask, xor_mask)
