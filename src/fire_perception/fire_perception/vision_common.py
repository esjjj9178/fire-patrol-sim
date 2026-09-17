"""역할: 비전 검출 공용 유틸 — 이미지 좌표 -> base_link 방위(bearing), depth -> 거리(range),
     TF 기반 map 좌표 추정. hsv_detector/yolo_detector/vision_node 가 공용으로 사용한다.
     좌표 규약: base_link/맵은 REP-103(x 전방, y 좌측, yaw CCW+). 카메라 optical frame 은
     z 전방, x 우측, y 하방이므로 이미지 우측(x_offset>0)은 CCW 규약에서 음의 각도가 된다.
"""
import math
from typing import Optional, Tuple

import numpy as np


def bbox_center(bbox: Tuple[int, int, int, int]) -> Tuple[float, float]:
    x1, y1, x2, y2 = bbox
    return (x1 + x2) / 2.0, (y1 + y2) / 2.0


def pixel_to_camera_angle(cx: float, image_width: int, hfov_rad: float) -> float:
    """이미지 중심 대비 픽셀 x오프셋을 카메라 광축 기준 수평각(CCW+)으로 변환."""
    f = (image_width / 2.0) / math.tan(hfov_rad / 2.0)
    x_offset = cx - image_width / 2.0
    return -math.atan2(x_offset, f)


def camera_angle_to_bearing(camera_angle: float, pan_angle: float) -> float:
    """카메라 광축 기준각 + 팬 조인트 각도 -> base_link 기준 방위(rad, CCW+, [-pi,pi])."""
    bearing = pan_angle + camera_angle
    return math.atan2(math.sin(bearing), math.cos(bearing))


def bbox_to_bearing(bbox, image_width: int, hfov_rad: float, pan_angle: float) -> float:
    cx, _ = bbox_center(bbox)
    cam_angle = pixel_to_camera_angle(cx, image_width, hfov_rad)
    return camera_angle_to_bearing(cam_angle, pan_angle)


def depth_bbox_range(depth_image: np.ndarray, bbox, margin_ratio: float = 0.25) -> Optional[float]:
    """bbox 중앙 영역(가장자리 margin_ratio 만큼 축소)의 depth[m] 중앙값.
    depth_image 는 32FC1(m) 가정, NaN/Inf/0 이하는 무효로 취급. 유효값 없으면 None.
    """
    x1, y1, x2, y2 = bbox
    w, h = x2 - x1, y2 - y1
    mx, my = int(w * margin_ratio), int(h * margin_ratio)
    x1c, x2c = x1 + mx, x2 - mx
    y1c, y2c = y1 + my, y2 - my
    if x2c <= x1c or y2c <= y1c:
        x1c, y1c, x2c, y2c = x1, y1, x2, y2
    region = depth_image[max(0, y1c):y2c, max(0, x1c):x2c]
    valid = region[np.isfinite(region) & (region > 0.0)]
    if valid.size == 0:
        return None
    return float(np.median(valid))


def yaw_from_quaternion(qx: float, qy: float, qz: float, qw: float) -> float:
    return math.atan2(2.0 * (qw * qz + qx * qy), 1.0 - 2.0 * (qy * qy + qz * qz))


def bearing_range_to_map(robot_x: float, robot_y: float, robot_yaw: float,
                          bearing_base_link: float, range_m: float) -> Tuple[float, float]:
    world_angle = robot_yaw + bearing_base_link
    return (robot_x + range_m * math.cos(world_angle),
            robot_y + range_m * math.sin(world_angle))
