"""Global constants. Edit here; no hard-coded values elsewhere."""
from __future__ import annotations

import math

# --- physical constants ---
C_SOUND: float = 343.0  # m/s, dry air @ 20C

# --- carrier / sampling ---
FC_HZ: int = 40_000          # carrier
FS_HZ: int = 96_000          # DAC sample rate to ASIO
LAMBDA_M: float = C_SOUND / FC_HZ  # ~8.575 mm

# --- array geometry ---
N_CHANNELS: int = 8           # 8 logical channels; each channel drives 4 vertical transducers
ELEMENT_SPACING_M: float = LAMBDA_M / 2.0  # ~4.287 mm ULA half-wavelength

# --- windowing ---
WINDOW_MS: float = 50.0
HOP_MS: float = 25.0
WINDOW_SAMPLES: int = int(FS_HZ * WINDOW_MS / 1000)
HOP_SAMPLES: int = int(FS_HZ * HOP_MS / 1000)

# --- null-steering beamformer ---
THETA_STEP_DEG: float = 3.0              # LUT angle quantisation
PASSBAND_BW_HZ: float = 4000.0           # ±4 kHz sideband bandwidth
FREQ_STEP_HZ: float = 100.0              # LUT frequency step
BEAM_LUT_PATH: str = "data/beam_weights/nullsteering_lut.json"

# --- audio source ---
AUDIO_WAV_DEFAULT: str = "data/audio/speech_mono.wav"

# --- HRTF ---
HRTF_SUBJECT_ID: int = 3                     # CIPIC subject_003 == KEMAR
HRTF_MAT_PATH: str = "data/hrtf/subject_003.mat"
HRTF_ORIG_FS_HZ: int = 44_100                # CIPIC raw
HRIR_LEN: int = 200                          # CIPIC HRIR length

# --- head tracker ---
W_EAR_M: float = 0.06                        # helix-tragus horizontal span, adult mean
INTERAURAL_M: float = 0.17                   # 17 cm adult average
VIRTUAL_DEFAULT_DISTANCE_M: float = 1.0
VIRTUAL_ALLOWED_ANGLES_DEG: tuple = (-60, 0, 60)
EMA_ALPHA: float = 0.5

# --- playback (buffer >= 3 frames) ---
ASIO_DEVICE_NAME_HINT: str = "LISSIG"        # substring match into sd.query_devices
PLAYBACK_BUFFER_FRAMES: int = 3
PLAYBACK_FALLBACK_BACKEND: str = "dummy"     # when no ASIO device found

# --- camera extrinsic ---
EXTRINSIC_JSON: str = "data/extrinsic.json"
# When extrinsic.json is missing, build the camera-to-array transform assuming
# the D435I is centred directly above OR below the array (same x, same z).
# Sign convention: positive = camera above array, negative = camera below array.
# Camera +y = down, array +y = up -> the matrix flips y and translates by h.
# Set to 0 if camera and array centres are at the same height (y-flip remains).
CAMERA_HEIGHT_M: float = -0.20

# --- runtime telemetry ---
LOG_INTERVAL_S: float = 1.0


def deg2rad(x: float) -> float:
    return x * math.pi / 180.0
