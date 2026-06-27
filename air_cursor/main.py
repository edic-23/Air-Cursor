"""Air Cursor entrypoint — wires tracking, overlay, mouse, tray and hotkeys together.

The Qt main thread owns all UI and the mouse controller. The TrackerThread does
camera + inference and only emits signals; those signals drive the overlay (paint)
and the mouse (act), so nothing blocks the UI.
"""

from __future__ import annotations

import sys

from PyQt6.QtCore import QObject, QTimer, pyqtSlot
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QApplication, QMessageBox

from . import config
from .hotkeys import HotkeyManager
from .mouse_control import MouseController
from .overlay import OverlayWindow
from .settings_window import SettingsWindow
from .tracker import TrackerThread
from .tray import Tray


class AirCursorApp(QObject):
    def __init__(self):
        super().__init__()
        self.settings = config.load()

        self.overlay = OverlayWindow(self.settings)
        self.mouse = MouseController()
        self.tray = Tray(self.settings.mist_color)
        self.settings_win: SettingsWindow | None = None
        self.tracker: TrackerThread | None = None
        self.active = False

        # Tray wiring.
        self.tray.startStopRequested.connect(self.toggle)
        self.tray.settingsRequested.connect(self.open_settings)
        self.tray.quitRequested.connect(self.quit)

        # Hotkeys.
        self.hotkeys = HotkeyManager(
            self.settings.hotkey_toggle, self.settings.hotkey_settings
        )
        self.hotkeys.toggleRequested.connect(self.toggle)
        self.hotkeys.settingsRequested.connect(self.open_settings)

        # First launch: show settings; otherwise honor enabled_on_start.
        if self.settings.first_run:
            self.settings.first_run = False
            config.save(self.settings)
            self.open_settings()
        elif self.settings.enabled_on_start:
            self.start()

    # --- tracking lifecycle ---
    def _screen_rect(self):
        geo = QGuiApplication.primaryScreen().virtualGeometry()
        return (geo.left(), geo.top(), geo.width(), geo.height())

    def start(self):
        if self.active:
            return
        self.tracker = TrackerThread(self.settings, self._screen_rect())
        self.tracker.cursorMoved.connect(self.overlay.on_cursor)
        self.tracker.cursorMoved.connect(self.on_cursor_move)
        self.tracker.gestureChanged.connect(self.overlay.on_gesture)
        self.tracker.gestureChanged.connect(self.on_gesture)
        self.tracker.handPresence.connect(self.overlay.on_presence)
        self.tracker.swipe.connect(self.on_swipe)
        self.tracker.swipeUp.connect(self.on_swipe_up)
        self.tracker.dwellClick.connect(self.on_dwell_click)
        self.tracker.dwellProgress.connect(self.overlay.on_dwell_progress)
        self.tracker.rightClick.connect(self.on_right_click)
        self.tracker.scroll.connect(self.on_scroll)
        self.tracker.error.connect(self.on_tracker_error)
        self.tracker.start()

        self.overlay.set_active(True)
        if self.settings.hide_os_cursor:
            self.mouse.hide_os_cursor()

        self.active = True
        self.tray.set_state(True)

    def stop(self):
        if not self.active:
            return
        self.mouse.release()
        if self.tracker:
            self.tracker.stop()
            self.tracker.wait(2000)
            self.tracker = None
        self.overlay.set_active(False)
        self.mouse.restore_os_cursor()
        self.active = False
        self.tray.set_state(False)

    def toggle(self):
        self.stop() if self.active else self.start()

    # --- tracker signal handlers ---
    @pyqtSlot(int, int)
    def on_cursor_move(self, x: int, y: int):
        self.mouse.move(x, y)

    @pyqtSlot(bool)
    def on_gesture(self, fist: bool):
        self.mouse.set_pressed(fist)

    @pyqtSlot(int)
    def on_swipe(self, direction: int):
        # Fast horizontal flick -> Windows app switch (Alt+Tab / Alt+Shift+Tab).
        self.mouse.alt_tab(forward=direction > 0)
        self.overlay.flash_swipe(direction)

    @pyqtSlot()
    def on_swipe_up(self):
        # Full bottom-to-top sweep -> Win+Tab (Task View).
        self.mouse.win_tab()
        self.overlay.flash_swipe_up()

    @pyqtSlot()
    def on_dwell_click(self):
        # Hover-to-click (accessibility): a full press + release.
        self.mouse.press()
        self.mouse.release()

    @pyqtSlot()
    def on_right_click(self):
        self.mouse.right_click()

    @pyqtSlot(int)
    def on_scroll(self, notches: int):
        self.mouse.scroll(notches)

    @pyqtSlot(str)
    def on_tracker_error(self, msg: str):
        self.stop()
        QMessageBox.warning(None, "Air Cursor", msg)

    # --- calibration ---
    def start_calibration(self):
        if not self.active or self.tracker is None:
            if self.settings_win:
                self.settings_win.set_calibration_status("Turn tracking on first (Ctrl+Shift+H).")
            return
        self._cal_samples = []
        self.tracker.curlSample.connect(self._collect_curl)
        if self.settings_win:
            self.settings_win.set_calibration_status("Open & close your hand a few times…", busy=True)
        QTimer.singleShot(5000, self._finish_calibration)

    @pyqtSlot(float)
    def _collect_curl(self, curl: float):
        self._cal_samples.append(curl)

    def _finish_calibration(self):
        if self.tracker is not None:
            try:
                self.tracker.curlSample.disconnect(self._collect_curl)
            except TypeError:
                pass
        samples = sorted(getattr(self, "_cal_samples", []))
        if len(samples) < 20:
            if self.settings_win:
                self.settings_win.set_calibration_status("Couldn't see your hand — try again.")
            return
        # Low band = open hand, high band = fist. Use percentiles for robustness.
        lo = samples[int(len(samples) * 0.20)]
        hi = samples[int(len(samples) * 0.85)]
        if hi - lo < 0.12:
            if self.settings_win:
                self.settings_win.set_calibration_status(
                    "Open/close more distinctly and retry.")
            return
        # Thresholds sit between the two bands with hysteresis.
        self.settings.fist_on = round(lo + (hi - lo) * 0.6, 2)
        self.settings.fist_off = round(lo + (hi - lo) * 0.35, 2)
        self.settings.clamp()
        self.apply_settings(self.settings)
        config.save(self.settings)
        if self.settings_win:
            self.settings_win.set_calibration_status(
                f"Done! on={self.settings.fist_on} off={self.settings.fist_off}")

    # --- settings ---
    def open_settings(self):
        if self.settings_win is None:
            self.settings_win = SettingsWindow(self.settings)
            self.settings_win.settingsChanged.connect(self.apply_settings)
            self.settings_win.calibrateRequested.connect(self.start_calibration)
            self.settings_win.closed.connect(self._on_settings_closed)
        self.settings_win.show()
        self.settings_win.raise_()
        self.settings_win.activateWindow()

    @pyqtSlot(object)
    def apply_settings(self, settings):
        self.settings = settings
        self.overlay.apply_settings(settings)
        self.tray.set_accent(settings.mist_color)
        self.tray.set_state(self.active)
        if self.tracker:
            self.tracker.apply_settings(settings)
        # Live-toggle cursor hiding while active.
        if self.active:
            if settings.hide_os_cursor:
                self.mouse.hide_os_cursor()
            else:
                self.mouse.restore_os_cursor()

    def _on_settings_closed(self):
        self.hotkeys.rebind(self.settings.hotkey_toggle, self.settings.hotkey_settings)

    # --- shutdown ---
    def quit(self):
        self.stop()
        self.hotkeys.unhook()
        self.mouse.shutdown()
        QApplication.instance().quit()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Air Cursor")
    app.setQuitOnLastWindowClosed(False)  # tray app keeps running without windows

    controller = AirCursorApp()
    app._air_cursor = controller  # keep a strong ref
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
