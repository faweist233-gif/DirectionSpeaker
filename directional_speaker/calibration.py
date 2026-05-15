"""One-shot camera-to-array extrinsic calibration (prompt §7 + §4.1).

Procedure (MANUAL.md §7.1):
  1. Mount a 9x6 checkerboard (20 mm squares) coplanar with the array face,
     with its centre at the array geometric centre. Array +x points right,
     +y up, +z forward.
  2. Run this script. Capture 5 checkerboard frames.
  3. Script solves cv2.solvePnP to get board pose in camera frame, then
     composes with the known board->array transform (identity by design,
     since board centre = array centre).

Output: writes config.EXTRINSIC_JSON with 4x4 matrix mapping
camera-space point -> array-space point (array_from_camera).
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np

from . import config as cfg

CHECKER_ROWS = 6
CHECKER_COLS = 9
SQUARE_SIZE_M = 0.020
N_CAPTURES = 5


def _object_points() -> np.ndarray:
    objp = np.zeros((CHECKER_ROWS * CHECKER_COLS, 3), dtype=np.float32)
    objp[:, :2] = np.mgrid[0:CHECKER_COLS, 0:CHECKER_ROWS].T.reshape(-1, 2) * SQUARE_SIZE_M
    # center the board: origin at board centre
    objp[:, 0] -= (CHECKER_COLS - 1) * SQUARE_SIZE_M / 2
    objp[:, 1] -= (CHECKER_ROWS - 1) * SQUARE_SIZE_M / 2
    return objp


def run_calibration(out_path: str = cfg.EXTRINSIC_JSON) -> pathlib.Path:
    try:
        import cv2
        import pyrealsense2 as rs
    except ImportError as e:
        raise ImportError(
            "calibration needs opencv-python and pyrealsense2"
        ) from e

    pipeline = rs.pipeline()
    cfg_rs = rs.config()
    cfg_rs.enable_stream(rs.stream.color, 1280, 720, rs.format.bgr8, 30)
    profile = pipeline.start(cfg_rs)
    intr = (
        profile.get_stream(rs.stream.color)
        .as_video_stream_profile()
        .get_intrinsics()
    )
    K = np.array([[intr.fx, 0, intr.ppx],
                  [0, intr.fy, intr.ppy],
                  [0, 0, 1]], dtype=np.float64)
    dist = np.array(intr.coeffs[:5], dtype=np.float64)

    objp = _object_points()
    r_list = []
    t_list = []

    print(f"Press SPACE to capture; collect {N_CAPTURES} frames. ESC to abort.")
    captured = 0
    try:
        while captured < N_CAPTURES:
            frames = pipeline.wait_for_frames()
            color = frames.get_color_frame()
            if not color:
                continue
            img = np.asanyarray(color.get_data())
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            ok, corners = cv2.findChessboardCorners(
                gray, (CHECKER_COLS, CHECKER_ROWS), None
            )
            disp = img.copy()
            if ok:
                cv2.drawChessboardCorners(disp, (CHECKER_COLS, CHECKER_ROWS), corners, ok)
            cv2.imshow("calibration", disp)
            key = cv2.waitKey(1) & 0xFF
            if key == 27:
                print("aborted.")
                return pathlib.Path(out_path)
            if key == 32 and ok:
                cv2.cornerSubPix(
                    gray, corners, (11, 11), (-1, -1),
                    (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 1e-3),
                )
                _, rvec, tvec = cv2.solvePnP(objp, corners, K, dist)
                r_list.append(rvec.flatten())
                t_list.append(tvec.flatten())
                captured += 1
                print(f"captured {captured}/{N_CAPTURES}")
    finally:
        pipeline.stop()
        cv2.destroyAllWindows()

    # average pose (rotation avg via quat mean)
    import cv2 as _cv
    Rs = []
    for rv in r_list:
        R, _ = _cv.Rodrigues(rv)
        Rs.append(R)
    R_mean = _rotation_mean(Rs)
    t_mean = np.mean(np.stack(t_list), axis=0)

    # camera_to_board = [R_mean | t_mean]; array_to_camera requires
    # board_to_array = identity (by construction). So
    # array_from_camera = inv(camera_to_array) = inv(camera_to_board * board_to_array)
    # = inv(camera_to_board) = [R^T | -R^T t]
    camera_to_array = np.eye(4)
    camera_to_array[:3, :3] = R_mean
    camera_to_array[:3, 3] = t_mean
    array_from_camera = np.linalg.inv(camera_to_array)

    obj = {
        "camera_to_array": array_from_camera.tolist(),  # misnomer kept for API stability
        "notes": (
            "Maps camera-frame points to array-frame points. "
            "Built assuming checkerboard centre = array centre and "
            "checkerboard coplanar with array face."
        ),
    }
    p = pathlib.Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    print(f"wrote {p}")
    return p


def _rotation_mean(Rs: list) -> np.ndarray:
    # via SVD on summed rotations (Moakher 2002 simplification)
    M = np.sum(Rs, axis=0)
    U, _, Vt = np.linalg.svd(M)
    R = U @ Vt
    if np.linalg.det(R) < 0:
        U[:, -1] = -U[:, -1]
        R = U @ Vt
    return R


if __name__ == "__main__":
    try:
        run_calibration()
    except ImportError as e:
        print(f"[calibration] {e}", file=sys.stderr)
        sys.exit(1)
