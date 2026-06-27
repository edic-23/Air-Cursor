"""One Euro Filter — adaptive low-pass smoothing.

Smooths jitter when the hand is still (low speed -> low cutoff -> heavy smoothing)
while staying responsive on fast moves (high speed -> high cutoff -> light smoothing).
This is what makes the cursor feel "smooth AND snappy."

Reference: Casiez, Roussel, Vogel — "1€ Filter" (CHI 2012).
"""

from __future__ import annotations

import math


class _Scalar:
    def __init__(self, min_cutoff: float, beta: float, d_cutoff: float = 1.0):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self._x_prev: float | None = None
        self._dx_prev: float = 0.0
        self._t_prev: float | None = None

    @staticmethod
    def _alpha(cutoff: float, dt: float) -> float:
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def __call__(self, x: float, t: float) -> float:
        if self._t_prev is None or self._x_prev is None:
            self._t_prev = t
            self._x_prev = x
            self._dx_prev = 0.0
            return x

        dt = t - self._t_prev
        if dt <= 0:
            dt = 1e-3

        dx = (x - self._x_prev) / dt
        a_d = self._alpha(self.d_cutoff, dt)
        dx_hat = a_d * dx + (1 - a_d) * self._dx_prev

        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = self._alpha(cutoff, dt)
        x_hat = a * x + (1 - a) * self._x_prev

        self._x_prev = x_hat
        self._dx_prev = dx_hat
        self._t_prev = t
        return x_hat


class OneEuroFilter2D:
    """Independent One Euro filters for x and y."""

    def __init__(self, min_cutoff: float, beta: float, d_cutoff: float = 1.0):
        self._fx = _Scalar(min_cutoff, beta, d_cutoff)
        self._fy = _Scalar(min_cutoff, beta, d_cutoff)

    def update_params(self, min_cutoff: float, beta: float) -> None:
        for f in (self._fx, self._fy):
            f.min_cutoff = min_cutoff
            f.beta = beta

    def reset(self) -> None:
        for f in (self._fx, self._fy):
            f._x_prev = None
            f._t_prev = None
            f._dx_prev = 0.0

    def __call__(self, x: float, y: float, t: float) -> tuple[float, float]:
        return self._fx(x, t), self._fy(y, t)
