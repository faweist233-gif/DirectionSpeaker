"""DSB-AM modulator — per-channel 40 kHz upconversion of complex baseband.

Input: complex baseband z[k,t], shape (N, T), |z|<=1 (from beamformer).
Output: real passband x[k,t], shape (N, T), |x|<=1 (DAC-safe).

Mapping (parametric array standard, modulation index m=1):
  x[k,t] = 0.5 * Re{ (1 + z[k,t]) * exp(j*2*pi*fc*t_abs) }

With |z|<=1, (1 + z) has magnitude <= 2, and the 0.5 factor caps |x|<=1.

The modulator keeps absolute sample-time (phase continuity across frames) so
all channels share a common carrier.
"""
from __future__ import annotations

import numpy as np

from . import config as cfg


class DSBAMModulator:
    def __init__(self,
                 fc_hz: float = cfg.FC_HZ,
                 fs_hz: int = cfg.FS_HZ,
                 modulation_index: float = 1.0):
        self.fc = fc_hz
        self.fs = fs_hz
        self.m = modulation_index
        self._n_emitted = 0

    def reset(self) -> None:
        self._n_emitted = 0

    def modulate(self, z: np.ndarray) -> np.ndarray:
        """Upconvert.

        z shape (T,) or (N, T). Returns real ndarray with same shape.
        """
        if z.ndim == 1:
            T = z.shape[0]
            t_idx = np.arange(self._n_emitted, self._n_emitted + T)
            phase = 2 * np.pi * self.fc * t_idx / self.fs
            carrier = np.exp(1j * phase)
            out = 0.5 * np.real((1.0 + self.m * z) * carrier)
            self._n_emitted += T
            return out.astype(np.float32)
        elif z.ndim == 2:
            N, T = z.shape
            t_idx = np.arange(self._n_emitted, self._n_emitted + T)
            phase = 2 * np.pi * self.fc * t_idx / self.fs
            carrier = np.exp(1j * phase)   # shape (T,)
            out = 0.5 * np.real((1.0 + self.m * z) * carrier[None, :])
            self._n_emitted += T
            return out.astype(np.float32)
        else:
            raise ValueError(f"z must be 1- or 2-D, got {z.shape}")

    def modulate_multi(self, *signals: np.ndarray) -> list[np.ndarray]:
        """Upconvert several 1-D signals sharing the same carrier phase.

        Useful when left/right passband signals must be perfectly phase-locked.
        Returns a list of real arrays, one per input signal.
        """
        if not signals:
            return []
        T = signals[0].shape[0]
        t_idx = np.arange(self._n_emitted, self._n_emitted + T)
        phase = 2 * np.pi * self.fc * t_idx / self.fs
        carrier = np.exp(1j * phase)
        outs = []
        for z in signals:
            if z.ndim != 1:
                raise ValueError(f"modulate_multi expects 1-D inputs, got {z.shape}")
            out = 0.5 * np.real((1.0 + self.m * z.astype(complex)) * carrier)
            outs.append(out.astype(np.float32))
        self._n_emitted += T
        return outs


if __name__ == "__main__":
    # Sanity: 1 kHz tone -> should see energy at 40k +/- 1 kHz after DSB-AM.
    mod = DSBAMModulator()
    t = np.arange(cfg.WINDOW_SAMPLES) / cfg.FS_HZ
    x = 0.5 * np.sin(2 * np.pi * 1000 * t).astype(complex)   # baseband tone
    y = mod.modulate(x)
    print(f"|y|_max = {np.max(np.abs(y)):.3f}  (should be <=1)")
    Y = np.fft.rfft(y)
    freqs = np.fft.rfftfreq(y.size, 1 / cfg.FS_HZ)
    peaks = freqs[np.argsort(np.abs(Y))[-4:][::-1]]
    print(f"top freqs: {np.round(peaks, 1)}")
