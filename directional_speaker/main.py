"""Main real-time pipeline.

tick (50 ms):
  tracker -> ear pose
  audio_source -> mono 50-ms frame
  hrtf_renderer -> (s_L, s_R)
  audio_adjuster -> distance compensation
  modulator -> upconvert both to 40 kHz (shared carrier phase)
  beamformer -> per-frequency null-steering -> 8-ch output
  playback -> push to ASIO ring

Run:
  python -m directional_speaker.main --mode virtual --angle 0
  python -m directional_speaker.main --mode virtual --angle -60 --distance 1.2
  python -m directional_speaker.main --mode live
"""
from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
import pathlib

import numpy as np

from . import config as cfg
from .audio_source import AudioSource, write_synthetic_speech
from .hrtf_renderer import HRTFRenderer, synthetic_hrir_pair
from .modulator import DSBAMModulator
from .audio_adjuster import AudioAdjuster
from .beamformer import Beamformer
from .head_tracker import make_tracker
from .playback import make_playback

log = logging.getLogger("directional_speaker.main")


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser("directional_speaker")
    p.add_argument("--mode", choices=["live", "virtual"], required=True)
    p.add_argument("--angle", type=int, default=0,
                   help="virtual mode azimuth in {-60, 0, 60}")
    p.add_argument("--distance", type=float, default=cfg.VIRTUAL_DEFAULT_DISTANCE_M,
                   help="virtual mode distance in metres")
    p.add_argument("--camera-height", type=float, default=None,
                   help="vertical distance from array centre to D435I (metres); "
                        "used to build extrinsic when data/extrinsic.json is missing. "
                        "defaults to config.CAMERA_HEIGHT_M (%.2f)" % cfg.CAMERA_HEIGHT_M)
    p.add_argument("--audio", type=str, default=cfg.AUDIO_WAV_DEFAULT,
                   help="mono wav source; synthesized if missing")
    p.add_argument("--backend", choices=["auto", "sounddevice", "dummy"], default="auto")
    p.add_argument("--duration", type=float, default=0.0,
                   help="run for this many seconds (0 = until Ctrl-C)")
    p.add_argument("--no-hrtf", action="store_true",
                   help="bypass CIPIC HRTF, use synthetic ITD-only")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


class _Orchestrator:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        logging.basicConfig(
            level=logging.DEBUG if args.verbose else logging.INFO,
            format="%(asctime)s %(name)s %(levelname)s %(message)s",
        )
        self.tracker = make_tracker(args.mode, args.angle, args.distance,
                                     args.camera_height)
        self.audio = self._open_audio(args.audio)
        self.adjuster = AudioAdjuster()
        self.modulator = DSBAMModulator()
        self.beamformer = Beamformer()
        self.playback = make_playback(args.backend)
        self.hrtf = None if args.no_hrtf else HRTFRenderer()
        self._hrtf_ready = False
        self._stop = False
        signal.signal(signal.SIGINT, self._on_sigint)

    def _on_sigint(self, *_):
        log.info("SIGINT -> stopping")
        self._stop = True

    def _open_audio(self, path: str) -> AudioSource:
        p = pathlib.Path(path)
        if not p.is_file():
            log.warning("%s missing; writing synthetic speech", p)
            write_synthetic_speech(p)
        return AudioSource(p)

    def _hrtf_render(self, x: np.ndarray, az_L: float, az_R: float) -> tuple[np.ndarray, np.ndarray]:
        if self.hrtf is None:
            return x.copy(), x.copy()
        if not self._hrtf_ready:
            try:
                self.hrtf.load()
                self._hrtf_ready = True
            except FileNotFoundError as e:
                log.warning("%s -- falling back to synthetic ITD HRIR", e)
                self.hrtf = None
                return self._synth_render(x, az_L, az_R)
        return self.hrtf.render_stereo(x, az_L, az_R)

    @staticmethod
    def _synth_render(x: np.ndarray, az_L: float, az_R: float) -> tuple[np.ndarray, np.ndarray]:
        h_L, _ = synthetic_hrir_pair(az_L)
        _, h_R = synthetic_hrir_pair(az_R)
        from scipy.signal import fftconvolve
        y_L = fftconvolve(x, h_L)[:x.size]
        y_R = fftconvolve(x, h_R)[:x.size]
        return y_L.astype(np.float32), y_R.astype(np.float32)

    def run(self) -> None:
        self.playback.start()
        frame_iter = self.audio.frames()
        tick_s = cfg.HOP_MS / 1000
        n_ticks = 0
        next_log_t = time.time() + cfg.LOG_INTERVAL_S
        t_start = time.time()
        try:
            while not self._stop:
                loop_start = time.time()
                pose = self.tracker.get_ear_pose()
                mono = next(frame_iter)
                s_L, s_R = self._hrtf_render(mono, pose.theta_L_deg, pose.theta_R_deg)
                s_L, s_R = self.adjuster.adjust(s_L, s_R, pose.d_L_m, pose.d_R_m)
                # clip to [-1, 1] to guarantee modulation index m<=1
                s_L = np.clip(s_L, -1.0, 1.0)
                s_R = np.clip(s_R, -1.0, 1.0)

                # Passband modulation with shared carrier phase
                mod_L, mod_R = self.modulator.modulate_multi(s_L, s_R)

                # Per-frequency null-steering beamforming
                block = self.beamformer.combine(
                    pose.theta_L_deg, pose.theta_R_deg, mod_L, mod_R,
                )

                self.playback.push(block)
                n_ticks += 1

                # throttle to real-time-ish
                elapsed = time.time() - loop_start
                remaining = tick_s - elapsed
                if remaining > 0:
                    time.sleep(remaining)

                if time.time() >= next_log_t:
                    under = self.playback.underrun_count
                    log.info(
                        "ticks=%d  underruns=%d  pose theta=(L%.1f, R%.1f) d=(L%.2f, R%.2f)",
                        n_ticks, under,
                        pose.theta_L_deg, pose.theta_R_deg,
                        pose.d_L_m, pose.d_R_m,
                    )
                    next_log_t += cfg.LOG_INTERVAL_S

                if self.args.duration and (time.time() - t_start) >= self.args.duration:
                    break
        finally:
            self.playback.stop()
            self.tracker.close()
            log.info(
                "stopped. ticks=%d underruns=%d duration=%.2fs",
                n_ticks, self.playback.underrun_count, time.time() - t_start,
            )


def main(argv=None) -> int:
    args = _parse_args(argv)
    orch = _Orchestrator(args)
    orch.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
