"""Render calibration figures to reports/images/.

  - af_theta0_0.png     : array factor at theta0=0 with key metrics annotated
  - beam_scan.png       : array factor overlay for theta0 in {-60,-30,0,30,60}
  - beta_pareto.png     : already produced by scripts/calibrate_beta.py
  - beta_lut.png        : already produced by scripts/calibrate_beta.py
  - joint_norm_mc.png   : Monte Carlo peak magnitude histogram under joint norm
  - sim_vs_meas_table.csv : placeholder table for §7 validation
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

from directional_speaker import beamformer as bf
from directional_speaker import config as cfg

OUT = ROOT / "reports" / "images"
OUT.mkdir(parents=True, exist_ok=True)


def _af_db(w: np.ndarray, grid: np.ndarray) -> np.ndarray:
    af = bf.array_factor(w, grid)
    mag2 = np.abs(af) ** 2
    mag2 /= mag2.max() + 1e-30
    return 10 * np.log10(mag2 + 1e-12)


def fig_af_theta0_0():
    w = bf.solve_weights(0.0, beta=cfg.BETA_LUT.get(0, cfg.BETA))
    grid = np.arange(-90, 90 + 0.25, 0.25)
    af_db = _af_db(w, grid)
    m = bf.af_metrics(w, 0.0)

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(grid, af_db, color="C0")
    ax.axvspan(-cfg.W_MAIN_DEG / 2, cfg.W_MAIN_DEG / 2, color="C2", alpha=0.15,
               label=rf"$W_{{main}}={cfg.W_MAIN_DEG}^\circ$")
    ax.axhline(m.psll_db, color="red", ls="--", lw=0.8,
               label=f"PSLL = {m.psll_db:.2f} dB")
    ax.axhline(cfg.PSLL_SOFT_DB, color="gray", ls=":", lw=0.6,
               label=f"soft target {cfg.PSLL_SOFT_DB} dB")
    ax.set_ylim(-40, 2)
    ax.set_xlim(-90, 90)
    ax.set_xlabel(r"$\theta$ (deg)")
    ax.set_ylabel("normalized AF (dB)")
    ax.set_title(
        rf"AF @ $\theta_0=0^\circ$, $\beta={cfg.BETA_LUT.get(0, cfg.BETA):.3f}$, "
        rf"-3 dB BW={m.bw_m3db_deg:.2f}$^\circ$, MLER={m.mler:.3f}"
    )
    ax.grid(True, alpha=0.4)
    ax.legend(loc="lower right", fontsize=8)
    plt.tight_layout()
    plt.savefig(OUT / "af_theta0_0.png", dpi=140)
    plt.close(fig)


def fig_beam_scan():
    thetas = [-60, -30, 0, 30, 60]
    grid = np.arange(-90, 90 + 0.25, 0.25)
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    for t0 in thetas:
        beta = cfg.BETA_LUT.get(t0, cfg.BETA)
        w = bf.solve_weights(t0, beta=beta)
        af_db = _af_db(w, grid)
        m = bf.af_metrics(w, float(t0))
        ax.plot(grid, af_db, lw=1.2,
                label=rf"$\theta_0={t0:+d}^\circ$, PSLL={m.psll_db:.1f} dB, BW={m.bw_m3db_deg:.1f}$^\circ$")
        ax.axvline(t0, color="gray", ls=":", lw=0.4)
    ax.set_ylim(-35, 2)
    ax.set_xlim(-90, 90)
    ax.set_xlabel(r"$\theta$ (deg)")
    ax.set_ylabel("normalized AF (dB)")
    ax.set_title("Beam scan across target directions (8ch ULA, eigenfilter)")
    ax.grid(True, alpha=0.4)
    ax.legend(loc="lower center", fontsize=7.5, ncol=2)
    plt.tight_layout()
    plt.savefig(OUT / "beam_scan.png", dpi=140)
    plt.close(fig)


def fig_joint_norm_mc(trials: int = 2000):
    """Verify |x[k,t]| <= 1 post-modulation across random (theta_L, theta_R) and audio."""
    from directional_speaker.modulator import DSBAMModulator

    rng = np.random.default_rng(0)
    beamformer = bf.Beamformer()
    beamformer.prewarm()
    peaks = []
    fs = cfg.FS_HZ
    t = np.arange(int(0.01 * fs)) / fs  # 10 ms
    for _ in range(trials):
        t_L = rng.integers(-60, 61)
        t_R = rng.integers(-60, 61)
        f1 = rng.uniform(200, 4000)
        f2 = rng.uniform(200, 4000)
        # baseband audio with |s|<=1
        s_L = np.clip(0.99 * np.sin(2 * np.pi * f1 * t), -1, 1)
        s_R = np.clip(0.99 * np.sin(2 * np.pi * f2 * t + rng.uniform(0, np.pi)), -1, 1)
        Z = beamformer.combine_baseband(float(t_L), float(t_R), s_L, s_R)
        mod = DSBAMModulator()
        X = mod.modulate(Z)
        peaks.append(float(np.max(np.abs(X))))

    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.hist(peaks, bins=60, color="C0", alpha=0.85)
    ax.axvline(1.0, color="red", ls="--", label="|x|=1")
    ax.set_xlabel("max |x[k,t]|")
    ax.set_ylabel("count")
    ax.set_title(f"Joint-normalization peak magnitudes ({trials} trials)")
    ax.legend()
    ax.grid(True, alpha=0.4)
    plt.tight_layout()
    plt.savefig(OUT / "joint_norm_mc.png", dpi=140)
    plt.close(fig)
    return max(peaks)


def main():
    fig_af_theta0_0()
    fig_beam_scan()
    max_peak = fig_joint_norm_mc()
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
