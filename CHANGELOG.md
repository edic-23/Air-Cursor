# Changelog

## v2.0 — Gesture suite

- **Right-click** with a ✌️ peace sign (index + middle extended), debounced so it
  can't misfire while forming a fist.
- **Scroll** by pinching (🤏 thumb + index) and moving the hand up/down; speed is
  configurable and accumulates sub-notch motion for smooth scrolling.
- **Editable hotkeys** — click a field in Settings and press your combo to rebind live.
- Gesture-priority handling so pinch / peace / fist never fight; secondary poses
  cleanly release a held left-button.
- New Settings toggles for every gesture.

## v1.0 — First release

- Real-time hand tracking (MediaPipe Hand Landmarker) driving the **real OS mouse**.
- Open-hand cursor; **fist = click & drag** (freeze-on-fist with a grace window so you
  can still drag windows).
- **Alt+Tab** on a fast sideways flick; **Win+Tab** (Task View) on a full bottom→top sweep.
- **Dwell / hover-to-click** accessibility mode (no fist required).
- Calibrated active zone, One Euro Filter smoothing, colored edge "mist" with color picker.
- Custom cursor art (SVG/PNG) with built-in cartoon fallback, glow, wiggle and click-pop.
- One-click **fist calibration** in Settings.
- System tray, global hotkeys, single-file `.exe` build.
