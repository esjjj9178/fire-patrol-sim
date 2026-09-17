"""역할: 2D 가시선(line-of-sight) 판정 공용 유틸 — virtual_thermal_node 가 선반/벽에
     가려진 불을 "안 보이게" 처리하는 데 사용한다. warehouse_layout.yaml 의 wall/shelf
     요소(축 정렬 아닌 임의 yaw 지원)를 회전 사각형으로 취급해 로봇-불 선분과의 교차를 검사한다.
     fire_world/scripts/generate_world.py 의 동일 로직(rect_corners/seg_intersects_rect)을
     fire_perception 패키지(ament_python)에서도 쓸 수 있도록 독립적으로 재구현한 것이다.
"""
import math
from typing import List, Sequence, Tuple

Point2 = Tuple[float, float]


def rect_corners(x: float, y: float, yaw: float, l: float, w: float) -> List[Point2]:
    hl, hw = l / 2.0, w / 2.0
    local = [(hl, hw), (hl, -hw), (-hl, -hw), (-hl, hw)]
    c, s = math.cos(yaw), math.sin(yaw)
    return [(x + lx * c - ly * s, y + lx * s + ly * c) for lx, ly in local]


def _cross(o: Point2, a: Point2, b: Point2) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def seg_intersects_seg(p1: Point2, p2: Point2, p3: Point2, p4: Point2) -> bool:
    d1 = _cross(p3, p4, p1)
    d2 = _cross(p3, p4, p2)
    d3 = _cross(p1, p2, p3)
    d4 = _cross(p1, p2, p4)
    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and \
       ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
        return True
    return False


def seg_intersects_rect(p1: Point2, p2: Point2, corners: Sequence[Point2]) -> bool:
    n = len(corners)
    for i in range(n):
        if seg_intersects_seg(p1, p2, corners[i], corners[(i + 1) % n]):
            return True
    # 선분 양 끝점이 사각형 내부에 있는 경우(완전히 관통하지 않고 시작/끝이 내부)도 차단으로 취급
    for p in (p1, p2):
        if _point_in_rect(p, corners):
            return True
    return False


def _point_in_rect(p: Point2, corners: Sequence[Point2]) -> bool:
    # 볼록 사각형 내부 판정: 모든 변에 대해 같은 방향(부호)이면 내부
    n = len(corners)
    sign = None
    for i in range(n):
        a, b = corners[i], corners[(i + 1) % n]
        cr = _cross(a, b, p)
        if abs(cr) < 1e-9:
            continue
        s = cr > 0
        if sign is None:
            sign = s
        elif s != sign:
            return False
    return True


def has_line_of_sight(robot_xy: Point2, target_xy: Point2, occluders: Sequence[dict]) -> bool:
    """occluders: [{'x','y','yaw','l','w'}, ...] (wall/shelf 등 가림막 요소).
    하나라도 선분을 막으면 False."""
    for occ in occluders:
        corners = rect_corners(occ['x'], occ['y'], occ.get('yaw', 0.0), occ['l'], occ['w'])
        if seg_intersects_rect(robot_xy, target_xy, corners):
            return False
    return True
