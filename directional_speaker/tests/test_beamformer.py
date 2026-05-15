"""Unit tests — null-steering beamformer."""
from __future__ import annotations

import json
import math

import numpy as np
import pytest

from directional_speaker import beamformer as bf
from directional_speaker import config as cfg


@pytest.fixture
def mock_lut_path(tmp_path):
    """Create a minimal LUT with a few angle pairs."""
    freqs = [cfg.FC_HZ + i * cfg.FREQ_STEP_HZ
             for i in range(-int(cfg.PASSBAND_BW_HZ / cfg.FREQ_STEP_HZ),
                            int(cfg.PASSBAND_BW_HZ / cfg.FREQ_STEP_HZ) + 1)]
    n_freqs = len(freqs)
    lut = {}
    for target in (-60, -30, 0, 30, 60):
        for null in (-60, -30, 0, 30, 60):
            amp = np.ones((n_freqs, cfg.N_CHANNELS)).tolist()
            phase = np.zeros((n_freqs, cfg.N_CHANNELS)).tolist()
            # Fill theoretical phase for target angle
            for i, f in enumerate(freqs):
                lam = cfg.C_SOUND / f
                for n in range(cfg.N_CHANNELS):
                    phase[i][n] = -2.0 * math.pi * n * cfg.ELEMENT_SPACING_M / lam * math.sin(math.radians(target))
            # Normalise to channel 0
            for i in range(n_freqs):
                base = phase[i][0]
                for n in range(cfg.N_CHANNELS):
                    phase[i][n] -= base
            key = f"{target}_{null}"
            lut[key] = {
                "freqs_hz": freqs,
                "amp": amp,
                "phase": phase,
            }
    p = tmp_path / "mock_lut.json"
    p.write_text(json.dumps(lut))
    return str(p)


def test_quantize():
    assert bf.NullSteeringBeamformer._quantize(0.0) == 0
    assert bf.NullSteeringBeamformer._quantize(1.4) == 0
    assert bf.NullSteeringBeamformer._quantize(1.5) == 3
    assert bf.NullSteeringBeamformer._quantize(-60) == -60
    assert bf.NullSteeringBeamformer._quantize(60) == 60
    assert bf.NullSteeringBeamformer._quantize(100) == 60


def test_lut_load(mock_lut_path):
    b = bf.NullSteeringBeamformer(mock_lut_path)
    assert b.lut_freqs is not None
    assert len(b.lut_freqs) == 81


def test_apply_passband_shape(mock_lut_path):
    b = bf.NullSteeringBeamformer(mock_lut_path)
    T = cfg.WINDOW_SAMPLES
    t = np.arange(T) / cfg.FS_HZ
    carrier = np.cos(2 * np.pi * cfg.FC_HZ * t)
    mod_tone = 0.5 * (1.0 + 0.5 * np.sin(2 * np.pi * 1000 * t)) * carrier
    out = b.apply_passband(mod_tone.astype(np.float32), target_deg=0, null_deg=30)
    assert out.shape == (cfg.N_CHANNELS, T)
    assert out.dtype == np.float32


def test_combine_shape(mock_lut_path):
    b = bf.NullSteeringBeamformer(mock_lut_path)
    T = cfg.WINDOW_SAMPLES
    x = np.sin(2 * np.pi * 500 * np.arange(T) / cfg.FS_HZ).astype(np.float32)
    out = b.combine(0, 30, x, x)
    assert out.shape == (cfg.N_CHANNELS, T)
    assert np.max(np.abs(out)) <= 1.0 + 1e-6


def test_combine_with_different_signals(mock_lut_path):
    b = bf.NullSteeringBeamformer(mock_lut_path)
    T = cfg.WINDOW_SAMPLES
    x1 = np.sin(2 * np.pi * 500 * np.arange(T) / cfg.FS_HZ).astype(np.float32)
    x2 = np.cos(2 * np.pi * 700 * np.arange(T) / cfg.FS_HZ).astype(np.float32)
    out = b.combine(-30, 30, x1, x2)
    assert out.shape == (cfg.N_CHANNELS, T)

