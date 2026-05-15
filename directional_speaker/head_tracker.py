"""Head tracker — abstract interface with Live (D435I) and Virtual implementations.

All angles in degrees. All distances in meters. Array coordinate system:
  +x = right of array, +y = up, +z = forward (away from array face).
  Origin at array geometric center. theta = atan2(x, z) in degrees.
"""
from __future__ import annotations

import abc
import json
import logging
import pathlib
from dataclasses import dataclass

import numpy as np

from . import config as cfg

log = logging.getLogger(__name__)


@dataclass
class EarPose:
    theta_L_deg: float
    theta_R_deg: float
    d_L_m: float
    d_R_m: float
    delta_theta_L_deg: float   # ear receiving angle, for beam-width warning
    delta_theta_R_deg: float


class HeadTracker(abc.ABC):
    @abc.abstractmethod
    def get_ear_pose(self) -> EarPose: ...

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Virtual tracker (no hardware)
# ---------------------------------------------------------------------------

class VirtualTracker(HeadTracker):
    def __init__(self,
                 angle_deg: int,
                 distance_m: float = cfg.VIRTUAL_DEFAULT_DISTANCE_M,
                 interaural_m: float = cfg.INTERAURAL_M,
                 w_ear_m: float = cfg.W_EAR_M):
        if angle_deg not in cfg.VIRTUAL_ALLOWED_ANGLES_DEG:
            raise ValueError(
                f"--angle must be one of {cfg.VIRTUAL_ALLOWED_ANGLES_DEG}, got {angle_deg}"
            )
        self.angle = float(angle_deg)
        self.d = float(distance_m)
        self.interaural = interaural_m
        self.w_ear = w_ear_m

    def get_ear_pose(self) -> EarPose:
        ang = np.deg2rad(self.angle)
        # Head center at (d*sin, 0, d*cos). Head faces array (yaw aligned).
        cx = self.d * np.sin(ang)
        cz = self.d * np.cos(ang)
        # interaural axis perpendicular to head facing; for yaw==angle, left ear
        # offset = (-cos(ang), 0, sin(ang)) * interaural/2
        offL_x = -np.cos(ang) * self.interaural / 2
        offL_z = np.sin(ang) * self.interaural / 2
        offR_x = np.cos(ang) * self.interaural / 2
        offR_z = -np.sin(ang) * self.interaural / 2
        L = (cx + offL_x, cz + offL_z)
        R = (cx + offR_x, cz + offR_z)
        theta_L = float(np.rad2deg(np.arctan2(L[0], L[1])))
        theta_R = float(np.rad2deg(np.arctan2(R[0], R[1])))
        d_L = float(np.hypot(*L))
        d_R = float(np.hypot(*R))
        delta_L = float(np.rad2deg(2 * np.arctan2(self.w_ear / 2, d_L)))
        delta_R = float(np.rad2deg(2 * np.arctan2(self.w_ear / 2, d_R)))
        return EarPose(theta_L, theta_R, d_L, d_R, delta_L, delta_R)


# ---------------------------------------------------------------------------
# Live tracker (D435I + MediaPipe) — lazy import so virtual mode has no deps
# ---------------------------------------------------------------------------

