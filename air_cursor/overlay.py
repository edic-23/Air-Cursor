"""Transparent, click-through, always-on-top overlay.

Paints two things and nothing else:
  1. The hand cursor (open palm -> animates to a fist on press) at the tracked point.
  2. A colored "mist" glow inset from the screen edges, signalling the system is active.

The window never receives mouse input (WA_TransparentForMouseEvents) so a fist-click
lands on the real app underneath. The hand is drawn as vector shapes, so it scales
crisply and needs no image assets.
"""

from __future__ import annotations

import math
import os

from PyQt6.QtCore import Qt, QPointF, QRectF, QTimer, pyqtSlot
from PyQt6.QtGui import (
    QColor,
    QGuiApplication,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PyQt6.QtWidgets import QWidget

from .config import Settings

from .paths import asset

_OPEN_PNG = asset("hand_open.png")
_FIST_PNG = asset("hand_fist.png")
_OPEN_SVG = asset("hand_open.svg")
_FIST_SVG = asset("hand_fist.svg")

# Resolution we rasterize SVGs to (high enough to stay crisp at any hand size).
_SVG_RENDER_PX = 512


class OverlayWindow(QWidget):
    def __init__(self, settings: Settings):
        super().__init__()
        self._settings = settings
        self._active = False
        self._has_hand = False
        self._cursor = QPointF(-1000, -1000)
        self._fist = False
        self._fist_anim = 0.0       # 0 = open, 1 = fist (eased)
        self._prev_fist = False
        self._phase = 0.0           # ever-increasing clock for idle wiggle
        self._pop = 0.0             # click "pop" springiness, decays to 0
        self._burst = 0.0           # expanding ring on click, 1 -> 0
        self._swipe_flash = 0.0     # horizontal swipe feedback pulse, 1 -> 0
        self._swipe_dir = 1         # direction of last swipe
        self._swipe_down_flash = 0.0  # vertical (Win+L) feedback pulse, 1 -> 0
        self._dwell = 0.0           # dwell-to-click ring progress, 0..1

        # Optional custom cursors: SVG (preferred, crisp) > PNG > built-in vector art.
        self._png_open = None
        self._png_fist = None
        self.reload_cursor_images()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self._fit_to_virtual_desktop()

        # Smooth fist animation + repaint clock, capped to fps.
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.set_fps(settings.fps_cap)

    # --- geometry ---
    def virtual_rect(self):
        geo = QGuiApplication.primaryScreen().virtualGeometry()
        return geo.left(), geo.top(), geo.width(), geo.height()

    def _fit_to_virtual_desktop(self):
        left, top, w, h = self.virtual_rect()
        self._origin = (left, top)
        self.setGeometry(left, top, w, h)

    # --- public control ---
    def set_fps(self, fps: int):
        self._timer.setInterval(int(1000 / max(10, min(120, fps))))

    def apply_settings(self, settings: Settings):
        self._settings = settings
        self.set_fps(settings.fps_cap)
        self.update()

    def set_active(self, active: bool):
        self._active = active
        if active:
            self.showFullScreen() if False else self.show()
            self._timer.start()
        else:
            self._timer.stop()
            self._has_hand = False
            self.update()

    @pyqtSlot(int, int)
    def on_cursor(self, x: int, y: int):
        # Convert global screen coords to widget-local (overlay may start at negative origin).
        self._cursor = QPointF(x - self._origin[0], y - self._origin[1])
        self._has_hand = True

    @pyqtSlot(bool)
    def on_gesture(self, fist: bool):
        self._fist = fist

    @pyqtSlot(bool)
    def on_presence(self, present: bool):
        self._has_hand = present
        self.update()

    def flash_swipe(self, direction: int):
        self._swipe_dir = direction
        self._swipe_flash = 1.0

    def flash_swipe_down(self):
        self._swipe_down_flash = 1.0

    @pyqtSlot(float)
    def on_dwell_progress(self, progress: float):
        self._dwell = progress

    # --- animation / repaint ---
    def _tick(self):
        target = 1.0 if self._fist else 0.0
        # Ease toward target for a snappy-but-smooth fist transition.
        self._fist_anim += (target - self._fist_anim) * 0.45
        if abs(self._fist_anim - target) < 0.01:
            self._fist_anim = target

        # Fire a "pop" + burst on the rising edge of a click (open -> fist).
        if self._fist and not self._prev_fist:
            self._pop = 1.0
            self._burst = 1.0
        self._prev_fist = self._fist

        # Idle clock + spring decays.
        self._phase += 0.16
        self._pop *= 0.80
        if self._pop < 0.01:
            self._pop = 0.0
        self._burst *= 0.88
        if self._burst < 0.01:
            self._burst = 0.0
        self._swipe_flash *= 0.90
        if self._swipe_flash < 0.01:
            self._swipe_flash = 0.0
        self._swipe_down_flash *= 0.90
        if self._swipe_down_flash < 0.01:
            self._swipe_down_flash = 0.0
        self.update()

    # --- painting ---
    def paintEvent(self, _event):
        if not self._active:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        if self._settings.mist_enabled:
            self._paint_mist(p)
        if self._swipe_flash > 0:
            self._paint_swipe(p)
        if self._swipe_down_flash > 0:
            self._paint_swipe_down(p)
        if self._has_hand:
            self._paint_hand(p, self._cursor, self._fist_anim)
        if self._has_hand and self._dwell > 0:
            self._paint_dwell(p)

    def _paint_dwell(self, p: QPainter):
        """Arc ring that fills around the cursor as the hover-to-click completes."""
        accent = QColor(self._settings.mist_color)
        accent.setAlpha(230)
        r = self._settings.hand_size * 0.7 + 10
        rect = QRectF(self._cursor.x() - r, self._cursor.y() - r, 2 * r, 2 * r)
        p.setBrush(Qt.BrushStyle.NoBrush)
        # Faint full track behind the progress arc.
        track = QColor(accent); track.setAlpha(60)
        p.setPen(QPen(track, 6))
        p.drawEllipse(rect)
        # Progress arc (12 o'clock clockwise).
        p.setPen(QPen(accent, 6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        span = int(-360 * 16 * self._dwell)
        p.drawArc(rect, 90 * 16, span)

    def _paint_swipe(self, p: QPainter):
        """Big translucent directional chevrons pulsing toward the swipe direction."""
        f = self._swipe_flash
        w, h = self.width(), self.height()
        cy = h / 2
        accent = QColor(self._settings.mist_color)
        accent.setAlpha(int(200 * f))
        p.setPen(QPen(accent, 18, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        d = self._swipe_dir
        slide = (1.0 - f) * 120
        base_x = w / 2 + d * (160 + slide)
        for i in range(3):
            cx = base_x + d * i * 70
            size = 55
            path = QPainterPath()
            path.moveTo(cx - d * size * 0.5, cy - size)
            path.lineTo(cx + d * size * 0.5, cy)
            path.lineTo(cx - d * size * 0.5, cy + size)
            p.drawPath(path)

    def _paint_swipe_down(self, p: QPainter):
        """Downward chevrons dropping down the screen for the Win+L (lock) sweep."""
        f = self._swipe_down_flash
        w, h = self.width(), self.height()
        cx = w / 2
        accent = QColor(self._settings.mist_color)
        accent.setAlpha(int(200 * f))
        p.setPen(QPen(accent, 18, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        drop = (1.0 - f) * 120
        base_y = h / 2 + (160 + drop)
        for i in range(3):
            cy = base_y + i * 70
            size = 55
            path = QPainterPath()
            path.moveTo(cx - size, cy - size * 0.5)
            path.lineTo(cx, cy + size * 0.5)
            path.lineTo(cx + size, cy - size * 0.5)
            p.drawPath(path)

    def _paint_mist(self, p: QPainter):
        s = self._settings
        color = QColor(s.mist_color)
        w, h = self.width(), self.height()
        thick = s.mist_thickness
        peak = QColor(color)
        peak.setAlpha(s.mist_opacity)
        clear = QColor(color)
        clear.setAlpha(0)

        # Four edge gradients fading inward.
        def band(rect: QRectF, start: QPointF, end: QPointF):
            from PyQt6.QtGui import QLinearGradient
            grad = QLinearGradient(start, end)
            grad.setColorAt(0.0, peak)
            grad.setColorAt(1.0, clear)
            p.fillRect(rect, grad)

        band(QRectF(0, 0, w, thick), QPointF(0, 0), QPointF(0, thick))               # top
        band(QRectF(0, h - thick, w, thick), QPointF(0, h), QPointF(0, h - thick))   # bottom
        band(QRectF(0, 0, thick, h), QPointF(0, 0), QPointF(thick, 0))               # left
        band(QRectF(w - thick, 0, thick, h), QPointF(w, 0), QPointF(w - thick, 0))   # right

    @staticmethod
    def _load_png(path: str):
        if os.path.exists(path):
            pm = QPixmap(path)
            if not pm.isNull():
                return pm
        return None

    @staticmethod
    def _render_svg(path: str):
        """Rasterize an SVG to a high-res transparent QPixmap (crisp at any hand size)."""
        if not os.path.exists(path):
            return None
        try:
            from PyQt6.QtSvg import QSvgRenderer
        except ImportError:
            return None
        renderer = QSvgRenderer(path)
        if not renderer.isValid():
            return None
        pm = QPixmap(_SVG_RENDER_PX, _SVG_RENDER_PX)
        pm.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # Center the SVG within a square, preserving its aspect ratio.
        size = renderer.defaultSize()
        if size.width() > 0 and size.height() > 0:
            ar = size.width() / size.height()
            if ar >= 1.0:
                dw = _SVG_RENDER_PX
                dh = _SVG_RENDER_PX / ar
            else:
                dw = _SVG_RENDER_PX * ar
                dh = _SVG_RENDER_PX
            x = (_SVG_RENDER_PX - dw) / 2
            y = (_SVG_RENDER_PX - dh) / 2
            renderer.render(painter, QRectF(x, y, dw, dh))
        else:
            renderer.render(painter)
        painter.end()
        return pm

    def reload_cursor_images(self):
        """(Re)load custom cursors from disk. SVG wins over PNG; else vector fallback.

        Call after dropping new files into assets\\.
        """
        self._png_open = self._render_svg(_OPEN_SVG) or self._load_png(_OPEN_PNG)
        self._png_fist = self._render_svg(_FIST_SVG) or self._load_png(_FIST_PNG)

    def _paint_hand(self, p: QPainter, pos: QPointF, fist: float):
        """Draw the hand cursor (custom PNG if present, else vector cartoon) with
        idle wiggle, click squash-and-stretch and a burst."""

        size = self._settings.hand_size
        scale = size / 100.0

        # --- cartoon animation: idle bob + wiggle, click squash & pop ---
        bob = math.sin(self._phase) * 1.2          # gentle vertical bob (px, pre-scale)
        wiggle = math.sin(self._phase * 0.8) * 2.5 # subtle rotation (degrees)
        # Spring "pop": overshoot then settle (squash on X, stretch on Y, then snap).
        pop = self._pop
        sx = 1.0 + 0.22 * pop * math.cos(self._pop * 9)
        sy = 1.0 - 0.18 * pop * math.cos(self._pop * 9)

        accent = QColor(self._settings.mist_color)

        p.save()
        p.translate(pos)

        # Burst ring on click (expands and fades).
        if self._burst > 0:
            ring = QColor(accent)
            ring.setAlpha(int(150 * self._burst))
            radius = (1.0 - self._burst) * 60 + 18
            pen = QPen(ring, max(2.0, 6 * self._burst * scale))
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(0, 0), radius * scale, radius * scale)

        p.scale(scale, scale)
        p.translate(0, bob)
        p.rotate(wiggle)
        p.scale(sx, sy)

        # Soft accent glow behind the hand for pop on any background.
        glow = QRadialGradient(QPointF(0, 0), 78)
        gc = QColor(accent); gc.setAlpha(80)
        gc2 = QColor(accent); gc2.setAlpha(0)
        glow.setColorAt(0.0, gc)
        glow.setColorAt(1.0, gc2)
        p.setBrush(glow)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(0, 0), 78, 78)

        # If custom PNGs are provided, draw them (they inherit glow + bob + wiggle + pop).
        pix = self._png_fist if fist > 0.5 else self._png_open
        if pix is not None and not pix.isNull():
            # Draw centered, fit into the ~160-unit cartoon coordinate box.
            box = 160.0
            pr = pix.width() / pix.height() if pix.height() else 1.0
            if pr >= 1.0:
                dw, dh = box, box / pr
            else:
                dw, dh = box * pr, box
            target = QRectF(-dw / 2, -dh / 2, dw, dh)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            p.drawPixmap(target, pix, QRectF(pix.rect()))
            p.restore()
            return

        path = self._hand_path(fist)

        # Chunky black cartoon "ink" outline.
        p.setPen(QPen(QColor(25, 22, 35, 255), 9, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

        # Bright flat fill (vertical toon gradient: light top -> accent-tinted bottom).
        from PyQt6.QtGui import QLinearGradient
        body = QLinearGradient(QPointF(0, -70), QPointF(0, 60))
        top = QColor(255, 250, 230)
        bot = QColor(accent.red(), accent.green(), accent.blue())
        bot = QColor(
            (bot.red() + 255 * 2) // 3,
            (bot.green() + 255 * 2) // 3,
            (bot.blue() + 255 * 2) // 3,
        )
        body.setColorAt(0.0, top)
        body.setColorAt(1.0, bot)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(body)
        p.drawPath(path)

        # Glossy white highlight blob (top-left) for that cartoon sheen.
        hl = QColor(255, 255, 255, 200)
        p.setBrush(hl)
        p.drawEllipse(QPointF(-12, -34), 9, 14)
        hl2 = QColor(255, 255, 255, 130)
        p.setBrush(hl2)
        p.drawEllipse(QPointF(6, -8), 6, 9)

        p.restore()

    @staticmethod
    def _hand_path(fist: float) -> QPainterPath:
        """Chunky cartoon hand: fat rounded palm + 4 stubby fingers + a big thumb.

        Fingers retract as fist -> 1, exaggerated for a bouncy toon feel.
        """
        path = QPainterPath()
        # Big rounded palm.
        palm = QRectF(-34, -8, 68, 58)
        path.addRoundedRect(palm, 26, 26)

        # Stubby fingers, exaggerated retraction on fist.
        full = 46
        flen = full * (1.0 - 0.82 * fist)
        finger_w = 17
        xs = (-22, -7.5, 7.5, 22)
        for i, x in enumerate(xs):
            # Middle fingers slightly longer (cartoon proportions).
            extra = 6 if i in (1, 2) else 0
            top = -8 - flen - extra
            finger = QRectF(x - finger_w / 2, top, finger_w, flen + extra + 22)
            sub = QPainterPath()
            sub.addRoundedRect(finger, 9, 9)
            path = path.united(sub)

        # Fat thumb on the left, curls in as fist increases.
        thumb = QPainterPath()
        tlen = 32 * (1.0 - 0.55 * fist)
        thumb.addRoundedRect(QRectF(-36 - tlen, 8, tlen + 20, 18), 9, 9)
        path = path.united(thumb)
        return path
