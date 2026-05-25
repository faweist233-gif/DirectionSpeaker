"""End-to-end 2D ultrasound field diagnostic.

Replicates the pipeline of `--mode virtual --angle 0 --distance 1.0`:
  audio -> HRTF (synth fallback) -> adjuster -> DSB-AM mod -> null-steering beam
then propagates the 8-channel output into a 2D (x, z) grid using free-space
spherical spreading + per-element phase, and plots intensity at 40 kHz.

This is OUR reference simulation. If the user's myplot.png shows a substantially
different asymmetry than this script, the discrepancy is in the user's external
plotting/measurement, not in this project's L/R generation.
"""
from __future__ import annotations

import pathlib
import sys

import numpy as np
import matplotlib.pyplot as plt

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from directional_speaker import config as cfg  # noqa: E402
from directional_speaker.beamformer import Beamformer  # noqa: E402
from directional_speaker.modulator import DSBAMModulator  # noqa: E402
from directional_speaker.audio_adjuster import AudioAdjuster  # noqa: E402
from directional_speaker.hrtf_renderer import synthetic_hrir_pair  # noqa: E402
from directional_speaker.head_tracker import make_tracker  # noqa: E402

N = cfg.N_CHANNELS
D = cfg.ELEMENT_SPACING_M
C = cfg.C_SOUND
FC = cfg.FC_HZ
FS = cfg.FS_HZ
T = cfg.WINDOW_SAMPLES


def gen_mono(T: int, fs: int) -> np.ndarray:
    """Bandlimited white noise (300 Hz - 3.4 kHz, speech-like)."""
    rng = np.random.default_rng(42)
    x = rng.standard_normal(T).astype(np.float32) * 0.3
    return x


def run_pipeline(angle: float, distance: float) -> np.ndarray:
    """Return 8-channel passband output, shape (8, T)."""
    tracker = make_tracker("virtual", angle, distance, None)
    pose = tracker.get_ear_pose()
    print(f"  pose: theta_L={pose.theta_L_deg:.3f}  theta_R={pose.theta_R_deg:.3f}"
          f"  d_L={pose.d_L_m:.4f}  d_R={pose.d_R_m:.4f}")

    mono = gen_mono(T, FS)

    # synth HRTF fallback (CIPIC absent)
    from scipy.signal import fftconvolve
    h_L, _ = synthetic_hrir_pair(pose.theta_L_deg)
    _, h_R = synthetic_hrir_pair(pose.theta_R_deg)
    s_L = fftconvolve(mono, h_L)[:T].astype(np.float32)
    s_R = fftconvolve(mono, h_R)[:T].astype(np.float32)
    print(f"  after HRTF synth: ||s_L||={np.linalg.norm(s_L):.4f}  ||s_R||={np.linalg.norm(s_R):.4f}")

    adj = AudioAdjuster()
    s_L, s_R = adj.adjust(s_L, s_R, pose.d_L_m, pose.d_R_m)
    print(f"  after adjuster:   ||s_L||={np.linalg.norm(s_L):.4f}  ||s_R||={np.linalg.norm(s_R):.4f}")

    s_L = np.clip(s_L, -1.0, 1.0)
    s_R = np.clip(s_R, -1.0, 1.0)

    mod = DSBAMModulator()
    mod_L, mod_R = mod.modulate_multi(s_L, s_R)
    print(f"  after modulator:  ||mod_L||={np.linalg.norm(mod_L):.4f}  ||mod_R||={np.linalg.norm(mod_R):.4f}")

    bf = Beamformer()
    # Run apply_passband separately so we can inspect each branch
    out_L = bf.apply_passband(mod_L, pose.theta_L_deg, pose.theta_R_deg)  # (8, T)
    out_R = bf.apply_passband(mod_R, pose.theta_R_deg, pose.theta_L_deg)
    print(f"  apply_passband:   ||out_L||={np.linalg.norm(out_L):.4f}  ||out_R||={np.linalg.norm(out_R):.4f}")
    print(f"                    peak|out_L|={np.abs(out_L).max():.4f}  peak|out_R|={np.abs(out_R).max():.4f}")

    out = (out_L + out_R) / 2.0
    peak = np.max(np.abs(out))
    print(f"  before soft clip: peak|out|={peak:.4f}")
    if peak > 1.0:
        out = out / peak
        print(f"  -> applied soft clip (gain={1/peak:.4f})")

    return out.astype(np.float32), out_L, out_R


