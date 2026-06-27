"""Persistent settings for Air Cursor.

Settings live in %APPDATA%\\AirCursor\\config.json. The dataclass below defines
defaults; anything missing from the JSON falls back to the default, so adding new
fields in future versions stays backward-compatible.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields


def _config_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "AirCursor")


CONFIG_DIR = _config_dir()
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")


@dataclass
class Settings:
    # --- camera / tracking ---
    camera_index: int = 0
    fps_cap: int = 30                # processing + repaint cap
    model_complexity: int = 1        # 0 = lite (faster), 1 = full (more accurate)

    # --- smoothing (One Euro Filter) ---
    # min_cutoff: lower = more smoothing when still. beta: higher = snappier when fast.
    min_cutoff: float = 1.5
    beta: float = 0.02

    # --- active zone (fraction of camera frame mapped to full screen) ---
    # A small comfortable box in the middle of the frame -> entire virtual desktop.
    # Smaller zone = less hand travel to reach edges/corners.
    zone_x: float = 0.27
    zone_y: float = 0.24
    zone_w: float = 0.46
    zone_h: float = 0.52

    # --- swipe-to-alt-tab ---
    swipe_enabled: bool = True
    swipe_speed: float = 2.2         # screen-widths/sec to count as a flick
    swipe_cooldown_s: float = 0.7    # min seconds between swipe fires

    # --- full bottom->top sweep for Win+Tab (Task View) ---
    swipe_up_enabled: bool = True
    swipe_up_bottom: float = 0.95    # must START at >= 95% down (very bottom)
    swipe_up_top: float = 0.05       # must REACH <= 5% (very top)
    swipe_up_max_time: float = 0.8   # whole sweep must complete within this many sec

    # --- axis mirroring (depends on camera mount/flip) ---
    mirror_x: bool = False           # flip if left/right is reversed
    mirror_y: bool = False           # flip if up/down is reversed

    # --- click behavior ---
    freeze_on_fist: bool = True      # lock cursor while closing so clicks don't drift
    freeze_grace: float = 2.0        # seconds frozen after closing, then unfreeze to drag

    # --- dwell click (accessibility: hover to click, no fist needed) ---
    dwell_enabled: bool = False      # off by default; fist is the primary click
    dwell_time: float = 1.0          # seconds to hold still before it clicks
    dwell_radius: int = 35           # px of allowed wobble while dwelling

    # --- gesture thresholds (curl ratio; fist = more curled) ---
    fist_on: float = 0.38            # cross above -> fist (press)
    fist_off: float = 0.25           # drop below -> open (release)
    gesture_debounce: int = 2        # consecutive frames required to switch state

    # --- right-click (peace sign ✌) ---
    rightclick_enabled: bool = True

    # --- scroll (pinch + move vertically) ---
    scroll_enabled: bool = True
    pinch_on: float = 0.45           # lateral-pinch distance below this -> scrolling
    pinch_off: float = 0.65          # release above this
    scroll_speed: float = 15.0       # wheel notches per full screen-height of hand travel

    # --- cursor appearance ---
    hand_size: int = 40              # px height of the hand sprite (~mouse-cursor size)
    hide_os_cursor: bool = True      # blank the real cursor so only the hand shows

    # --- edge mist ---
    mist_enabled: bool = True
    mist_color: str = "#ffe500"      # yellow default
    mist_thickness: int = 70         # px glow inset from edges
    mist_opacity: int = 90           # 0-255

    # --- hotkeys ---
    hotkey_settings: str = "ctrl+m"
    hotkey_toggle: str = "ctrl+shift+h"

    # --- app behavior ---
    enabled_on_start: bool = True
    first_run: bool = True

    def clamp(self) -> "Settings":
        """Keep values in sane ranges after loading or editing."""
        self.fps_cap = max(10, min(120, self.fps_cap))
        self.model_complexity = 1 if self.model_complexity not in (0, 1) else self.model_complexity
        self.min_cutoff = max(0.1, min(10.0, self.min_cutoff))
        self.beta = max(0.0, min(2.0, self.beta))
        for attr in ("zone_x", "zone_y", "zone_w", "zone_h"):
            setattr(self, attr, max(0.05, min(1.0, getattr(self, attr))))
        self.fist_off = max(0.05, min(0.95, self.fist_off))
        self.fist_on = max(self.fist_off + 0.05, min(0.98, self.fist_on))
        self.hand_size = max(40, min(400, self.hand_size))
        self.mist_thickness = max(10, min(600, self.mist_thickness))
        self.mist_opacity = max(0, min(255, self.mist_opacity))
        self.gesture_debounce = max(1, min(10, self.gesture_debounce))
        return self


def load() -> Settings:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        known = {f.name for f in fields(Settings)}
        clean = {k: v for k, v in data.items() if k in known}
        return Settings(**clean).clamp()
    except (FileNotFoundError, json.JSONDecodeError, TypeError, ValueError):
        return Settings()


def save(settings: Settings) -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
        json.dump(asdict(settings), fh, indent=2)
