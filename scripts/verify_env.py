"""Environment sanity — imports every dependency, lists ASIO devices."""
from __future__ import annotations

import importlib
import os
import sys

if sys.platform == "win32":
    os.environ.setdefault("SD_ENABLE_ASIO", "1")


def check(mod: str, optional: bool = False) -> bool:
    try:
        m = importlib.import_module(mod)
        v = getattr(m, "__version__", "?")
        print(f"  OK  {mod:20s} {v}")
        return True
    except ImportError as e:
        tag = "WARN" if optional else "FAIL"
        print(f"  {tag:4s} {mod:20s} {e}")
        return optional


def main() -> int:
    ok = True
    for m in ("numpy", "scipy", "matplotlib", "soundfile", "sounddevice"):
        ok &= check(m)
    for m in ("cv2", "pyrealsense2", "mediapipe"):
        ok &= check(m, optional=True)

    try:
        import sounddevice as sd
        print("\nAudio hostapis:")
        for h in sd.query_hostapis():
            print(f"  - {h['name']}")
        print("\nAudio devices (output >=8 channels):")
        for i, d in enumerate(sd.query_devices()):
            if d["max_output_channels"] >= 8:
                hapi = sd.query_hostapis(d["hostapi"])["name"]
                print(f"  [{i:3d}] {d['name']}  (hostapi={hapi}, out={d['max_output_channels']}, fs={d['default_samplerate']:.0f})")
    except Exception as e:
        print(f"  sounddevice device query failed: {e}")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
