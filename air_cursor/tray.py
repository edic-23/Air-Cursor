"""System tray icon + menu.

Shows active/inactive state and offers Start/Stop, Settings and Quit. The icon is
drawn in code (a hand glyph on a colored disc) so no image asset is required.
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QIcon, QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon


def make_icon(active: bool, accent: str = "#ff2bd1") -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    disc = QColor(accent) if active else QColor(90, 90, 100)
    p.setBrush(disc)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(2, 2, 60, 60)

    # Simple hand glyph.
    p.setBrush(QColor(255, 255, 255, 240))
    path = QPainterPath()
    path.addRoundedRect(QRectF(24, 28, 16, 20), 6, 6)
    for i, x in enumerate((22, 28, 34, 40)):
        path.addRoundedRect(QRectF(x - 3, 16 + (0 if i in (1, 2) else 4), 6, 18), 3, 3)
    p.drawPath(path)
    p.end()
    return QIcon(pm)


class Tray(QObject):
    startStopRequested = pyqtSignal()
    settingsRequested = pyqtSignal()
    quitRequested = pyqtSignal()

    def __init__(self, accent: str, parent=None):
        super().__init__(parent)
        self._accent = accent
        self._icon = QSystemTrayIcon(make_icon(False, accent), parent)
        self._icon.setToolTip("Air Cursor — inactive")

        menu = QMenu()
        self._start_action = QAction("Start", menu)
        self._start_action.triggered.connect(self.startStopRequested.emit)
        settings_action = QAction("Settings…", menu)
        settings_action.triggered.connect(self.settingsRequested.emit)
        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self.quitRequested.emit)

        menu.addAction(self._start_action)
        menu.addAction(settings_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self._icon.setContextMenu(menu)
        self._icon.activated.connect(self._on_activated)
        self._icon.show()

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.startStopRequested.emit()

    def set_state(self, active: bool):
        self._icon.setIcon(make_icon(active, self._accent))
        self._icon.setToolTip(f"Air Cursor — {'active' if active else 'inactive'}")
        self._start_action.setText("Stop" if active else "Start")

    def set_accent(self, accent: str):
        self._accent = accent

    def message(self, title: str, body: str):
        self._icon.showMessage(title, body, QSystemTrayIcon.MessageIcon.Information, 2500)
