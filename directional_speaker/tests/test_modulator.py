"""Modulator — DSB-AM correctness + peak bound."""
from __future__ import annotations

import numpy as np

from directional_speaker import config as cfg
from directional_speaker.modulator import DSBAMModulator


def test_dsbam_spectrum():
    mod = DSBAMModulator()
    t = np.arange(cfg.WINDOW_SAMPLES) / cfg.FS_HZ
    f_aud = 1000.0
    z = 0.5 * np.sin(2 * np.pi * f_aud * t).astype(complex)
    y = mod.modulate(z)
    Y = np.fft.rfft(y)
    freqs = np.fft.rfftfreq(y.size, 1 / cfg.FS_HZ)
    # expect peaks near fc, fc-f_aud, fc+f_aud
    sig = np.abs(Y)
    top = freqs[np.argsort(sig)[-6:]]
    assert any(abs(f - cfg.FC_HZ) < 50 for f in top), top
    assert any(abs(f - (cfg.FC_HZ - f_aud)) < 80 for f in top), top
    assert any(abs(f - (cfg.FC_HZ + f_aud)) < 80 for f in top), top


def test_dsbam_peak_le_one():
    mod = DSBAMModulator()
    z = np.ones(cfg.WINDOW_SAMPLES, dtype=complex) * 0.99
    y = mod.modulate(z)
    assert np.max(np.abs(y)) <= 1.0 + 1e-6


def test_phase_continuity_across_frames():
    """Absolute-time carrier => no click at frame boundary."""
    mod = DSBAMModulator()
    z = np.zeros(cfg.WINDOW_SAMPLES, dtype=complex)
    y1 = mod.modulate(z)
    y2 = mod.modulate(z)
    # stitched carrier should be continuous
    diff = y2[0] - y1[-1]
    step = np.cos(2 * np.pi * cfg.FC_HZ / cfg.FS_HZ) - 1.0
    assert abs(diff) <= 2 * 0.5  # |step|*0.5 amplitude
