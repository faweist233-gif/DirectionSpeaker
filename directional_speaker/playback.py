"""Playback — sounddevice ASIO 8-channel stream with dummy fallback.

Prompt §6 calls for >=3-frame ring buffer (150 ms at 50 ms frames).
"""
from __future__ import annotations

import logging
import os
import queue
import sys
import threading
import time

if sys.platform == "win32":
    os.environ.setdefault("SD_ENABLE_ASIO", "1")

import numpy as np

from . import config as cfg

log = logging.getLogger(__name__)


class Playback:
    """Abstract playback interface."""

    def start(self) -> None: ...
    def push(self, block: np.ndarray) -> None: ...
    def stop(self) -> None: ...
    @property
    def underrun_count(self) -> int: ...


class DummyPlayback(Playback):
    """No audio output; tracks stats only. Used for CI / headless smoke tests."""

    def __init__(self, n_channels: int = cfg.N_CHANNELS, fs: int = cfg.FS_HZ):
        self.n = n_channels
        self.fs = fs
        self._q: queue.Queue = queue.Queue(maxsize=32)
        self._under = 0
        self._pushed = 0
        self._stop = threading.Event()
        self._thread = None

    def _run(self) -> None:
        frame_s = cfg.WINDOW_MS / 1000
        while not self._stop.is_set():
            try:
                _ = self._q.get(timeout=frame_s * 2)
                time.sleep(frame_s)
            except queue.Empty:
                self._under += 1

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def push(self, block: np.ndarray) -> None:
        if block.shape[0] != self.n:
            raise ValueError(f"expected {self.n} channels, got {block.shape[0]}")
        try:
            self._q.put(block.copy(), timeout=0.5)
            self._pushed += 1
        except queue.Full:
            self._under += 1

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    @property
    def underrun_count(self) -> int:
        return self._under


class SoundDevicePlayback(Playback):
    """sounddevice ASIO backend (if present). Uses OutputStream callback."""

    def __init__(self,
                 device_hint: str = cfg.ASIO_DEVICE_NAME_HINT,
                 n_channels: int = cfg.N_CHANNELS,
                 fs: int = cfg.FS_HZ,
                 blocksize: int = cfg.WINDOW_SAMPLES,
                 buffer_frames: int = cfg.PLAYBACK_BUFFER_FRAMES):
        import sounddevice as sd
        self._sd = sd
        self.device_hint = device_hint
        self.n = n_channels
        self.fs = fs
        self.blocksize = blocksize
        self._q: queue.Queue = queue.Queue(maxsize=max(buffer_frames * 4, 8))
        self._under = 0
        self._stream = None
        self._device_index = self._find_device()

    def _find_device(self) -> int:
        devs = self._sd.query_devices()
        hapis = self._sd.query_hostapis()
        # prefer ASIO hostapi match on device_hint
        for i, d in enumerate(devs):
            hapi_name = hapis[d["hostapi"]]["name"]
            if self.device_hint.lower() in d["name"].lower() and "ASIO" in hapi_name.upper():
                log.info("ASIO device: %s (index %d)", d["name"], i)
                return i
        # fall back to any ASIO device with >=N channels
        for i, d in enumerate(devs):
            hapi_name = hapis[d["hostapi"]]["name"]
            if "ASIO" in hapi_name.upper() and d["max_output_channels"] >= self.n:
                log.warning(
                    "device hint %r not found; using %s",
                    self.device_hint, d["name"]
                )
                return i
        raise RuntimeError(
            f"No ASIO device matching {self.device_hint!r} with >= {self.n} outputs."
        )

    def _callback(self, outdata, frames, time_info, status):
        if status:
            log.warning("sd status: %s", status)
        try:
            block = self._q.get_nowait()
        except queue.Empty:
            outdata.fill(0)
            self._under += 1
            return
        if block.shape[0] != self.n:
            outdata.fill(0)
            self._under += 1
            return
        # block shape (n_channels, frames); sounddevice wants (frames, channels)
        outdata[:] = block.T[:frames]

    def start(self) -> None:
        self._stream = self._sd.OutputStream(
            device=self._device_index,
            samplerate=self.fs,
            blocksize=self.blocksize,
            channels=self.n,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()

    def push(self, block: np.ndarray) -> None:
        if block.shape[0] != self.n:
            raise ValueError(f"expected {self.n} channels, got {block.shape[0]}")
        try:
            self._q.put_nowait(block.astype(np.float32, copy=True))
        except queue.Full:
            self._under += 1

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    @property
    def underrun_count(self) -> int:
        return self._under


def make_playback(backend: str = "auto") -> Playback:
    if backend == "dummy":
        return DummyPlayback()
    if backend == "sounddevice":
        return SoundDevicePlayback()
    if backend == "auto":
        try:
            return SoundDevicePlayback()
        except Exception as e:
            log.warning("sounddevice unavailable (%s); using DummyPlayback", e)
            return DummyPlayback()
    raise ValueError(f"unknown backend {backend}")


if __name__ == "__main__":
    pb = make_playback("dummy")
    pb.start()
    block = np.zeros((cfg.N_CHANNELS, cfg.WINDOW_SAMPLES), dtype=np.float32)
    for _ in range(10):
        pb.push(block)
    time.sleep(0.2)
    pb.stop()
    print(f"underruns={pb.underrun_count}")
