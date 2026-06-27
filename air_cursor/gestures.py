"""Open-hand vs fist classification from MediaPipe hand landmarks.

We compute a "curl ratio": how curled the four fingers are relative to hand size.
An open palm has extended fingers (low curl); a fist has curled fingers (high curl).
Hysteresis (separate on/off thresholds) plus a frame debounce prevent the click
from flickering at the boundary.

Landmark indices (MediaPipe Hands):
    0 wrist
    finger tips: 8 (index), 12 (middle), 16 (ring), 20 (pinky)
    finger MCP (knuckle): 5, 9, 13, 17
    palm center is approximated as the mean of wrist + MCPs.
"""

from __future__ import annotations

import math

TIP_IDS = (8, 12, 16, 20)
MCP_IDS = (5, 9, 13, 17)
PIP_IDS = (6, 10, 14, 18)          # proximal joints, one per finger
WRIST = 0
THUMB_TIP = 4
INDEX_TIP = 8
PALM_REF_IDS = (0, 5, 9, 13, 17)


def _dist(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def hand_scale(lm) -> float:
    """Roughly constant per-hand size: wrist -> middle-finger MCP."""
    return _dist(lm[WRIST], lm[9]) or 1e-6


def extended_fingers(lm) -> tuple[bool, bool, bool, bool]:
    """Which of (index, middle, ring, pinky) are extended.

    A finger is extended when its tip is farther from the palm than its PIP joint.
    """
    palm = palm_center(lm)
    out = []
    for tip, pip in zip(TIP_IDS, PIP_IDS):
        out.append(_dist(lm[tip], palm) > _dist(lm[pip], palm) * 1.05)
    return tuple(out)  # type: ignore[return-value]


def is_peace(lm) -> bool:
    """Index + middle extended, ring + pinky curled (the ✌ sign)."""
    idx, mid, ring, pinky = extended_fingers(lm)
    return idx and mid and not ring and not pinky


def pinch_distance(lm) -> float:
    """Thumb-tip to index-tip distance, normalized by hand size (0 = touching)."""
    return _dist(lm[THUMB_TIP], lm[INDEX_TIP]) / hand_scale(lm)


def is_lateral_pinch(lm, max_dist: float) -> bool:
    """A *sideways* pinch used for scrolling, designed NOT to trigger on a fist.

    Requirements:
      1. Thumb tip and index tip are close (pinch).            -> max_dist
      2. The pinch points sideways: the thumb->index vector is more horizontal
         than vertical (so it reads as a lateral, rotated pinch).
      3. The hand is NOT a fist: at least one of middle/ring/pinky is still
         extended. A fist curls every finger, so this excludes it cleanly.
    """
    if pinch_distance(lm) > max_dist:
        return False

    # Orientation: thumb tip -> index tip vector, mostly horizontal.
    dx = abs(lm[THUMB_TIP][0] - lm[INDEX_TIP][0])
    dy = abs(lm[THUMB_TIP][1] - lm[INDEX_TIP][1])
    if dx < dy:                       # more vertical than horizontal -> not lateral
        return False

    # Fist guard: a fist has all of middle/ring/pinky curled.
    _idx, mid, ring, pinky = extended_fingers(lm)
    if not (mid or ring or pinky):
        return False

    return True


def palm_center(lm) -> tuple[float, float]:
    xs = sum(lm[i][0] for i in PALM_REF_IDS) / len(PALM_REF_IDS)
    ys = sum(lm[i][1] for i in PALM_REF_IDS) / len(PALM_REF_IDS)
    return xs, ys


def curl_ratio(lm) -> float:
    """0 = fully open, ~1+ = fully curled.

    For each finger, compare tip->palm distance to MCP->palm distance. When a finger
    curls, its tip moves toward the palm, so tip distance shrinks below MCP distance.
    Normalizing by hand scale keeps it distance-invariant.
    """
    palm = palm_center(lm)
    scale = hand_scale(lm)

    curl_sum = 0.0
    for tip, mcp in zip(TIP_IDS, MCP_IDS):
        tip_d = _dist(lm[tip], palm) / scale
        mcp_d = _dist(lm[mcp], palm) / scale
        # When open, tip_d > mcp_d (ratio > 1). When fisted, tip_d < mcp_d.
        # Convert to a curl value in roughly [0, 1+].
        curl = 1.0 - min(1.5, tip_d / (mcp_d + 1e-6))
        curl_sum += max(0.0, curl)
    return curl_sum / len(TIP_IDS)


class FistDetector:
    """Stateful fist detector with hysteresis + debounce."""

    def __init__(self, on_thresh: float, off_thresh: float, debounce: int = 2):
        self.on = on_thresh
        self.off = off_thresh
        self.debounce = debounce
        self._fist = False
        self._streak = 0
        self._pending: bool | None = None

    def update_params(self, on_thresh: float, off_thresh: float, debounce: int) -> None:
        self.on = on_thresh
        self.off = off_thresh
        self.debounce = debounce

    def reset(self) -> None:
        self._fist = False
        self._streak = 0
        self._pending = None

    def update(self, lm) -> bool:
        ratio = curl_ratio(lm)
        # Decide the candidate state using hysteresis.
        if self._fist:
            candidate = ratio > self.off          # stay fisted until it relaxes
        else:
            candidate = ratio > self.on           # need a firm fist to engage

        if candidate == self._fist:
            self._streak = 0
            self._pending = None
            return self._fist

        # State wants to change; require it to persist for `debounce` frames.
        if self._pending == candidate:
            self._streak += 1
        else:
            self._pending = candidate
            self._streak = 1

        if self._streak >= self.debounce:
            self._fist = candidate
            self._streak = 0
            self._pending = None
        return self._fist
