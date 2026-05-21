"""Offline null-steering weight calibration (pure NumPy/SciPy).

Mirrors the logic of legacy/audio_generation_v0/optimization_difffreq_widenullsteering.py
(the original PyTorch Adam prototype) but uses L-BFGS-B instead.

Outputs a JSON LUT keyed by "{target}_{null}" (quantised to THETA_STEP_DEG).
Each entry contains:
  - freqs_hz: list of centre frequencies (fc - bw .. fc + bw, step FREQ_STEP_HZ)
  - amp:   (n_freqs, N) float array
  - phase: (n_freqs, N) float array

Run:
    python scripts/calibrate_nullsteering.py

On a modern desktop this takes ~30-60 min for the full 3° grid.
"""
from __future__ import annotations

import argparse
import json
import math
import multiprocessing as mp
import os
import pathlib
import time
from typing import Any

import numpy as np
from scipy.optimize import minimize

# ---------------------------------------------------------------------------
# Constants: imported from the single source of truth (directional_speaker.config)
# ---------------------------------------------------------------------------
_ROOT = pathlib.Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(_ROOT))
from directional_speaker import config as cfg  # noqa: E402

C_SOUND = cfg.C_SOUND
FC_HZ = cfg.FC_HZ
FS_HZ = cfg.FS_HZ
N_CHANNELS = cfg.N_CHANNELS
ELEMENT_SPACING_M = cfg.ELEMENT_SPACING_M

THETA_MIN = -60.0
THETA_MAX = 60.0
THETA_STEP = cfg.THETA_STEP_DEG

PASSBAND_BW = cfg.PASSBAND_BW_HZ
FREQ_STEP = cfg.FREQ_STEP_HZ

# Optimisation grid for array response
AZ_GRID_STEP = 1.0     # degree
AZ_GRID = np.arange(-90, 91, AZ_GRID_STEP)
EDGE_THETA = 90        # for index arithmetic

# Mask widths (degrees)
W_MAIN = 10.0
W_NULL = 10.0

# Loss coefficients (tuned to match reference code ratios)
COEF_MAIN = -1.0
COEF_SIDE = 0.5
COEF_NULL = 10.0
COEF_VAR = 1000.0

MAX_ITER = 2000

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _freqs() -> np.ndarray:
    """Centre frequencies for the passband."""
    n_half = int(PASSBAND_BW / FREQ_STEP)
    return np.array([FC_HZ + i * FREQ_STEP for i in range(-n_half, n_half + 1)])


def _angles() -> np.ndarray:
    """Quantised steering angles."""
    return np.arange(THETA_MIN, THETA_MAX + THETA_STEP / 2, THETA_STEP)


