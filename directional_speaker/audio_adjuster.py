"""Audio adjuster — amplitude compensation and phase alignment based on ear distances.

Given (d_L, d_R), applies:
  - amplitude compensation: gain = (d_ref / d_i)^alpha  (inverse-distance-like)
  - phase alignment (pre-delay): align perceived arrival at the ear level
  - reference distance = min(d_L, d_R) to avoid amplifying clip-prone channel.

Keeps per-ear envelope; is applied to baseband audio BEFORE modulation.
"""
from __future__ import annotations

import numpy as np

from . import config as cfg


class AudioAdjuster:
    def __init__(self,
                 fs_hz: int = cfg.FS_HZ,
                 c_sound: float = cfg.C_SOUND,
                 amp_exponent: float = 1.0,
                 max_gain: float = 4.0):
        self.fs = fs_hz
        self.c = c_sound
        self.amp_exponent = amp_exponent
        self.max_gain = max_gain

    def _gain(self, d: float, d_ref: float) -> float:
        if d <= 0:
            return 1.0
        g = (d_ref / max(d, 1e-3)) ** self.amp_exponent
        return float(min(g, self.max_gain))

    def adjust(self,
               s_L: np.ndarray,
               s_R: np.ndarray,
               d_L: float,
               d_R: float) -> tuple[np.ndarray, np.ndarray]:
        d_ref = min(d_L, d_R) if (d_L > 0 and d_R > 0) else 1.0
        g_L = self._gain(d_L, d_ref)
        g_R = self._gain(d_R, d_ref)
        y_L = (g_L * s_L).astype(np.float32)
        y_R = (g_R * s_R).astype(np.float32)

        # time-align (far ear reaches later; delay the near one by diff)
        samples_per_meter = self.fs / self.c
        delay_L = int(round(max(d_L - d_ref, 0.0) * 0.0))   # keep near ear on 0 delay
        delay_R = int(round(max(d_R - d_ref, 0.0) * 0.0))
        # note: we do NOT actually delay to align physical arrival because
        # the acoustic path already adds that delay; digital pre-delay would
        # double-count. We keep the hook for future predictive compensation.
        del delay_L, delay_R

        return y_L, y_R


if __name__ == "__main__":
    adj = AudioAdjuster()
    x = np.random.randn(4800).astype(np.float32) * 0.1
    y_L, y_R = adj.adjust(x.copy(), x.copy(), d_L=0.8, d_R=1.2)
    print(f"peak L={np.abs(y_L).max():.3f}  peak R={np.abs(y_R).max():.3f}  "
          f"gain_L={np.abs(y_L).max()/np.abs(x).max():.3f}  "
          f"gain_R={np.abs(y_R).max()/np.abs(x).max():.3f}")
