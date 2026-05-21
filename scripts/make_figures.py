"""Render null-steering calibration figures to reports/images/.

Figures (regenerated from data/beam_weights/nullsteering_lut.json):
  - af_target_0_null_40.png : array factor at carrier for (target=0, null=40)
  - beam_scan.png           : AF overlay for several (target, null) pairs
  - joint_norm_mc.png       : Monte Carlo |x[k,t]| histogram from beamformer.combine()
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from directional_speaker import config as cfg
from directional_speaker.beamformer import NullSteeringBeamformer
from directional_speaker.modulator import DSBAMModulator

OUT = ROOT / "reports" / "images"
OUT.mkdir(parents=True, exist_ok=True)


def _lut_array_factor(amp_row: np.ndarray, phase_row: np.ndarray,
                      freq_hz: float, grid_deg: np.ndarray) -> np.ndarray:
    """Per-frequency array factor for a single passband bin.

    AF(θ) = (1/N) Σ_n  amp[n] * exp(j*(phase[n] + 2π·n·d/λ·sinθ))
    Returns magnitude in dB normalised to its peak.
    """
    N = amp_row.shape[0]
    lam = cfg.C_SOUND / freq_hz
    n_idx = np.arange(N)[None, :]                     # (1, N)
    sin_az = np.sin(np.deg2rad(grid_deg))[:, None]    # (G, 1)
    geom = 2.0 * np.pi * cfg.ELEMENT_SPACING_M * n_idx / lam * sin_az  # (G, N)
    total = geom + phase_row[None, :]
    af = np.sum(amp_row[None, :] * np.exp(1j * total), axis=1) / N
    mag2 = np.abs(af) ** 2
    mag2 /= mag2.max() + 1e-30
    return 10 * np.log10(mag2 + 1e-12)


def _carrier_row(entry: dict) -> tuple[np.ndarray, np.ndarray, float]:
    """Pick the amplitude/phase row closest to the carrier frequency."""
    freqs = np.asarray(entry["freqs_hz"], dtype=float)
    j = int(np.argmin(np.abs(freqs - cfg.FC_HZ)))
    amp = np.asarray(entry["amp"], dtype=float)[j]
    phase = np.asarray(entry["phase"], dtype=float)[j]
    return amp, phase, float(freqs[j])


def fig_single(lut: dict, target: int, null: int) -> None:
    key = f"{target}_{null}"
    if key not in lut:
        print(f"[skip] LUT missing {key}")
        return
    amp, phase, fc = _carrier_row(lut[key])
    grid = np.arange(-90, 90 + 0.25, 0.25)
    af_db = _lut_array_factor(amp, phase, fc, grid)

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(grid, af_db, color="C0")
    ax.axvline(target, color="C2", ls="--", lw=0.8, label=f"target {target}°")
    ax.axvline(null, color="red", ls="--", lw=0.8, label=f"null {null}°")
    ax.set_ylim(-50, 2)
    ax.set_xlim(-90, 90)
    ax.set_xlabel(r"$\theta$ (deg)")
    ax.set_ylabel("normalised AF (dB)")
    ax.set_title(f"Null-steering AF @ {fc/1000:.1f} kHz  (target={target}°, null={null}°)")
    ax.grid(True, alpha=0.4)
    ax.legend(loc="lower right", fontsize=9)
    plt.tight_layout()
    plt.savefig(OUT / f"af_target_{target}_null_{null}.png", dpi=140)
    plt.close(fig)


def fig_beam_scan(lut: dict) -> None:
    pairs = [(-60, 0), (-30, 30), (0, 39), (30, -30), (60, 0)]
    grid = np.arange(-90, 90 + 0.25, 0.25)
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    for tgt, nul in pairs:
        key = f"{tgt}_{nul}"
        entry = lut.get(key)
        if entry is None:
            continue
        amp, phase, fc = _carrier_row(entry)
        af_db = _lut_array_factor(amp, phase, fc, grid)
        ax.plot(grid, af_db, lw=1.2, label=f"target={tgt:+d}°, null={nul:+d}°")
    ax.set_ylim(-50, 2)
    ax.set_xlim(-90, 90)
    ax.set_xlabel(r"$\theta$ (deg)")
    ax.set_ylabel("normalised AF (dB)")
    ax.set_title("Beam scan across (target, null) pairs (8-ch ULA, null-steering LUT)")
    ax.grid(True, alpha=0.4)
    ax.legend(loc="lower center", fontsize=8, ncol=2)
    plt.tight_layout()
    plt.savefig(OUT / "beam_scan.png", dpi=140)
    plt.close(fig)


def fig_joint_norm_mc(bf: NullSteeringBeamformer, trials: int = 200) -> float:
    """Verify |x[k,t]| ≤ 1 across random (theta_L, theta_R) and random audio."""
    rng = np.random.default_rng(0)
    mod = DSBAMModulator()
    fs = cfg.FS_HZ
    t = np.arange(int(0.01 * fs)) / fs  # 10 ms

    # Use only quantised LUT angles to guarantee LUT hits
    angles = np.arange(-60, 61, int(cfg.THETA_STEP_DEG))
    peaks = []
    for _ in range(trials):
        t_L = int(rng.choice(angles))
        t_R = int(rng.choice(angles))
        f1 = rng.uniform(200, 4000)
        f2 = rng.uniform(200, 4000)
        s_L = np.clip(0.99 * np.sin(2 * np.pi * f1 * t), -1, 1).astype(np.float32)
        s_R = np.clip(0.99 * np.sin(2 * np.pi * f2 * t + rng.uniform(0, np.pi)),
                      -1, 1).astype(np.float32)
        mod_L, mod_R = mod.modulate_multi(s_L, s_R)
        out = bf.combine(float(t_L), float(t_R), mod_L, mod_R)
        peaks.append(float(np.max(np.abs(out))))

    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.hist(peaks, bins=40, color="C0", alpha=0.85)
    ax.axvline(1.0, color="red", ls="--", label="|x|=1")
    ax.set_xlabel("max |x[k,t]|")
    ax.set_ylabel("count")
    ax.set_title(f"Joint-normalisation peak magnitudes ({trials} trials)")
    ax.legend()
    ax.grid(True, alpha=0.4)
    plt.tight_layout()
    plt.savefig(OUT / "joint_norm_mc.png", dpi=140)
    plt.close(fig)
    return max(peaks) if peaks else float("nan")


def main() -> None:
    lut_path = ROOT / cfg.BEAM_LUT_PATH
    if not lut_path.is_file():
        print(f"LUT not found: {lut_path}\nRun scripts/calibrate_nullsteering.py first.")
        sys.exit(1)

    with open(lut_path, "r", encoding="utf-8") as f:
        lut = json.load(f)

    fig_single(lut, target=0, null=39)
    fig_beam_scan(lut)

    bf = NullSteeringBeamformer(lut_path)
    max_peak = fig_joint_norm_mc(bf)

    summary = {
        "files": sorted(p.name for p in OUT.iterdir()),
        "joint_norm_max_peak": max_peak,
    }
    (ROOT / "reports" / "figure_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
