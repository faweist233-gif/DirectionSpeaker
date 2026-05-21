# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup & Commands

```bash
python -m venv .venv && .\.venv\Scripts\activate
pip install -r requirements.txt

# Check hardware + list ASIO devices
python scripts/verify_env.py

# Virtual mode (no hardware required)
python -m directional_speaker.main --mode virtual --angle 0 --distance 1.0 --backend dummy

# Live mode (requires D435I + ASIO device)
python -m directional_speaker.main --mode live

# Tests (61 tests, no hardware needed)
python -m pytest directional_speaker/tests/ -v

# Single test file
python -m pytest directional_speaker/tests/test_beamformer.py -v
```

## Offline Scripts

```bash
# Regenerate null-steering LUT (~30-60 min) → data/beam_weights/nullsteering_lut.json
python scripts/calibrate_nullsteering.py

# Regenerate report figures → reports/images/
python scripts/make_figures.py

# Interactive camera-array extrinsic calibration → data/extrinsic.json
python -m directional_speaker.calibration
```

## Architecture

Real-time pipeline (25 ms hop, 50 ms window @ 96 kHz):

```
head_tracker → audio_source → hrtf_renderer → audio_adjuster
  → modulator (DSB-AM @ 40 kHz) → beamformer (8-ch null-steering) → playback (ASIO)
```

All physics/DSP constants live in `config.py` — never hardcode values elsewhere. Key parameters: `FC_HZ=40_000`, `FS_HZ=96_000`, `N_CHANNELS=8`, `ELEMENT_SPACING_M≈4.287mm` (λ/2 ULA), `THETA_STEP_DEG=3.0` (LUT quantization).

**Beamformer LUT** (`data/beam_weights/nullsteering_lut.json`): Pre-computed offline by `calibrate_nullsteering.py`. Keys are `"{target_deg}_{null_deg}"` quantized to 3° grid. Per-frequency amp+phase arrays. Never recompute at runtime.

**Joint normalization**: `beamformer.combine()` applies a single gain `α = 1/max(|w_L| + |w_R|)` across all 8 channels and both ears, ensuring the 8-ch peak ≤ 1 regardless of L/R signal correlation.

**Phase continuity**: `modulator.py` maintains absolute sample time across frames to prevent carrier-phase clicks at frame boundaries.

**Head tracker modes**: `VirtualTracker` (fixed angle, pure geometry, no hardware) and `LiveTracker` (D435I + MediaPipe Face Mesh, ear landmarks 234/454, EMA α=0.5). Factory: `make_tracker(mode, angle, distance)`.

**HRTF**: CIPIC subject_003 KEMAR @ 44.1 kHz, resampled to 96 kHz. Must be placed at `data/hrtf/subject_003.mat`. Falls back silently to ITD-only (Woodworth formula) if file absent — behavior is valid but spatially degraded.

**Playback backends**: `SoundDevicePlayback` (ASIO, device hint `"LISSIG"`) and `DummyPlayback` (headless, for CI/tests). `--backend dummy` forces dummy mode.

## PSLL Design Target

Per `reports/DECISIONS.md`: PSLL target is first-sidelobe −13 dB (soft) / −10 dB (hard), not −30 dB. The 8-channel ULA physically cannot achieve −30 dB; the current target matches the engineering standard for the first null region of a uniform array.
