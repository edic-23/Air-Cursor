"""Resolve bundled asset paths, working both from source and a PyInstaller .exe."""

from __future__ import annotations

import os
import sys


def assets_dir() -> str:
    base = getattr(sys, "_MEIPASS", None)
    if base:                                   # frozen (PyInstaller) -> _MEIPASS/assets
        return os.path.join(base, "assets")
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "..", "assets")  # source layout -> repo/assets


def asset(name: str) -> str:
    return os.path.join(assets_dir(), name)
