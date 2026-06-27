# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Air Cursor -> a single windowed AirCursor.exe.

Bundles the MediaPipe runtime data (models, .tflite graphs, binaries) and the
app's own assets (hand SVGs + the hand_landmarker.task model). Build with:

    .venv\\Scripts\\pyinstaller AirCursor.spec
"""

from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = []
binaries = []
hiddenimports = []

# MediaPipe ships model graphs / .tflite / native libs as package data.
for pkg in ("mediapipe",):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# cv2 + PyQt6 occasionally need their submodules pulled in explicitly.
hiddenimports += collect_submodules("cv2")
hiddenimports += ["PyQt6.QtSvg"]

# Our own assets (hand model + cursor art).
datas += [("assets", "assets")]


a = Analysis(
    ["air_cursor\\__main__.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="AirCursor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # windowed app, no console window
    disable_windowed_traceback=False,
    icon="assets\\app_icon.ico" if __import__("os").path.exists("assets\\app_icon.ico") else None,
)