class LiveTracker(HeadTracker):
    def __init__(self, extrinsic_json: str = cfg.EXTRINSIC_JSON,
                 camera_height: float | None = None):
        self._camera_height = (camera_height if camera_height is not None
                               else cfg.CAMERA_HEIGHT_M)
        self._pipeline = None
        self._align = None
        self._face_mesh = None
        self._extrinsic = self._load_extrinsic(extrinsic_json, self._camera_height)
        self._ema_prev: EarPose | None = None
        self._start()

    @staticmethod
    def _load_extrinsic(path: str, camera_height: float) -> np.ndarray:
        p = pathlib.Path(path)
        if p.is_file():
            obj = json.loads(p.read_text(encoding="utf-8"))
            T = np.array(obj["camera_to_array"], dtype=float)
            if T.shape != (4, 4):
                raise ValueError(f"extrinsic must be 4x4, got {T.shape}")
            return T
        log.warning("extrinsic %s missing, building from camera_height=%.3f m",
                    p, camera_height)
        return LiveTracker._build_extrinsic(camera_height)

    @staticmethod
    def _build_extrinsic(camera_height: float) -> np.ndarray:
        """4×4 camera-to-array transform assuming the D435I is centred directly
        above or below the array (same x, same z), with a known vertical offset.

        Camera frame:  +x right, +y DOWN, +z forward
        Array frame:   +x right, +y UP,   +z forward

        Sign convention: camera_height > 0 → camera above array;
                         camera_height < 0 → camera below array.

        The only non-identity entries are the y-flip (R[1,1] = -1) and the
        vertical translation (T[1,3] = camera_height).
        """
        T = np.eye(4, dtype=float)
        T[1, 1] = -1.0           # y: camera-down → array-up
        T[1, 3] = camera_height  # camera origin in array frame
        return T

    def _start(self) -> None:
        try:
            import pyrealsense2 as rs
            import mediapipe as mp
        except ImportError as e:
            raise ImportError(
                "Live mode needs pyrealsense2 and mediapipe. "
                "Install or use --mode virtual."
            ) from e
        self._rs = rs
        pipe = rs.pipeline()
        cfg_rs = rs.config()
        cfg_rs.enable_stream(rs.stream.depth, 848, 480, rs.format.z16, 30)
        cfg_rs.enable_stream(rs.stream.color, 1280, 720, rs.format.bgr8, 30)
        self._profile = pipe.start(cfg_rs)
        self._pipeline = pipe
        self._align = rs.align(rs.stream.color)
        self._intr = (
            self._profile.get_stream(rs.stream.color)
            .as_video_stream_profile()
            .get_intrinsics()
        )
        self._face_mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False, max_num_faces=1, refine_landmarks=True,
            min_detection_confidence=0.5, min_tracking_confidence=0.5,
        )

    def close(self) -> None:
        if self._pipeline is not None:
            self._pipeline.stop()
            self._pipeline = None
        if self._face_mesh is not None:
            self._face_mesh.close()
            self._face_mesh = None

    def _deproject(self, u: float, v: float, z: float) -> tuple[float, float, float]:
        intr = self._intr
        x = (u - intr.ppx) / intr.fx * z
        y = (v - intr.ppy) / intr.fy * z
        return float(x), float(y), float(z)

    def _camera_to_array(self, p_cam: tuple[float, float, float]) -> tuple[float, float, float]:
        v = np.array([*p_cam, 1.0])
        out = self._extrinsic @ v
        return float(out[0]), float(out[1]), float(out[2])

    def _ema(self, cur: EarPose) -> EarPose:
        a = cfg.EMA_ALPHA
        prev = self._ema_prev
        if prev is None:
            self._ema_prev = cur
            return cur
        smoothed = EarPose(
            theta_L_deg=a * cur.theta_L_deg + (1 - a) * prev.theta_L_deg,
            theta_R_deg=a * cur.theta_R_deg + (1 - a) * prev.theta_R_deg,
            d_L_m=a * cur.d_L_m + (1 - a) * prev.d_L_m,
            d_R_m=a * cur.d_R_m + (1 - a) * prev.d_R_m,
            delta_theta_L_deg=a * cur.delta_theta_L_deg + (1 - a) * prev.delta_theta_L_deg,
            delta_theta_R_deg=a * cur.delta_theta_R_deg + (1 - a) * prev.delta_theta_R_deg,
        )
        self._ema_prev = smoothed
        return smoothed

    def get_ear_pose(self) -> EarPose:
        frames = self._pipeline.wait_for_frames(5000)
        aligned = self._align.process(frames)
        depth = aligned.get_depth_frame()
        color = aligned.get_color_frame()
        if not depth or not color:
            raise RuntimeError("frame fetch failed")
        import numpy as np
        color_img = np.asanyarray(color.get_data())
        # BGR -> RGB for mediapipe
        rgb = color_img[..., ::-1]
        res = self._face_mesh.process(rgb)
        if not res.multi_face_landmarks:
            if self._ema_prev is not None:
                return self._ema_prev
            raise RuntimeError("no face detected and no prior state")

        lm = res.multi_face_landmarks[0].landmark
        H, W = rgb.shape[:2]
        def _pix(idx: int) -> tuple[int, int]:
            return int(lm[idx].x * W), int(lm[idx].y * H)

        u_L, v_L = _pix(234)
        u_R, v_R = _pix(454)
        d_L_raw = depth.get_distance(u_L, v_L)
        d_R_raw = depth.get_distance(u_R, v_R)
        if d_L_raw <= 0 or d_R_raw <= 0:
            if self._ema_prev is not None:
                return self._ema_prev
            raise RuntimeError("invalid depth at ear landmarks")

        pL_cam = self._deproject(u_L, v_L, d_L_raw)
        pR_cam = self._deproject(u_R, v_R, d_R_raw)
        pL_arr = self._camera_to_array(pL_cam)
        pR_arr = self._camera_to_array(pR_cam)

        def _ang_dist(p):
            theta = float(np.rad2deg(np.arctan2(p[0], p[2])))
            d = float(np.hypot(p[0], p[2]))
            delta = float(np.rad2deg(2 * np.arctan2(cfg.W_EAR_M / 2, max(d, 1e-3))))
            return theta, d, delta

        tL, dL, deL = _ang_dist(pL_arr)
        tR, dR, deR = _ang_dist(pR_arr)
        raw = EarPose(tL, tR, dL, dR, deL, deR)
        return self._ema(raw)


def make_tracker(mode: str, angle: int | None = None, distance: float | None = None,
                 camera_height: float | None = None) -> HeadTracker:
    if mode == "virtual":
        return VirtualTracker(
            angle_deg=int(angle) if angle is not None else 0,
            distance_m=float(distance) if distance is not None else cfg.VIRTUAL_DEFAULT_DISTANCE_M,
        )
    if mode == "live":
        return LiveTracker(camera_height=camera_height)
    raise ValueError(f"unknown mode: {mode}")


if __name__ == "__main__":
    for a in (-60, 0, 60):
        t = VirtualTracker(a)
        print(a, t.get_ear_pose())
