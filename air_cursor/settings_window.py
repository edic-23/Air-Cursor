"""Normal, mouse-clickable settings window.

Kept separate from the click-through overlay so the real mouse can operate it while
the overlay continues to pass gestures through. Edits apply live (settingsChanged)
and persist to disk on close / Save.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QKeySequence
from PyQt6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

# Qt key names -> the strings the `keyboard` library expects.
_QT_KEY_FIXUPS = {
    "Control": "ctrl", "Ctrl": "ctrl", "Meta": "windows", "Return": "enter",
    "Escape": "esc", "PgUp": "page up", "PgDown": "page down",
}


class HotkeyEdit(QPushButton):
    """Click, then press a key combo to capture it (in `keyboard` format)."""

    changed = pyqtSignal()

    def __init__(self, combo: str):
        super().__init__()
        self._combo = combo
        self._capturing = False
        self._refresh()
        self.clicked.connect(self._begin)

    def value(self) -> str:
        return self._combo

    def _refresh(self):
        self.setText("Press keys…" if self._capturing else (self._combo or "—"))

    def _begin(self):
        self._capturing = True
        self.setFocus()
        self._refresh()

    def keyPressEvent(self, event):
        if not self._capturing:
            return super().keyPressEvent(event)
        key = event.key()
        # Ignore lone modifier presses; wait for a real key.
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
            return
        parts = []
        mods = event.modifiers()
        if mods & Qt.KeyboardModifier.ControlModifier:
            parts.append("ctrl")
        if mods & Qt.KeyboardModifier.AltModifier:
            parts.append("alt")
        if mods & Qt.KeyboardModifier.ShiftModifier:
            parts.append("shift")
        if mods & Qt.KeyboardModifier.MetaModifier:
            parts.append("windows")
        name = QKeySequence(key).toString().lower()
        name = _QT_KEY_FIXUPS.get(name, name)
        if name:
            parts.append(name)
            self._combo = "+".join(parts)
        self._capturing = False
        self._refresh()
        self.changed.emit()

from . import config
from .config import Settings

_PRESETS = [
    ("Magenta", "#ff2bd1"),
    ("Pink", "#ff7ac6"),
    ("White", "#ffffff"),
    ("Black", "#000000"),
    ("Cyan", "#00e5ff"),
]


class _Slider(QWidget):
    """Labeled slider that reports float values via a scale factor."""

    valueChangedF = pyqtSignal(float)

    def __init__(self, lo: float, hi: float, value: float, scale: int = 100):
        super().__init__()
        self._scale = scale
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._s = QSlider(Qt.Orientation.Horizontal)
        self._s.setMinimum(int(lo * scale))
        self._s.setMaximum(int(hi * scale))
        self._s.setValue(int(value * scale))
        self._lbl = QLabel(f"{value:.2f}")
        self._lbl.setMinimumWidth(44)
        self._s.valueChanged.connect(self._on)
        lay.addWidget(self._s)
        lay.addWidget(self._lbl)

    def _on(self, v):
        f = v / self._scale
        self._lbl.setText(f"{f:.2f}")
        self.valueChangedF.emit(f)


class SettingsWindow(QWidget):
    settingsChanged = pyqtSignal(object)   # emits Settings on any live edit
    calibrateRequested = pyqtSignal()      # user pressed "Calibrate fist"
    closed = pyqtSignal()

    def __init__(self, settings: Settings):
        super().__init__()
        self._s = settings
        self.setWindowTitle("Air Cursor — Settings")
        self.setMinimumWidth(420)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        root = QVBoxLayout(self)

        # --- Camera & performance ---
        perf = QGroupBox("Camera & Performance")
        pf = QFormLayout(perf)
        self._cam = QSpinBox(); self._cam.setRange(0, 8); self._cam.setValue(settings.camera_index)
        self._cam.valueChanged.connect(self._changed)
        self._fps = QSpinBox(); self._fps.setRange(10, 120); self._fps.setValue(settings.fps_cap)
        self._fps.valueChanged.connect(self._changed)
        self._model = QComboBox(); self._model.addItems(["Lite (fast)", "Full (accurate)"])
        self._model.setCurrentIndex(settings.model_complexity)
        self._model.currentIndexChanged.connect(self._changed)
        pf.addRow("Camera index", self._cam)
        pf.addRow("FPS cap", self._fps)
        pf.addRow("Model", self._model)
        root.addWidget(perf)

        # --- Feel (smoothing) ---
        feel = QGroupBox("Feel (smoothing)")
        ff = QFormLayout(feel)
        self._mincut = _Slider(0.1, 5.0, settings.min_cutoff)
        self._mincut.valueChangedF.connect(self._changed)
        self._beta = _Slider(0.0, 0.5, settings.beta)
        self._beta.valueChangedF.connect(self._changed)
        ff.addRow("Smoothness (min cutoff)", self._mincut)
        ff.addRow("Responsiveness (beta)", self._beta)
        root.addWidget(feel)

        # --- Active zone ---
        zone = QGroupBox("Active zone (smaller = less hand motion)")
        zf = QFormLayout(zone)
        self._zw = _Slider(0.2, 1.0, settings.zone_w)
        self._zw.valueChangedF.connect(self._changed)
        self._zh = _Slider(0.2, 1.0, settings.zone_h)
        self._zh.valueChangedF.connect(self._changed)
        self._mirror_x = QCheckBox("Flip left/right"); self._mirror_x.setChecked(settings.mirror_x)
        self._mirror_x.stateChanged.connect(self._changed)
        self._mirror_y = QCheckBox("Flip up/down"); self._mirror_y.setChecked(settings.mirror_y)
        self._mirror_y.stateChanged.connect(self._changed)
        zf.addRow("Zone width", self._zw)
        zf.addRow("Zone height", self._zh)
        zf.addRow("", self._mirror_x)
        zf.addRow("", self._mirror_y)
        root.addWidget(zone)

        # --- Gestures ---
        gest = QGroupBox("Gestures")
        gf = QFormLayout(gest)
        self._freeze = QCheckBox("Freeze cursor while clicking (recommended)")
        self._freeze.setChecked(settings.freeze_on_fist)
        self._freeze.stateChanged.connect(self._changed)
        self._swipe = QCheckBox("Sweep left↔right (edge to edge) → switch windows (Alt+Tab)")
        self._swipe.setChecked(settings.swipe_enabled)
        self._swipe.stateChanged.connect(self._changed)
        self._swipe_down = QCheckBox("Sweep top→bottom (edge to edge) → Lock (Win+L)")
        self._swipe_down.setChecked(settings.swipe_down_enabled)
        self._swipe_down.stateChanged.connect(self._changed)
        self._rightclick = QCheckBox("Peace sign ✌ → right-click")
        self._rightclick.setChecked(settings.rightclick_enabled)
        self._rightclick.stateChanged.connect(self._changed)
        self._scroll = QCheckBox("Sideways pinch + move up/down → scroll")
        self._scroll.setChecked(settings.scroll_enabled)
        self._scroll.stateChanged.connect(self._changed)
        self._dwell = QCheckBox("Hover to click (no fist needed — accessibility)")
        self._dwell.setChecked(settings.dwell_enabled)
        self._dwell.stateChanged.connect(self._changed)
        self._dwell_time = _Slider(0.3, 3.0, settings.dwell_time)
        self._dwell_time.valueChangedF.connect(self._changed)
        gf.addRow("", self._freeze)
        gf.addRow("", self._swipe)
        gf.addRow("", self._swipe_down)
        gf.addRow("", self._rightclick)
        gf.addRow("", self._scroll)
        gf.addRow("", self._dwell)
        gf.addRow("Hover time (sec)", self._dwell_time)
        cal_row = QHBoxLayout()
        self._calibrate_btn = QPushButton("Calibrate fist")
        self._calibrate_btn.clicked.connect(self.calibrateRequested.emit)
        self._calibrate_status = QLabel("")
        cal_row.addWidget(self._calibrate_btn)
        cal_row.addWidget(self._calibrate_status, 1)
        cal_widget = QWidget(); cal_widget.setLayout(cal_row)
        gf.addRow("Click tuning", cal_widget)
        root.addWidget(gest)

        # --- Cursor ---
        cur = QGroupBox("Cursor")
        cf = QFormLayout(cur)
        self._handsz = QSpinBox(); self._handsz.setRange(24, 400); self._handsz.setValue(settings.hand_size)
        self._handsz.valueChanged.connect(self._changed)
        self._hideos = QCheckBox("Hide real Windows cursor"); self._hideos.setChecked(settings.hide_os_cursor)
        self._hideos.stateChanged.connect(self._changed)
        cf.addRow("Hand size (px)", self._handsz)
        cf.addRow("", self._hideos)
        root.addWidget(cur)

        # --- Edge mist ---
        mist = QGroupBox("Edge mist")
        mf = QFormLayout(mist)
        self._mist_on = QCheckBox("Enabled"); self._mist_on.setChecked(settings.mist_enabled)
        self._mist_on.stateChanged.connect(self._changed)

        color_row = QHBoxLayout()
        self._color_combo = QComboBox()
        for name, hexv in _PRESETS:
            self._color_combo.addItem(name, hexv)
        self._color_combo.addItem("Custom…", "custom")
        self._select_current_color(settings.mist_color)
        self._color_combo.currentIndexChanged.connect(self._on_color_combo)
        self._swatch = QLabel(); self._swatch.setFixedSize(28, 20)
        self._set_swatch(settings.mist_color)
        color_row.addWidget(self._color_combo); color_row.addWidget(self._swatch)
        color_widget = QWidget(); color_widget.setLayout(color_row)

        self._thick = QSpinBox(); self._thick.setRange(10, 600); self._thick.setValue(settings.mist_thickness)
        self._thick.valueChanged.connect(self._changed)
        self._opacity = QSlider(Qt.Orientation.Horizontal)
        self._opacity.setRange(0, 255); self._opacity.setValue(settings.mist_opacity)
        self._opacity.valueChanged.connect(self._changed)
        mf.addRow("", self._mist_on)
        mf.addRow("Color", color_widget)
        mf.addRow("Thickness (px)", self._thick)
        mf.addRow("Opacity", self._opacity)
        root.addWidget(mist)

        # --- Hotkeys (editable: click then press a combo) ---
        hk = QGroupBox("Hotkeys (click, then press your combo)")
        hf = QFormLayout(hk)
        self._hk_toggle = HotkeyEdit(settings.hotkey_toggle)
        self._hk_toggle.changed.connect(self._changed)
        self._hk_settings = HotkeyEdit(settings.hotkey_settings)
        self._hk_settings.changed.connect(self._changed)
        hf.addRow("Toggle on/off", self._hk_toggle)
        hf.addRow("Open settings", self._hk_settings)
        root.addWidget(hk)

        # --- Buttons ---
        btns = QHBoxLayout()
        save = QPushButton("Save & Close")
        save.clicked.connect(self.close)
        btns.addStretch(1); btns.addWidget(save)
        root.addLayout(btns)

        self._custom_color = settings.mist_color

    # --- color helpers ---
    def _select_current_color(self, hexv: str):
        for i in range(self._color_combo.count()):
            if self._color_combo.itemData(i) == hexv:
                self._color_combo.setCurrentIndex(i)
                return
        self._color_combo.setCurrentIndex(self._color_combo.count() - 1)  # Custom

    def _set_swatch(self, hexv: str):
        self._swatch.setStyleSheet(
            f"background:{hexv}; border:1px solid #444; border-radius:3px;"
        )

    def _on_color_combo(self):
        data = self._color_combo.currentData()
        if data == "custom":
            initial = QColor(self._custom_color)
            chosen = QColorDialog.getColor(initial, self, "Pick mist color")
            if chosen.isValid():
                self._custom_color = chosen.name()
        self._changed()

    def _current_color(self) -> str:
        data = self._color_combo.currentData()
        return self._custom_color if data == "custom" else data

    # --- collect + emit ---
    def _changed(self, *_):
        s = self._s
        s.camera_index = self._cam.value()
        s.fps_cap = self._fps.value()
        s.model_complexity = self._model.currentIndex()
        s.min_cutoff = self._mincut._s.value() / 100.0
        s.beta = self._beta._s.value() / 100.0
        s.zone_w = self._zw._s.value() / 100.0
        s.zone_h = self._zh._s.value() / 100.0
        # Keep the zone centered for the chosen size.
        s.zone_x = max(0.0, (1.0 - s.zone_w) / 2.0)
        s.zone_y = max(0.0, (1.0 - s.zone_h) / 2.0)
        s.mirror_x = self._mirror_x.isChecked()
        s.mirror_y = self._mirror_y.isChecked()
        s.freeze_on_fist = self._freeze.isChecked()
        s.swipe_enabled = self._swipe.isChecked()
        s.swipe_down_enabled = self._swipe_down.isChecked()
        s.rightclick_enabled = self._rightclick.isChecked()
        s.scroll_enabled = self._scroll.isChecked()
        s.hotkey_toggle = self._hk_toggle.value()
        s.hotkey_settings = self._hk_settings.value()
        s.dwell_enabled = self._dwell.isChecked()
        s.dwell_time = self._dwell_time._s.value() / 100.0
        s.hand_size = self._handsz.value()
        s.hide_os_cursor = self._hideos.isChecked()
        s.mist_enabled = self._mist_on.isChecked()
        s.mist_color = self._current_color()
        s.mist_thickness = self._thick.value()
        s.mist_opacity = self._opacity.value()
        self._set_swatch(s.mist_color)
        s.clamp()
        self.settingsChanged.emit(s)

    def set_calibration_status(self, text: str, busy: bool = False):
        self._calibrate_status.setText(text)
        self._calibrate_btn.setEnabled(not busy)

    def closeEvent(self, event):
        self._changed()
        config.save(self._s)
        self.closed.emit()
        super().closeEvent(event)
