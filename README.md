<div align="center">

# 🖐 Air Cursor

### Control your Windows PC with your bare hand — like the Xbox Kinect, but for your desktop.

Wave your hand in front of any webcam and a cursor follows it across your **real** screen.
Make a **fist** to click and drag, a **peace sign** to right-click, **pinch** to scroll,
**flick** to switch windows. No mouse, no touchscreen, no extra hardware — just your hand
in the air. Everything runs **locally** on your machine.

![Platform](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-0078D6?logo=windows)
![Python](https://img.shields.io/badge/python-3.11–3.13-3776AB?logo=python&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green)
![Privacy](https://img.shields.io/badge/privacy-100%25%20on--device-success)

<!-- TODO: drop a demo.gif here once recorded, then uncomment: -->
<!-- ![Air Cursor demo](docs/demo.gif) -->

*(demo GIF coming soon)*

</div>

---

## What it does

| Gesture | Action |
|--------|--------|
| ✋ Move your open hand | Move the cursor |
| ✊ Make a fist | Press & hold the left mouse button (click + **drag**) |
| ✌️ Peace sign | **Right-click** |
| 🤏 Pinch & move up/down | **Scroll** the page |
| 👉 Flick sideways (fast) | Switch windows — **Alt + Tab** |
| ⬆️ Sweep from very bottom to very top | Open Task View — **Win + Tab** |
| 🕐 Hover & hold (optional) | Click without a fist — for accessibility |

Plus:
- **Glowing edge "mist"** so you always know it's active — pick any color
- **Cartoon hand cursor** that squashes & pops when you click (bring your own SVG/PNG)
- **Smart smoothing** (One Euro Filter) — precise when slow, snappy when fast
- **Click-anywhere** — works over *any* app, because it drives the real OS mouse
- **Everything is tunable** in Settings, including one-click **fist calibration**
- **System tray** + global hotkeys, lives quietly in the background

---

## Get it

### Option A — Just run it (no coding) *(recommended)*
1. Go to the [**Releases**](../../releases) page.
2. Download **`AirCursor.exe`**.
3. Double-click it. That's it — no Python, no install.

> First launch opens **Settings**. Pick your camera, hit start, and hold your hand up.

### Option B — Run from source (developers)
```bash
git clone https://github.com/edic-23/Air-Cursor.git
cd Air-Cursor
py -3.13 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m air_cursor.main
```

---

## Controls

| Hotkey | Does |
|--------|------|
| `Ctrl + Shift + H` | Turn tracking on / off |
| `Ctrl + M` | Open Settings |
| Tray icon | Start / Stop / Settings / Quit |

---

## First-time tips

- **Point the camera at your hand**, well-lit, about 40–60 cm away. (A phone-as-webcam app like GlideX/DroidCam works great.)
- Click **Settings → Calibrate fist** and open/close your hand a few times — it auto-tunes detection to *your* hand.
- Cursor jittery? Lower **Responsiveness** or raise **Smoothness**.
- Laggy? Lower the **FPS cap** or switch the model to **Lite**.
- Can't reach screen corners? Shrink the **Active zone**.
- Left/right reversed? Toggle **Flip left/right** (common with phone cameras).

---

## Accessibility

Air Cursor can be used **without making a fist**. Turn on **Hover to click** in Settings:
hold the cursor still over a target and it clicks automatically (a ring shows the
countdown). Useful for anyone who can't reliably grip or curl their hand.

---

## Custom cursor art

The cursor is drawn from code by default, but you can drop in your own:
- `assets/hand_open.svg` (or `.png`) — resting / open hand
- `assets/hand_fist.svg` (or `.png`) — shown while clicking

SVG is preferred (stays crisp at any size). Transparent background, roughly square.
The glow, wiggle and click-pop are applied automatically. CC0 art sources:
[SVG Repo](https://www.svgrepo.com), [openclipart.org](https://openclipart.org).

---

## How it works

- **Hand tracking:** [MediaPipe Hand Landmarker](https://ai.google.dev/edge/mediapipe) (runs locally, on CPU)
- **UI / overlay:** PyQt6 — a transparent, click-through, always-on-top window that only paints
- **Mouse control:** Win32 API (`SetCursorPos` / `mouse_event`) for low-latency real clicks
- **Smoothing:** a built-in [One Euro Filter](https://gery.casiez.net/1euro/)

The camera + AI run on a background thread and talk to the UI via Qt signals, so the
cursor stays smooth and never blocks the interface.

> **Privacy:** all processing is on your machine. No video ever leaves your computer.

---

## Requirements

- Windows 10 / 11
- Any webcam (built-in, USB, or a phone-as-webcam app)
- (Source install only) Python 3.11–3.13

---

## Contributing

Issues and PRs welcome — gesture ideas, cursor art, and platform ports especially.

## License

MIT — see [LICENSE](LICENSE). Bundled hand model is from Google MediaPipe (Apache-2.0).
