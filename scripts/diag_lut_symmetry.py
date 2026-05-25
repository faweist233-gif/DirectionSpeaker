"""Diagnostic: compare mirror-pair LUT entries (e.g. -6,+6 vs +6,-6).

For a true L/R symmetric beam at head-angle=0, the two LUT entries must
satisfy the ULA mirror relation:

    a_new[n]   == a_old[N-1-n]
    psi_new[n] == -psi_old[N-1-n]   (mod 2 pi)

If they don't, the L-BFGS-B converged to inconsistent local minima — that
is the prime suspect for the L/R intensity asymmetry shown in
data/image/myplot.png.

Also computes |AF(theta, fc)| for both keys and reports peak and null depths.
"""
from __future__ import annotations

import json
import sys
import pathlib

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from directional_speaker import config as cfg  # noqa: E402

LUT_PATH = ROOT / "data" / "beam_weights" / "nullsteering_lut.json"
N = cfg.N_CHANNELS
D = cfg.ELEMENT_SPACING_M
C = cfg.C_SOUND
FC = cfg.FC_HZ


def load_entry(lut: dict, tgt: int, null: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    key = f"{tgt}_{null}"
    e = lut[key]
    return (
        np.array(e["freqs_hz"]),
        np.array(e["amp"]),    # (n_f, N)
        np.array(e["phase"]),  # (n_f, N)
    )


def array_factor(amp: np.ndarray, phase: np.ndarray, f: float, theta_deg_grid: np.ndarray) -> np.ndarray:
    """|AF(theta)| at a single frequency.

    amp, phase shape (N,). Returns array of |AF| over theta_deg_grid.
    """
    n_idx = np.arange(N)
    sin_t = np.sin(np.deg2rad(theta_deg_grid))             # (M,)
    geom = (2 * np.pi * f / C) * D * np.outer(sin_t, n_idx)  # (M, N)
    total_phase = phase[None, :] + geom                    # (M, N)
    z = amp[None, :] * np.exp(1j * total_phase)            # (M, N)
    return np.abs(z.sum(axis=1)) / N


def mirror_test(amp_a: np.ndarray, phase_a: np.ndarray,
                amp_b: np.ndarray, phase_b: np.ndarray) -> dict:
    """Compare entry A to mirrored entry B (B should equal mirror(A))."""
    amp_b_mirror_from_a = amp_a[:, ::-1]
    phase_b_mirror_from_a = -phase_a[:, ::-1]
    amp_err = np.abs(amp_b - amp_b_mirror_from_a).mean()
    # Phase: wrap to [-pi, pi]
    dphi = np.angle(np.exp(1j * (phase_b - phase_b_mirror_from_a)))
    phase_err = np.abs(dphi).mean()
    return {
        "amp_mae": float(amp_err),
        "amp_max_dev": float(np.abs(amp_b - amp_b_mirror_from_a).max()),
        "phase_mae_rad": float(phase_err),
        "phase_max_dev_rad": float(np.abs(dphi).max()),
    }


def main() -> None:
    print(f"loading LUT: {LUT_PATH}")
    with open(LUT_PATH, "r", encoding="utf-8") as f:
        lut = json.load(f)
    print(f"  entries: {len(lut)}")

    # angle=0, distance=1.0 -> theta_L ~ -4.86, theta_R ~ +4.86
    # quantized at 3 deg step (round half away from zero) -> +/-6
    # Also check +/-3 in case quantization rounds differently
    for tgt in (6, 3):
        keyL = f"{-tgt}_{tgt}"
        keyR = f"{tgt}_{-tgt}"
        if keyL not in lut or keyR not in lut:
            print(f"  MISS: {keyL} or {keyR} not in LUT, skipping")
            continue
        print(f"\n=== mirror pair: {keyL}  vs  {keyR} ===")
        fA, aA, pA = load_entry(lut, -tgt, tgt)
        fB, aB, pB = load_entry(lut, tgt, -tgt)
        assert np.allclose(fA, fB)

        res = mirror_test(aA, pA, aB, pB)
        print(f"  amp   MAE = {res['amp_mae']:.4e}   max dev = {res['amp_max_dev']:.4e}")
        print(f"  phase MAE = {res['phase_mae_rad']:.4e} rad   max dev = {res['phase_max_dev_rad']:.4e} rad")

        # |AF| at fc on dense grid; quantify peak ratio + null depth
        theta_grid = np.linspace(-90, 90, 1801)
        # Use the LUT-frequency closest to fc
        j_fc = int(np.argmin(np.abs(fA - FC)))
        AF_A = array_factor(aA[j_fc], pA[j_fc], fA[j_fc], theta_grid)
        AF_B = array_factor(aB[j_fc], pB[j_fc], fA[j_fc], theta_grid)

        peakA, peakB = AF_A.max(), AF_B.max()
        # null depth: |AF| at null direction
        idx_null_A = int(np.argmin(np.abs(theta_grid - tgt)))    # A's null is +tgt
        idx_null_B = int(np.argmin(np.abs(theta_grid - (-tgt)))) # B's null is -tgt
        nullA = AF_A[idx_null_A]
        nullB = AF_B[idx_null_B]

        print(f"  @ fc={fA[j_fc]:.0f} Hz")
        print(f"    peak |AF|: A={peakA:.4f}  B={peakB:.4f}  ratio A/B={peakA/peakB:.3f}")
        print(f"    null |AF|: A@(+{tgt})={nullA:.4f} ({20*np.log10(nullA/peakA):+.1f} dB)"
              f"   B@(-{tgt})={nullB:.4f} ({20*np.log10(nullB/peakB):+.1f} dB)")

        # If perfect mirror, AF_A(theta) should equal AF_B(-theta)
        AF_B_flipped = AF_B[::-1]
        sym_err = np.abs(AF_A - AF_B_flipped).max()
        print(f"  max |AF_A(theta) - AF_B(-theta)| = {sym_err:.4e}")


if __name__ == "__main__":
    main()
