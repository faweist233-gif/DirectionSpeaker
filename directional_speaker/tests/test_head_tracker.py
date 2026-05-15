"""Virtual tracker geometry + bad-angle guard."""
from __future__ import annotations

import numpy as np
import pytest

from directional_speaker import config as cfg
from directional_speaker.head_tracker import VirtualTracker, make_tracker


@pytest.mark.parametrize("angle", [-60, 0, 60])
def test_virtual_allowed_angles(angle):
    t = VirtualTracker(angle)
    pose = t.get_ear_pose()
    # theta_L < theta_R (left ear to the left of right ear in x)
    assert pose.theta_L_deg < pose.theta_R_deg + 1e-6
    # distances reasonable
    assert 0.5 < pose.d_L_m < 2.0
    assert 0.5 < pose.d_R_m < 2.0
    # delta_theta should be small positive
    assert 0 < pose.delta_theta_L_deg < 20
    assert 0 < pose.delta_theta_R_deg < 20


def test_virtual_invalid_angle_raises():
    with pytest.raises(ValueError):
        VirtualTracker(45)


def test_virtual_center_angle_symmetric():
    t = VirtualTracker(0)
    p = t.get_ear_pose()
    # symmetric: theta_L == -theta_R, d_L == d_R
    assert abs(p.theta_L_deg + p.theta_R_deg) < 1e-3
    assert abs(p.d_L_m - p.d_R_m) < 1e-6


def test_virtual_distance_scales():
    p1 = VirtualTracker(0, distance_m=1.0).get_ear_pose()
    p2 = VirtualTracker(0, distance_m=2.0).get_ear_pose()
    assert 1.9 < p2.d_L_m / p1.d_L_m < 2.1
    # larger distance -> smaller ear-opening angle
    assert p2.delta_theta_L_deg < p1.delta_theta_L_deg


def test_make_tracker_dispatch():
    t = make_tracker("virtual", 0, 1.0)
    assert isinstance(t, VirtualTracker)
    with pytest.raises(ValueError):
        make_tracker("bad")


def test_delta_theta_formula():
    """Delta_theta = 2*atan(W_ear/2 / d)."""
    t = VirtualTracker(0, distance_m=0.3)
    p = t.get_ear_pose()
    expected = np.rad2deg(2 * np.arctan2(cfg.W_EAR_M / 2, p.d_L_m))
    assert abs(p.delta_theta_L_deg - expected) < 1e-6
