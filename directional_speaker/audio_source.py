"""Audio source — mono wav loader with FS resample and sliding-window iterator.

Input: wav path. Output: 50-ms numpy float32 frames at FS_HZ.
"""
from __future__ import annotations

import pathlib
from typing import Iterator

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from . import config as cfg


class AudioSource:
    def __init__(self, path: str | pathlib.Path = cfg.AUDIO_WAV_DEFAULT,
                 window_samples: int = cfg.WINDOW_SAMPLES,
                 hop_samples: int = cfg.HOP_SAMPLES,
                 loop: bool = True):
        self.path = pathlib.Path(path)
        if not self.path.is_file():
            raise FileNotFoundError(f"audio file not found: {self.path}")
        data, fs = sf.read(str(self.path), always_2d=False)
        if data.ndim == 2:
            data = data.mean(axis=1)
        data = data.astype(np.float32)
        if fs != cfg.FS_HZ:
            # use polyphase resampling
            from math import gcd
            g = gcd(cfg.FS_HZ, fs)
            up, down = cfg.FS_HZ // g, fs // g
            data = resample_poly(data, up, down).astype(np.float32)
        self._data = data
        self._window = window_samples
        self._hop = hop_samples
        self._loop = loop

    def __len__(self) -> int:
        return (self._data.size - self._window) // self._hop + 1

    def frames(self) -> Iterator[np.ndarray]:
        """Yield overlapping frames of length `window_samples`."""
        n = self._data.size
        i = 0
        while True:
            end = i + self._window
            if end > n:
                if not self._loop:
                    return
                i = 0
                end = self._window
                if end > n:
                    raise RuntimeError("audio shorter than window")
            yield self._data[i:end].copy()
            i += self._hop


def synthetic_speech_like(duration_s: float = 3.0,
                          fs: int = cfg.FS_HZ) -> np.ndarray:
    """Fallback source: formant-like synthetic speech for smoke tests."""
    t = np.arange(int(fs * duration_s)) / fs
    f0 = 140.0 * (1 + 0.05 * np.sin(2 * np.pi * 2.0 * t))
    pulse = 0.5 * (np.sign(np.sin(2 * np.pi * f0 * t)) + 1)
    # 3 formants
    def _formant(center, bw, amp):
        from scipy.signal import lfilter, iirpeak
        b, a = iirpeak(center / (fs / 2), center / bw)
        return amp * lfilter(b, a, pulse)
    y = _formant(700, 60, 1.0) + _formant(1220, 80, 0.6) + _formant(2600, 150, 0.3)
    y = y / (np.max(np.abs(y)) + 1e-9) * 0.8
    return y.astype(np.float32)


def write_synthetic_speech(path: str | pathlib.Path = cfg.AUDIO_WAV_DEFAULT) -> pathlib.Path:
    """Emit a short synthetic speech wav to `path` at FS_HZ."""
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    y = synthetic_speech_like()
    sf.write(str(p), y, cfg.FS_HZ, subtype="PCM_16")
    return p


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--make-synthetic", action="store_true")
    args = ap.parse_args()
    if args.make_synthetic:
        p = write_synthetic_speech()
        print(f"wrote {p}")
    src = AudioSource(cfg.AUDIO_WAV_DEFAULT, loop=False)
    frames = list(src.frames())
    print(f"{len(frames)} frames of shape {frames[0].shape} at fs={cfg.FS_HZ}")