def _build_masks(target: float, null: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return boolean masks for main-lobe, null, and side-lobe regions."""
    n_az = AZ_GRID.size
    target_mask = np.zeros(n_az, dtype=bool)
    null_mask = np.zeros(n_az, dtype=bool)

    # main lobe
    t_lo = target - W_MAIN / 2
    t_hi = target + W_MAIN / 2
    target_mask[(AZ_GRID >= t_lo) & (AZ_GRID <= t_hi)] = True

    # null region
    n_lo = null - W_NULL / 2
    n_hi = null + W_NULL / 2
    null_mask[(AZ_GRID >= n_lo) & (AZ_GRID <= n_hi)] = True

    side_mask = ~(target_mask | null_mask)
    return target_mask, null_mask, side_mask


def _pack(amp: np.ndarray, phase: np.ndarray) -> np.ndarray:
    """Flatten (n_freqs, N) amp + (n_freqs, N) phase into 1-D vector."""
    return np.concatenate([amp.ravel(), phase.ravel()])


def _unpack(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Inverse of _pack."""
    n_freqs = int(len(x) / (2 * N_CHANNELS))
    split = n_freqs * N_CHANNELS
    amp = x[:split].reshape(n_freqs, N_CHANNELS)
    phase = x[split:].reshape(n_freqs, N_CHANNELS)
    return amp, phase


# ---------------------------------------------------------------------------
# Vectorised objective + gradient
# ---------------------------------------------------------------------------

def _objective_and_grad(x: np.ndarray,
                        freqs: np.ndarray,
                        target_mask: np.ndarray,
                        null_mask: np.ndarray,
                        side_mask: np.ndarray) -> tuple[float, np.ndarray]:
    """Return (loss, grad) for the flattened parameter vector x."""
    n_freqs = freqs.size
    n_az = AZ_GRID.size
    N = N_CHANNELS

    amp, phase = _unpack(x)
    np.clip(amp, 0.1, 1.0, out=amp)

    wavelengths = C_SOUND / freqs  # (n_freqs,)
    sin_az = np.sin(np.deg2rad(AZ_GRID))  # (n_az,)

    # Phase delay due to geometry: 2π·n·d/λ·sin(θ)
    # shape (n_freqs, n_az, N)
    n_idx = np.arange(N)
    phase_delay = (2.0 * math.pi * ELEMENT_SPACING_M *
                   n_idx[None, None, :] / wavelengths[:, None, None] *
                   sin_az[None, :, None])

    # Applied phase law: (n_freqs, 1, N)
    total_phase = phase_delay + phase[:, None, :]  # (n_freqs, n_az, N)

    # Amplitude law: (n_freqs, 1, N)
    amp_exp = amp[:, None, :]  # (n_freqs, 1, N)

    # Real / imag parts of the sum
    cos_tp = np.cos(total_phase)
    sin_tp = np.sin(total_phase)
    re = np.sum(amp_exp * cos_tp, axis=2)  # (n_freqs, n_az)
    im = np.sum(amp_exp * sin_tp, axis=2)  # (n_freqs, n_az)

    mag = np.sqrt(re ** 2 + im ** 2) / N  # (n_freqs, n_az)
    mag = np.maximum(mag, 1e-12)  # avoid div-by-zero

    # --- loss terms ---
    main_power = np.sum(mag[:, target_mask])           # scalar
    null_power = np.sum(mag[:, null_mask])             # scalar
    side_power = np.sum(mag[:, side_mask])             # scalar
    freq_main = np.sum(mag[:, target_mask], axis=1)    # (n_freqs,)
    freqs_var = np.var(freq_main)                      # scalar

    loss = (COEF_MAIN * main_power +
            COEF_SIDE * side_power +
            COEF_NULL * null_power +
            COEF_VAR * freqs_var)

    # --- gradients ---
    inv_mag = 1.0 / mag  # (n_freqs, n_az)
    re_inv = re * inv_mag  # (n_freqs, n_az)
    im_inv = im * inv_mag  # (n_freqs, n_az)

    dmag_da = (re_inv[:, :, None] * cos_tp +
               im_inv[:, :, None] * sin_tp) / N       # (n_freqs, n_az, N)
    dmag_dp = amp_exp * (-re_inv[:, :, None] * sin_tp +
                          im_inv[:, :, None] * cos_tp) / N  # (n_freqs, n_az, N)

    # ∂loss/∂mag coefficients
    coef = np.zeros_like(mag)  # (n_freqs, n_az)
    coef[:, target_mask] = COEF_MAIN
    coef[:, null_mask] = COEF_NULL
    coef[:, side_mask] = COEF_SIDE

    # freqs_var term
    n_target = target_mask.sum()
    if n_target > 0:
        mean_x = freq_main.mean()
        dvar = 2.0 * (freq_main - mean_x) / n_target  # (n_freqs,)
        dvar_exp = np.zeros_like(mag)
        dvar_exp[:, target_mask] = dvar[:, None]
        coef += COEF_VAR * dvar_exp

    grad_a = np.sum(coef[:, :, None] * dmag_da, axis=1)  # (n_freqs, N)
    grad_p = np.sum(coef[:, :, None] * dmag_dp, axis=1)  # (n_freqs, N)

    grad = _pack(grad_a, grad_p)
    return float(loss), grad


# ---------------------------------------------------------------------------
# Single (target, null) optimisation
# ---------------------------------------------------------------------------

def _optimize_one(args: tuple[float, float, np.ndarray,
                  np.ndarray, np.ndarray, np.ndarray]) -> dict[str, Any]:
    target, null, freqs, target_mask, null_mask, side_mask = args
    n_freqs = freqs.size
    N = N_CHANNELS

    # Initialise with theoretical phase law
    wavelengths = C_SOUND / freqs
    amp0 = np.ones((n_freqs, N))
    phase0 = np.zeros((n_freqs, N))
    for i, lam in enumerate(wavelengths):
        for n in range(N):
            phase0[i, n] = -2.0 * math.pi * n * ELEMENT_SPACING_M / lam * math.sin(math.radians(target))

    x0 = _pack(amp0, phase0)

    # Bounds: amp [0.1, 1.0], phase unbounded
    lb = np.concatenate([np.full(n_freqs * N, 0.1), np.full(n_freqs * N, -np.inf)])
    ub = np.concatenate([np.full(n_freqs * N, 1.0), np.full(n_freqs * N, np.inf)])
    bounds = list(zip(lb, ub))

    t0 = time.time()
    res = minimize(
        lambda x: _objective_and_grad(x, freqs, target_mask, null_mask, side_mask),
        x0,
        method="L-BFGS-B",
        jac=True,
        bounds=bounds,
        options={"maxiter": MAX_ITER, "disp": False},
    )
    elapsed = time.time() - t0

    amp_opt, phase_opt = _unpack(res.x)
    np.clip(amp_opt, 0.1, 1.0, out=amp_opt)

    # Normalise phase by channel-0 reference (matches reference code convention)
    phase_opt = phase_opt - phase_opt[:, 0:1]

    loss_final, _ = _objective_and_grad(res.x, freqs, target_mask, null_mask, side_mask)

    key = f"{int(round(target))}_{int(round(null))}"
    print(f"[calibrate] {key}  loss={loss_final:.3f}  iters={res.nit}  time={elapsed:.1f}s")

    return {
        "key": key,
        "freqs_hz": freqs.tolist(),
        "amp": amp_opt.tolist(),
        "phase": phase_opt.tolist(),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="data/beam_weights/nullsteering_lut.json")
    p.add_argument("--workers", type=int, default=max(1, mp.cpu_count() - 1))
    p.add_argument("--dry-run", action="store_true", help="print grid size and exit")
    args = p.parse_args()

    freqs = _freqs()
    angles = _angles()

    print(f"Grid: {angles.size} angles x {angles.size} pairs = {angles.size**2} combos")
    print(f"Freqs: {freqs.size} bins  ({freqs[0]} .. {freqs[-1]} Hz)")
    print(f"Vars per combo: {freqs.size * N_CHANNELS * 2}")

    if args.dry_run:
        return

    # Pre-build masks
    tasks = []
    for target in angles:
        for null in angles:
            tm, nm, sm = _build_masks(target, null)
            tasks.append((target, null, freqs, tm, nm, sm))

    out_path = pathlib.Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    lut: dict[str, Any] = {}
    if args.workers > 1:
        with mp.Pool(args.workers) as pool:
            for result in pool.imap_unordered(_optimize_one, tasks):
                lut[result["key"]] = {
                    "freqs_hz": result["freqs_hz"],
                    "amp": result["amp"],
                    "phase": result["phase"],
                }
    else:
        for task in tasks:
            result = _optimize_one(task)
            lut[result["key"]] = {
                "freqs_hz": result["freqs_hz"],
                "amp": result["amp"],
                "phase": result["phase"],
            }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(lut, f, indent=2)

    print(f"\nWrote LUT ({len(lut)} entries) to {out_path}")


if __name__ == "__main__":
    main()
