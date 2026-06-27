"""Camera capture + MediaPipe hand landmark detection on a background thread.

Runs the camera loop off the Qt UI thread and communicates results purely through
Qt signals (thread-safe). Emits the smoothed, screen-mapped cursor position and the
debounced fist state, plus FPS and hand-presence status.
"""

from __future__ import annotations

import os
import time

import cv2
from PyQt6.QtCore import QThread, pyqtSignal

import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import (
    HandLandmarker,
    HandLandmarkerOptions,
    RunningMode,
)

from .config import Settings
from .gestures import (
    FistDetector,
    curl_ratio,
    extended_fingers,
    is_lateral_pinch,
    is_peace,
    palm_center,
    pinch_distance,
)
from .mapping import map_to_screen
from .one_euro import OneEuroFilter2D
from .paths import asset


def _model_path() -> str:
    """Path to the bundled hand model (works from source and frozen .exe)."""
    return asset("hand_landmarker.task")


_MODEL_PATH = _model_path()


def _open_camera(index: int):
    """Open a camera, trying multiple backends.

    Virtual cameras (GlideX, OBS, DroidCam, etc.) don't always answer on the same
    backend a built-in webcam would, so we try DirectShow, then Media Foundation,
    then OpenCV's default. Returns an opened VideoCapture or None.
    """
    for backend in (cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY):
        cap = cv2.VideoCapture(index, backend)
        if cap.isOpened():
            ok, _ = cap.read()
            if ok:
                return cap
        cap.release()
    return None


