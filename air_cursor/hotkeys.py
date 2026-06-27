"""Global hotkeys via the `keyboard` library.

`keyboard` callbacks fire on its own thread, so we hop back to the Qt thread with a
signal before touching any UI. Hotkeys are rebindable: call rebind() with new combos.
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal

try:
    import keyboard
except Exception:  # noqa: BLE001 - library can fail to import on locked-down systems
    keyboard = None


class HotkeyManager(QObject):
    toggleRequested = pyqtSignal()
    settingsRequested = pyqtSignal()

    def __init__(self, toggle_combo: str, settings_combo: str, parent=None):
        super().__init__(parent)
        self._toggle_combo = toggle_combo
        self._settings_combo = settings_combo
        self._handles: list = []
        self._register()

    def _register(self):
        """Register both hotkeys. Failures are swallowed per-combo so a bad combo
        (or missing permissions) never crashes the app — the tray menu still works."""
        if keyboard is None:
            return
        for combo, slot in (
            (self._toggle_combo, self.toggleRequested.emit),
            (self._settings_combo, self.settingsRequested.emit),
        ):
            try:
                self._handles.append(keyboard.add_hotkey(combo, slot))
            except Exception:  # noqa: BLE001 - invalid combo / no permission
                pass

    def rebind(self, toggle_combo: str, settings_combo: str):
        self.unhook()
        self._toggle_combo = toggle_combo
        self._settings_combo = settings_combo
        self._register()

    def unhook(self):
        if keyboard is not None:
            for h in self._handles:
                try:
                    keyboard.remove_hotkey(h)
                except (KeyError, ValueError):
                    pass
        self._handles.clear()
