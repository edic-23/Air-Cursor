"""Map a point in the camera's active zone to the full virtual desktop.

MediaPipe gives landmark coords normalized to [0, 1] within the camera frame.
We treat a smaller rectangle (the "active zone") as the usable region so small,
comfortable hand movements span the entire screen. X is mirrored so the cursor
moves the same direction as the hand (selfie view).
"""

from __future__ import annotations


def map_to_screen(
    nx: float,
    ny: float,
    zone_x: float,
    zone_y: float,
    zone_w: float,
    zone_h: float,
    screen_left: int,
    screen_top: int,
    screen_w: int,
    screen_h: int,
    mirror_x: bool = True,
    mirror_y: bool = False,
) -> tuple[int, int]:
    # Mirror axes as needed (depends on how the camera is mounted/flipped).
    if mirror_x:
        nx = 1.0 - nx
    if mirror_y:
        ny = 1.0 - ny

    # Normalize within the active zone, clamped to [0, 1].
    zx = (nx - zone_x) / zone_w if zone_w else 0.0
    zy = (ny - zone_y) / zone_h if zone_h else 0.0
    zx = min(1.0, max(0.0, zx))
    zy = min(1.0, max(0.0, zy))

    px = screen_left + zx * screen_w
    py = screen_top + zy * screen_h
    return int(round(px)), int(round(py))