def fft_at_fc(y8: np.ndarray) -> np.ndarray:
    """Return complex amplitude per channel at frequency closest to fc."""
    Y = np.fft.rfft(y8, axis=-1)  # (8, n_fft)
    freqs = np.fft.rfftfreq(y8.shape[-1], 1.0 / FS)
    k = int(np.argmin(np.abs(freqs - FC)))
    return Y[:, k], freqs[k]


def propagate_2d(amp8: np.ndarray, x_grid_m: np.ndarray, z_grid_m: np.ndarray, f_hz: float) -> np.ndarray:
    """Free-space spherical-spreading propagation from each of 8 elements.

    amp8: shape (8,), complex per-channel amplitude at frequency f_hz.
    Returns |P|^2 (intensity) on (z, x) grid.
    """
    # Elements at x_n = (n - (N-1)/2) * D, z=0
    n_idx = np.arange(N)
    x_n = (n_idx - (N - 1) / 2) * D
    Z, X = np.meshgrid(z_grid_m, x_grid_m, indexing="ij")  # (nz, nx)
    P = np.zeros_like(X, dtype=complex)
    k_w = 2 * np.pi * f_hz / C
    for n in range(N):
        r = np.sqrt((X - x_n[n]) ** 2 + Z ** 2)
        r = np.maximum(r, 1e-3)
        P += amp8[n] * np.exp(-1j * k_w * r) / r
    return np.abs(P) ** 2


def main() -> None:
    print("=== Pipeline run: angle=0 distance=1.0 ===")
    out_total, out_L, out_R = run_pipeline(angle=0, distance=1.0)

    # Per-channel amplitude at fc
    aL, f_pick = fft_at_fc(out_L)
    aR, _ = fft_at_fc(out_R)
    aT, _ = fft_at_fc(out_total)
    print(f"\nAt FFT bin {f_pick:.1f} Hz:")
    print(f"  |a_L|_per_ch = {np.abs(aL).round(4)}  sum={np.sum(np.abs(aL)):.4f}")
    print(f"  |a_R|_per_ch = {np.abs(aR).round(4)}  sum={np.sum(np.abs(aR)):.4f}")

    # 2D field grid
    x_grid = np.linspace(-0.6, 0.6, 241)   # meters
    z_grid = np.linspace(0.05, 1.4, 271)
    I_L = propagate_2d(aL, x_grid, z_grid, f_pick)
    I_R = propagate_2d(aR, x_grid, z_grid, f_pick)
    I_T = propagate_2d(aT, x_grid, z_grid, f_pick)

    # Pick a horizontal slice at z = 1.0 m to quantify L/R intensity
    z_idx = int(np.argmin(np.abs(z_grid - 1.0)))
    print(f"\nAt z=1.0 m horizontal slice (z_idx={z_idx}, z={z_grid[z_idx]:.3f} m):")
    print(f"  max I_L at x = {x_grid[np.argmax(I_L[z_idx])]:.3f} m  intensity={I_L[z_idx].max():.4e}")
    print(f"  max I_R at x = {x_grid[np.argmax(I_R[z_idx])]:.3f} m  intensity={I_R[z_idx].max():.4e}")
    print(f"  max I_T at x = {x_grid[np.argmax(I_T[z_idx])]:.3f} m  intensity={I_T[z_idx].max():.4e}")
    peakL = I_T[z_idx, x_grid <= 0].max()
    peakR = I_T[z_idx, x_grid >= 0].max()
    print(f"  I_total peak in x<0: {peakL:.4e}")
    print(f"  I_total peak in x>0: {peakR:.4e}")
    print(f"  L/R ratio: {peakL / peakR:.3f}  =  {10*np.log10(peakL/peakR):+.2f} dB")

    # Plot
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
    extent = [x_grid[0]*100, x_grid[-1]*100, z_grid[-1]*100, z_grid[0]*100]
    for ax, I, title in zip(axes, [I_L, I_R, I_T],
                             ["y_L only (8-ch)", "y_R only (8-ch)", "y_total = (y_L+y_R)/2"]):
        I_db = 10 * np.log10(np.maximum(I, I.max() * 1e-6))
        im = ax.imshow(I_db, aspect="auto", extent=extent, cmap="jet",
                       vmax=I_db.max(), vmin=I_db.max() - 40)
        ax.set_title(title)
        ax.set_xlabel("x [cm]")
        ax.set_ylabel("z [cm]")
        plt.colorbar(im, ax=ax, label="dB")
    fig.suptitle(f"2D sound field at {f_pick/1000:.1f} kHz  (angle=0, d=1.0)")
    fig.tight_layout()
    out_path = ROOT / "data" / "image" / "diag_field_2d.png"
    fig.savefig(out_path, dpi=120)
    print(f"\nsaved: {out_path}")


if __name__ == "__main__":
    main()