class TrackerThread(QThread):
    cursorMoved = pyqtSignal(int, int)
    gestureChanged = pyqtSignal(bool)
    fpsUpdated = pyqtSignal(float)
    handPresence = pyqtSignal(bool)
    swipe = pyqtSignal(int)         # +1 = swipe right, -1 = swipe left
    swipeUp = pyqtSignal()          # full bottom->top sweep (Win+Tab / Task View)
    dwellProgress = pyqtSignal(float)  # 0..1 ring fill while hovering to click
    dwellClick = pyqtSignal()       # dwell completed -> perform a click
    curlSample = pyqtSignal(float)  # raw curl ratio each frame (for calibration)
    rightClick = pyqtSignal()       # peace sign -> single right-click
    scroll = pyqtSignal(int)        # wheel notches (+ up / - down)
    error = pyqtSignal(str)

    def __init__(self, settings: Settings, screen_rect, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._screen = screen_rect  # (left, top, width, height) of virtual desktop
        self._running = False
        self._filter = OneEuroFilter2D(settings.min_cutoff, settings.beta)
        self._fist = FistDetector(settings.fist_on, settings.fist_off, settings.gesture_debounce)
        self._had_hand = False
        # Freeze-on-fist: hold the cursor still briefly while the hand closes.
        self._frozen_pos: tuple[int, int] | None = None
        self._freeze_start = 0.0
        self._prev_fist = False
        # Swipe detection: track recent x positions for velocity.
        self._last_x: float | None = None
        self._last_x_t = 0.0
        self._swipe_cooldown = 0.0
        # Vertical full-sweep (bottom -> top) for Win+Tab.
        self._bottom_armed_t: float | None = None
        self._swipe_up_cooldown = 0.0
        # Dwell-to-click: anchor position + when we started holding still.
        self._dwell_anchor: tuple[int, int] | None = None
        self._dwell_start = 0.0
        self._dwell_fired = False
        # Right-click (peace): edge-triggered so one hold = one click.
        self._peace_active = False
        self._peace_streak = 0          # frames the peace pose has persisted
        # Pinch-scroll: track pinch state + last y while pinching.
        self._pinching = False
        self._scroll_last_y: float | None = None
        self._scroll_residual = 0.0

    # Called from the UI thread; the loop reads these live each frame.
    def apply_settings(self, settings: Settings) -> None:
        self._settings = settings
        self._filter.update_params(settings.min_cutoff, settings.beta)
        self._fist.update_params(settings.fist_on, settings.fist_off, settings.gesture_debounce)

    def set_screen(self, screen_rect) -> None:
        self._screen = screen_rect

    def _detect_swipe(self, px: float, t: float) -> None:
        """Fire a swipe when the cursor crosses the screen fast horizontally.

        Uses screen-space x velocity. A quick flick (faster than normal pointing)
        triggers alt-tab; a cooldown prevents repeat fires from one motion.
        """
        s = self._settings
        if not s.swipe_enabled:
            return
        if self._last_x is None:
            self._last_x = px
            self._last_x_t = t
            return
        dt = t - self._last_x_t
        if dt <= 0:
            return
        screen_w = max(1, self._screen[2])
        vx = (px - self._last_x) / dt / screen_w   # fraction of screen width / sec
        self._last_x = px
        self._last_x_t = t

        if t < self._swipe_cooldown:
            return
        if abs(vx) >= s.swipe_speed:
            self.swipe.emit(1 if vx > 0 else -1)
            self._swipe_cooldown = t + s.swipe_cooldown_s

    def _detect_swipe_up(self, py: float, t: float) -> None:
        """Fire Win+Tab on a full sweep from the very bottom to the very top.

        Requires the cursor to start in the bottom band (>= bottom_thresh of the
        screen, e.g. 95-100%) and reach the top band (<= top_thresh, e.g. 0-5%)
        within max_time seconds. A partial sweep does nothing.
        """
        s = self._settings
        if not s.swipe_up_enabled:
            return
        screen_h = max(1, self._screen[3])
        # py is absolute pixels; convert to fraction 0 (top) .. 1 (bottom).
        frac = (py - self._screen[1]) / screen_h

        if frac >= s.swipe_up_bottom:          # hand in the bottom band -> arm
            self._bottom_armed_t = t
        elif self._bottom_armed_t is not None:
            within = (t - self._bottom_armed_t) <= s.swipe_up_max_time
            if frac <= s.swipe_up_top and within and t >= self._swipe_up_cooldown:
                self.swipeUp.emit()
                self._swipe_up_cooldown = t + s.swipe_cooldown_s
                self._bottom_armed_t = None
            elif not within:
                self._bottom_armed_t = None     # took too long, disarm

    def _detect_dwell(self, px: int, py: int, t: float) -> None:
        """Click when the cursor is held still within a small radius for dwell_time.

        Accessibility feature: lets people click without making a fist. Emits a 0..1
        progress for the ring UI and a dwellClick when the hold completes.
        """
        s = self._settings
        if not s.dwell_enabled:
            if self._dwell_anchor is not None:
                self._dwell_anchor = None
                self.dwellProgress.emit(0.0)
            return

        if self._dwell_anchor is None:
            self._dwell_anchor = (px, py)
            self._dwell_start = t
            self._dwell_fired = False
            return

        dx = px - self._dwell_anchor[0]
        dy = py - self._dwell_anchor[1]
        if (dx * dx + dy * dy) ** 0.5 > s.dwell_radius:
            # Moved too far -> reset the dwell.
            self._dwell_anchor = (px, py)
            self._dwell_start = t
            self._dwell_fired = False
            self.dwellProgress.emit(0.0)
            return

        held = t - self._dwell_start
        progress = min(1.0, held / max(0.1, s.dwell_time))
        self.dwellProgress.emit(progress)
        if progress >= 1.0 and not self._dwell_fired:
            self._dwell_fired = True
            self.dwellClick.emit()
            # Require leaving the radius before another dwell-click can arm.

    def _reset_open_hand_gestures(self) -> None:
        """Clear swipe/dwell state so secondary poses don't leave them armed."""
        self._last_x = None
        self._bottom_armed_t = None
        self._dwell_anchor = None

    def _suppress_fist(self) -> None:
        """A secondary pose (pinch/peace) overrides the fist: drop fist state so a
        held left-button releases cleanly and the next real fist re-arms freeze."""
        self._fist.reset()
        self._prev_fist = False
        self._frozen_pos = None

    def _update_pinch(self, lm) -> bool:
        """Lateral-pinch detector for scroll, with hysteresis.

        Engages only on a clear sideways pinch that is NOT a fist (so a closed fist
        can never be mistaken for scroll). Once engaged, it stays active while the
        pinch is held and the hand isn't a fist, so a little orientation drift mid-
        scroll won't drop it.
        """
        s = self._settings
        if self._pinching:
            d = pinch_distance(lm)
            _idx, mid, ring, pinky = extended_fingers(lm)
            not_fist = mid or ring or pinky
            self._pinching = d < s.pinch_off and not_fist
        else:
            self._pinching = is_lateral_pinch(lm, s.pinch_on)
        return self._pinching

    def _do_scroll(self, py: float) -> None:
        """Turn vertical cursor movement (while pinching) into wheel notches.

        Moving the hand UP scrolls UP. Accumulates sub-notch motion so slow drags
        still scroll smoothly.
        """
        if self._scroll_last_y is None:
            self._scroll_last_y = py
            self._scroll_residual = 0.0
            return
        screen_h = max(1, self._screen[3])
        dy_frac = (self._scroll_last_y - py) / screen_h   # up = positive
        self._scroll_last_y = py
        # scroll_speed = wheel notches per full screen-height of hand travel.
        self._scroll_residual += dy_frac * self._settings.scroll_speed
        notches = int(self._scroll_residual)
        if notches != 0:
            self._scroll_residual -= notches
            self.scroll.emit(notches)

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        self._running = True
        s = self._settings

        cap = _open_camera(s.camera_index)
        if cap is None:
            self.error.emit(
                f"Could not open camera #{s.camera_index}.\n\n"
                "If you're using GlideX (phone as webcam): make sure the GlideX "
                "camera is running, then try a different Camera index in Settings "
                "(0, 1, 2…)."
            )
            return
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        model_path = os.path.abspath(_MODEL_PATH)
        if not os.path.exists(model_path):
            self.error.emit("hand_landmarker.task model not found in assets/.")
            cap.release()
            return

        options = HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            running_mode=RunningMode.VIDEO,
            num_hands=1,
            min_hand_detection_confidence=0.5,
            min_hand_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )

        try:
            landmarker = HandLandmarker.create_from_options(options)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"Failed to load hand model: {exc}")
            cap.release()
            return

        self._filter.reset()
        self._fist.reset()

        last_fps_t = time.time()
        frames = 0

        try:
            while self._running:
                loop_start = time.time()
                ok, frame = cap.read()
                if not ok:
                    continue

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                ts_ms = int(loop_start * 1000)
                result = landmarker.detect_for_video(mp_image, ts_ms)

                if result.hand_landmarks:
                    lm = [(p.x, p.y) for p in result.hand_landmarks[0]]
                    if not self._had_hand:
                        self._had_hand = True
                        self.handPresence.emit(True)

                    s = self._settings  # re-read for live edits
                    ax, ay = palm_center(lm)
                    fx, fy = self._filter(ax, ay, loop_start)
                    px, py = map_to_screen(
                        fx, fy,
                        s.zone_x, s.zone_y, s.zone_w, s.zone_h,
                        self._screen[0], self._screen[1], self._screen[2], self._screen[3],
                        s.mirror_x, s.mirror_y,
                    )

                    self.curlSample.emit(curl_ratio(lm))

                    # --- secondary poses (pinch=scroll, peace=right-click) take
                    # priority and suppress the fist so gestures don't fight. ---
                    pinching = self._update_pinch(lm) if s.scroll_enabled else False
                    # Debounce peace a couple frames so a transient pose while the
                    # hand forms a fist can't fire a phantom right-click.
                    if not pinching and s.rightclick_enabled and is_peace(lm):
                        self._peace_streak += 1
                    else:
                        self._peace_streak = 0
                    peace = self._peace_streak >= s.gesture_debounce

                    if pinching:
                        # Pinch-scroll: vertical hand motion -> wheel notches.
                        self._suppress_fist()
                        self._do_scroll(py)
                        self.cursorMoved.emit(px, py)
                        self.gestureChanged.emit(False)
                        self._reset_open_hand_gestures()
                    elif peace:
                        # Right-click once on the rising edge of the peace sign.
                        self._suppress_fist()
                        self._scroll_last_y = None
                        if not self._peace_active:
                            self._peace_active = True
                            self.rightClick.emit()
                        self.cursorMoved.emit(px, py)
                        self.gestureChanged.emit(False)
                        self._reset_open_hand_gestures()
                    else:
                        self._scroll_last_y = None
                        self._peace_active = False
                        fist = self._fist.update(lm)

                        # Freeze-on-fist (with grace window): lock the cursor when the
                        # hand begins to close so the click lands precisely, then
                        # release the lock after freeze_grace seconds so you can still
                        # DRAG (move a window) while the button stays held down.
                        if fist and not self._prev_fist:
                            self._frozen_pos = (px, py)
                            self._freeze_start = loop_start
                        elif not fist:
                            self._frozen_pos = None
                        self._prev_fist = fist

                        frozen_active = (
                            s.freeze_on_fist
                            and fist
                            and self._frozen_pos is not None
                            and (loop_start - self._freeze_start) < s.freeze_grace
                        )
                        out_x, out_y = self._frozen_pos if frozen_active else (px, py)
                        self.cursorMoved.emit(out_x, out_y)
                        self.gestureChanged.emit(fist)

                        # Swipe + dwell: only when the hand is open (not mid-click).
                        if not fist:
                            self._detect_swipe(px, loop_start)
                            self._detect_swipe_up(py, loop_start)
                            self._detect_dwell(out_x, out_y, loop_start)
                        else:
                            self._reset_open_hand_gestures()
                else:
                    if self._had_hand:
                        self._had_hand = False
                        self._filter.reset()
                        self.handPresence.emit(False)

                # FPS accounting.
                frames += 1
                now = time.time()
                if now - last_fps_t >= 0.5:
                    self.fpsUpdated.emit(frames / (now - last_fps_t))
                    frames = 0
                    last_fps_t = now

                # Respect FPS cap.
                target_dt = 1.0 / max(1, self._settings.fps_cap)
                elapsed = time.time() - loop_start
                sleep_for = target_dt - elapsed
                if sleep_for > 0:
                    time.sleep(sleep_for)
        finally:
            try:
                landmarker.close()
            except Exception:  # noqa: BLE001
                pass
            cap.release()
