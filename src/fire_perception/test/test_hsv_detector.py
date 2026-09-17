"""HsvDetector/vision_common 을 합성 이미지(numpy)로 검증한다(ROS/시뮬 불필요)."""
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fire_perception.hsv_detector import HsvDetector  # noqa: E402
from fire_perception.vision_common import (bbox_to_bearing, bearing_range_to_map,  # noqa: E402
                                            depth_bbox_range, yaw_from_quaternion)


def _red_box_image(w=320, h=240, box=(120, 90, 200, 170)):
    img = np.full((h, w, 3), (40, 40, 40), dtype=np.uint8)  # BGR 회색 배경
    x1, y1, x2, y2 = box
    img[y1:y2, x1:x2] = (0, 0, 255)  # BGR 빨강
    return img


def test_hsv_detector_finds_red_box():
    detector = HsvDetector()
    img = _red_box_image()
    detections = detector.detect(img)
    assert len(detections) == 1
    (x1, y1, x2, y2), conf = detections[0]
    assert abs((x1 + x2) / 2 - 160) < 10
    assert abs((y1 + y2) / 2 - 130) < 10
    assert conf > 0.5


def test_hsv_detector_no_false_positive_on_gray():
    detector = HsvDetector()
    img = np.full((240, 320, 3), (40, 40, 40), dtype=np.uint8)
    assert detector.detect(img) == []


def test_bbox_to_bearing_center_is_zero():
    # 이미지 중심의 bbox -> 카메라 광축과 일치 -> bearing == pan_angle
    bbox = (150, 100, 170, 140)
    bearing = bbox_to_bearing(bbox, image_width=320, hfov_rad=1.204, pan_angle=0.3)
    assert abs(bearing - 0.3) < 1e-3


def test_bbox_to_bearing_right_side_is_negative_ccw():
    # 이미지 우측 bbox -> base_link 기준 CCW 규약에서 음의 방향
    bbox = (280, 100, 310, 140)
    bearing = bbox_to_bearing(bbox, image_width=320, hfov_rad=1.204, pan_angle=0.0)
    assert bearing < 0.0


def test_depth_bbox_range_median():
    depth = np.full((240, 320), 5.0, dtype=np.float32)
    depth[95:135, 145:175] = 2.0
    depth[0:10, 0:10] = float('nan')
    r = depth_bbox_range(depth, (140, 90, 180, 140))
    assert abs(r - 2.0) < 1e-3


def test_depth_bbox_range_all_invalid_returns_none():
    depth = np.full((10, 10), float('nan'), dtype=np.float32)
    assert depth_bbox_range(depth, (0, 0, 10, 10)) is None


def test_yaw_from_quaternion_identity():
    assert abs(yaw_from_quaternion(0, 0, 0, 1)) < 1e-9


def test_yaw_from_quaternion_90deg():
    yaw = math.pi / 2
    qz, qw = math.sin(yaw / 2), math.cos(yaw / 2)
    assert abs(yaw_from_quaternion(0, 0, qz, qw) - yaw) < 1e-6


def test_bearing_range_to_map_forward():
    x, y = bearing_range_to_map(1.0, 2.0, robot_yaw=0.0, bearing_base_link=0.0, range_m=3.0)
    assert abs(x - 4.0) < 1e-6
    assert abs(y - 2.0) < 1e-6
