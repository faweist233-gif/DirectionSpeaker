"""HRTF convolution — CIPIC subject_003 loader and stereo renderer.

CIPIC HRTF dataset (UC Davis): per-subject hrir_final.mat containing:
  hrir_l, hrir_r: shape (25, 50, 200) — [azimuth, elevation, tap]
  azimuth  grid: [-80, -65, -55, -45:5:45, 55, 65, 80]  (25 pts)
  elevation grid: -45 + 5.625*k deg, k=0..49           (50 pts)
  fs = 44100 Hz.

Download instructions (MANUAL.md §3.5):
  1. Register at https://interface.cipic.ucdavis.edu/
  2. Download CIPIC HRTF Database v1.2, extract to data/hrtf/.
  3. Rename `subject_003/hrir_final.mat` -> `data/hrtf/subject_003.mat`.

If the file is absent, `HRTFRenderer.load()` raises FileNotFoundError with
a pointer to the download instructions.
"""
from __future__ import annotations

import pathlib

import numpy as np
from scipy.signal import fftconvolve, resample_poly

from . import config as cfg


# CIPIC azimuth grid (degrees). Reference: CIPIC v1.2 README.
CIPIC_AZIMUTH_DEG = np.array(
    [-80, -65, -55, -45, -40, -35, -30, -25, -20, -15, -10, -5,
     0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 55, 65, 80], dtype=float
)
CIPIC_ELEVATION_DEG = -45.0 + 5.625 * np.arange(50)
CIPIC_ELEV_0_IDX = int(np.argmin(np.abs(CIPIC_ELEVATION_DEG)))


class HRTFRenderer:
    def __init__(self, mat_path: str | pathlib.Path = cfg.HRTF_MAT_PATH,
                 orig_fs: int = cfg.HRTF_ORIG_FS_HZ,
                 target_fs: int = cfg.FS_HZ):
        self.mat_path = pathlib.Path(mat_path)
        self.orig_fs = orig_fs
        self.target_fs = target_fs
        self._hrir_l = None
        self._hrir_r = None

    def load(self) -> None:
        if not self.mat_path.is_file():
            raise FileNotFoundError(
                f"CIPIC HRTF file not found: {self.mat_path}\n"
                f"Register at https://interface.cipic.ucdavis.edu/ and place "
                f"subject_003/hrir_final.mat at this path. See MANUAL.md §3.5."
            )
        from scipy.io import loadmat
        mat = loadmat(str(self.mat_path))
        hrir_l = mat["hrir_l"]  # (25, 50, 200)
        hrir_r = mat["hrir_r"]
        if self.orig_fs != self.target_fs:
            from math import gcd
            g = gcd(self.target_fs, self.orig_fs)
            up, down = self.target_fs // g, self.orig_fs // g
            # resample along last axis
            hrir_l = resample_poly(hrir_l, up, down, axis=-1)
            hrir_r = resample_poly(hrir_r, up, down, axis=-1)
        self._hrir_l = hrir_l.astype(np.float32)
        self._hrir_r = hrir_r.astype(np.float32)

    def _nearest_az_idx(self, az_deg: float) -> int:
        return int(np.argmin(np.abs(CIPIC_AZIMUTH_DEG - az_deg)))

    def hrir_pair(self, az_deg: float, el_deg: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
        if self._hrir_l is None:
            self.load()
        az_i = self._nearest_az_idx(az_deg)
        el_i = int(np.argmin(np.abs(CIPIC_ELEVATION_DEG - el_deg)))
        return self._hrir_l[az_i, el_i], self._hrir_r[az_i, el_i]

    def render_stereo(self,
                      mono: np.ndarray,
                      az_left_deg: float,
                      az_right_deg: float,
                      el_deg: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
        """Return (s_L, s_R): mono convolved with HRIR at the two target azimuths.

        s_L is what the left ear should receive (= mono * hrir_l[az_L]);
        s_R is what the right ear should receive (= mono * hrir_r[az_R]).
        Output length matches input (valid-mode center crop).
        """
        if self._hrir_l is None:
            self.load()
        hl, _ = self.hrir_pair(az_left_deg, el_deg)
        _, hr = self.hrir_pair(az_right_deg, el_deg)
        s_L = _same_conv(mono, hl)
        s_R = _same_conv(mono, hr)
        return s_L.astype(np.float32), s_R.astype(np.float32)


def _same_conv(x: np.ndarray, h: np.ndarray) -> np.ndarray:
    y = fftconvolve(x, h, mode="full")
    # align to 'same' with causal start
    start = 0
    return y[start:start + x.size]


def synthetic_hrir_pair(az_deg: float,
                        fs: int = cfg.FS_HZ,
                        taps: int = 128) -> tuple[np.ndarray, np.ndarray]:
    """Fallback HRIR pair (ITD-only, no HRTF magnitude shaping).

    Use when CIPIC is unavailable — keeps pipeline runnable. Degrades
    spatial fidelity. Not for production.
    """
    c = cfg.C_SOUND
    head_r = cfg.INTERAURAL_M / 2.0
    # Woodworth ITD formula
    az = np.deg2rad(az_deg)
    itd_L = (head_r / c) * (az + np.sin(az))    # left-ear delay (positive = later for az>0)
    itd_R = (head_r / c) * (-az + np.sin(-az))
    h_L = np.zeros(taps, dtype=np.float32)
    h_R = np.zeros(taps, dtype=np.float32)
    def _put(h, delay_s):
        d = max(int(round(delay_s * fs)), 0)
        if d < taps:
            h[d] = 1.0
    _put(h_L, itd_L)
    _put(h_R, itd_R)
    return h_L, h_R


if __name__ == "__main__":
    r = HRTFRenderer()
    try:
        r.load()
        print(f"CIPIC loaded: hrir_l={r._hrir_l.shape}  target_fs={r.target_fs}")
    except FileNotFoundError as e:
        print(f"{e}\nfalling back to synthetic ITD HRIR")
        hl, hr = synthetic_hrir_pair(30.0)
        print(f"synthetic HRIR pair taps={hl.size}, delays: L=peak@{np.argmax(np.abs(hl))}, R=peak@{np.argmax(np.abs(hr))}")
