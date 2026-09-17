#!/usr/bin/env python3
"""fire_world/config/warehouse_layout.yaml 하나로 Gazebo Harmonic SDF 월드와
Nav2 맵(pgm/yaml)을 동시에 생성한다. 두 산출물은 같은 좌표 계산에서 나오므로
맵과 월드가 항상 일치한다.

사용:
  generate_world.py                # sdf + map 생성
  generate_world.py --check        # 생성 없이 레이아웃 검증만 (겹침/통로폭/웨이포인트/hidden_fire 시야)
  generate_world.py --layout PATH  # 레이아웃 yaml 경로 지정 (기본: config/warehouse_layout.yaml)
"""
import argparse
import math
import sys
from pathlib import Path

import yaml

PKG_DIR = Path(__file__).resolve().parent.parent
DEFAULT_LAYOUT = PKG_DIR / "config" / "warehouse_layout.yaml"
DEFAULT_WORLD_OUT = PKG_DIR / "worlds" / "warehouse.sdf"
DEFAULT_MAP_DIR = PKG_DIR / "maps"

WAYPOINT_MARGIN_M = 0.4          # 웨이포인트-장애물/점유칸 최소 거리
MIN_AISLE_WIDTH_M = 1.8          # 통로 최소 폭
MIN_BOX_HEIGHT_M = 0.3           # 라이다(0.17m)에 보이려면 필요한 최소 높이
HIDDEN_FIRE_GAS_RANGE_M = 2.0    # hidden_fire 가 가스로 감지되려면 경로와 이만큼은 가까워야 함
FOV_HALF_DEG = 90.0              # 진행방향 기준 ±90도 안에서 시야 판정


# ---------------------------------------------------------------------------
# 기하 유틸
# ---------------------------------------------------------------------------
def rect_corners(x, y, yaw, l, w):
    """중심(x,y), 회전 yaw, x방향 길이 l, y방향 길이 w 인 사각형의 4꼭짓점."""
    hl, hw = l / 2.0, w / 2.0
    local = [(hl, hw), (hl, -hw), (-hl, -hw), (-hl, hw)]
    c, s = math.cos(yaw), math.sin(yaw)
    return [(x + lx * c - ly * s, y + lx * s + ly * c) for lx, ly in local]


def _axes(corners):
    axes = []
    n = len(corners)
    for i in range(n):
        x1, y1 = corners[i]
        x2, y2 = corners[(i + 1) % n]
        edge = (x2 - x1, y2 - y1)
        axes.append((-edge[1], edge[0]))
    return axes


def _project(corners, axis):
    dots = [c[0] * axis[0] + c[1] * axis[1] for c in corners]
    return min(dots), max(dots)


def rects_overlap(cornersA, cornersB):
    """SAT 로 두 사각형(회전 포함) 겹침 판정."""
    for axis in _axes(cornersA) + _axes(cornersB):
        norm = math.hypot(*axis)
        if norm < 1e-9:
            continue
        axis = (axis[0] / norm, axis[1] / norm)
        minA, maxA = _project(cornersA, axis)
        minB, maxB = _project(cornersB, axis)
        if maxA < minB or maxB < minA:
            return False
    return True


def point_rect_distance(px, py, corners):
    """점과 사각형(폴리곤) 최소 거리. 내부면 0."""
    n = len(corners)
    # 내부 판정 (모든 변에 대해 같은 쪽에 있는지, convex 가정)
    inside = True
    for i in range(n):
        x1, y1 = corners[i]
        x2, y2 = corners[(i + 1) % n]
        cross = (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)
        if cross > 1e-9:
            inside = False
            break
    if inside:
        return 0.0
    best = float("inf")
    for i in range(n):
        x1, y1 = corners[i]
        x2, y2 = corners[(i + 1) % n]
        best = min(best, _point_seg_dist(px, py, x1, y1, x2, y2))
    return best


def _point_seg_dist(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)
    t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    cx, cy = x1 + t * dx, y1 + t * dy
    return math.hypot(px - cx, py - cy)


def seg_intersects_seg(p1, p2, p3, p4):
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    d1 = cross(p3, p4, p1)
    d2 = cross(p3, p4, p2)
    d3 = cross(p1, p2, p3)
    d4 = cross(p1, p2, p4)
    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and \
       ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
        return True
    return False


def seg_intersects_rect(p1, p2, corners):
    n = len(corners)
    # 두 끝점 중 하나라도 사각형 내부면 교차로 취급
    if point_rect_distance(*p1, corners) < 1e-9 or point_rect_distance(*p2, corners) < 1e-9:
        return True
    for i in range(n):
        if seg_intersects_seg(p1, p2, corners[i], corners[(i + 1) % n]):
            return True
    return False


# ---------------------------------------------------------------------------
# 레이아웃 로딩
# ---------------------------------------------------------------------------
def load_layout(path):
    with open(path, "r", encoding="utf-8") as f:
        layout = yaml.safe_load(f)
    return layout


def element_corners(elem):
    p = elem["pose"]
    s = elem["size"]
    return rect_corners(p["x"], p["y"], p.get("yaw", 0.0), s["l"], s["w"])


# ---------------------------------------------------------------------------
# SDF 생성 (Gazebo Harmonic 문법: gz-sim-*-system / gz::sim::systems::*)
# ---------------------------------------------------------------------------
SDF_HEADER = """<?xml version="1.0" ?>
<sdf version="1.9">
  <world name="{name}">
    <physics name="default_physics" type="ignored">
      <max_step_size>0.001</max_step_size>
      <real_time_factor>1.0</real_time_factor>
    </physics>
    <plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/>
    <plugin filename="gz-sim-sensors-system" name="gz::sim::systems::Sensors">
      <render_engine>ogre2</render_engine>
    </plugin>
    <plugin filename="gz-sim-scene-broadcaster-system" name="gz::sim::systems::SceneBroadcaster"/>
    <plugin filename="gz-sim-user-commands-system" name="gz::sim::systems::UserCommands"/>
    <plugin filename="gz-sim-imu-system" name="gz::sim::systems::Imu"/>

    <light type="directional" name="sun">
      <cast_shadows>true</cast_shadows>
      <pose>0 0 10 0 0 0</pose>
      <diffuse>0.8 0.8 0.8 1</diffuse>
      <specular>0.2 0.2 0.2 1</specular>
      <attenuation>
        <range>1000</range>
        <constant>0.9</constant>
        <linear>0.01</linear>
        <quadratic>0.001</quadratic>
      </attenuation>
      <direction>-0.5 0.1 -0.9</direction>
    </light>

    <model name="ground_plane">
      <static>true</static>
      <link name="link">
        <collision name="collision">
          <geometry><plane><normal>0 0 1</normal><size>{gx} {gy}</size></plane></geometry>
        </collision>
        <visual name="visual">
          <geometry><plane><normal>0 0 1</normal><size>{gx} {gy}</size></plane></geometry>
          <material>
            <ambient>0.5 0.5 0.5 1</ambient>
            <diffuse>0.5 0.5 0.5 1</diffuse>
          </material>
        </visual>
      </link>
    </model>
"""

BOX_MODEL_TEMPLATE = """
    <model name="{name}">
      <static>true</static>
      <pose>{x} {y} {z} 0 0 {yaw}</pose>
      <link name="link">
        <collision name="collision">
          <geometry><box><size>{l} {w} {h}</size></box></geometry>
        </collision>
        <visual name="visual">
          <geometry><box><size>{l} {w} {h}</size></box></geometry>
          <material>
            <ambient>{r} {g} {b} 1</ambient>
            <diffuse>{r} {g} {b} 1</diffuse>
          </material>
{thermal_plugin}
        </visual>
      </link>
    </model>
"""

THERMAL_PLUGIN_TEMPLATE = """          <plugin filename="gz-sim-thermal-system" name="gz::sim::systems::Thermal">
            <temperature>{temp}</temperature>
          </plugin>
"""

AMBIENT_THERMAL_TEMPLATE = """    <model name="ambient_floor">
      <static>true</static>
      <pose>0 0 0.005 0 0 0</pose>
      <link name="link">
        <visual name="visual">
          <geometry><box><size>{gx} {gy} 0.01</size></box></geometry>
          <material><ambient>0.4 0.4 0.4 1</ambient><diffuse>0.4 0.4 0.4 1</diffuse></material>
          <plugin filename="gz-sim-thermal-system" name="gz::sim::systems::Thermal">
            <temperature>293.0</temperature>
          </plugin>
        </visual>
      </link>
    </model>
"""


def build_sdf(layout):
    w = layout["world"]
    gx, gy = w["size"]["x"] + 2.0, w["size"]["y"] + 2.0
    parts = [SDF_HEADER.format(name=w["name"], gx=gx, gy=gy)]
    parts.append(AMBIENT_THERMAL_TEMPLATE.format(gx=gx, gy=gy))

    for elem in layout["elements"]:
        s = elem["size"]
        p = elem["pose"]
        color = elem.get("color", [0.6, 0.6, 0.6])
        thermal = ""
        if elem["type"] == "fire":
            thermal = THERMAL_PLUGIN_TEMPLATE.format(temp=elem["temperature_k"])
        parts.append(BOX_MODEL_TEMPLATE.format(
            name=elem["name"], x=p["x"], y=p["y"], z=s["h"] / 2.0, yaw=p.get("yaw", 0.0),
            l=s["l"], w=s["w"], h=s["h"], r=color[0], g=color[1], b=color[2],
            thermal_plugin=thermal,
        ))

    parts.append("  </world>\n</sdf>\n")
    return "".join(parts)


# ---------------------------------------------------------------------------
# 맵(pgm/yaml) 생성 — SDF 와 동일한 yaml 좌표에서 직접 계산 (Gazebo 실행 불필요)
# ---------------------------------------------------------------------------
def build_map(layout):
    import numpy as np

    w = layout["world"]
    res = layout["map"]["resolution"]
    size_x, size_y = w["size"]["x"], w["size"]["y"]
    width = int(round(size_x / res))
    height = int(round(size_y / res))
    origin_x, origin_y = -size_x / 2.0, -size_y / 2.0

    occupied_rects = [element_corners(e) for e in layout["elements"] if e.get("in_map")]

    grid = np.full((height, width), 254, dtype=np.uint8)  # 254=free
    for r in range(height):
        wy = origin_y + (height - 1 - r + 0.5) * res
        for c in range(width):
            wx = origin_x + (c + 0.5) * res
            for corners in occupied_rects:
                if point_rect_distance(wx, wy, corners) < 1e-9:
                    grid[r, c] = 0  # occupied
                    break

    return grid, res, origin_x, origin_y, width, height


def write_pgm(path, grid):
    height, width = grid.shape
    with open(path, "wb") as f:
        f.write(f"P5\n{width} {height}\n255\n".encode("ascii"))
        f.write(grid.tobytes())


def write_map_yaml(path, pgm_name, res, origin_x, origin_y):
    content = (
        f"image: {pgm_name}\n"
        f"resolution: {res}\n"
        f"origin: [{origin_x}, {origin_y}, 0.0]\n"
        "negate: 0\n"
        "occupied_thresh: 0.65\n"
        "free_thresh: 0.196\n"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# ---------------------------------------------------------------------------
# --check 검증
# ---------------------------------------------------------------------------
def check_layout(layout):
    ok = True
    rows = []

    elements = layout["elements"]
    by_name = {e["name"]: e for e in elements}
    corners_by_name = {e["name"]: element_corners(e) for e in elements}
    waypoints = layout["waypoints"]

    # 1) 요소 겹침 (in_map 요소끼리, 그리고 obstacle/fire 가 in_map 요소와 겹치면 안 됨)
    names = list(by_name.keys())
    overlap_bad = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = by_name[names[i]], by_name[names[j]]
            if rects_overlap(corners_by_name[names[i]], corners_by_name[names[j]]):
                # 벽끼리 모서리에서 맞닿는 것은 의도된 것이므로, 실제 침투(면적 큰 겹침)만 문제 삼음.
                if not (a["type"] == "wall" and b["type"] == "wall"):
                    overlap_bad.append((names[i], names[j]))
    ok_overlap = len(overlap_bad) == 0
    rows.append(("요소 겹침 (벽 제외)", "PASS" if ok_overlap else f"FAIL: {overlap_bad}"))
    ok &= ok_overlap

    # 2) 박스 높이 >= 0.3m (obstacle, fire)
    bad_height = [e["name"] for e in elements if e["type"] in ("obstacle", "fire") and e["size"]["h"] < MIN_BOX_HEIGHT_M]
    ok_height = len(bad_height) == 0
    rows.append((f"박스 높이 >= {MIN_BOX_HEIGHT_M}m", "PASS" if ok_height else f"FAIL: {bad_height}"))
    ok &= ok_height

    # 3) 웨이포인트 - 장애물/불 거리 >= 0.4m
    bad_wp = []
    dyn_elems = [e for e in elements if e["type"] in ("obstacle", "fire")]
    for wp in waypoints:
        for e in dyn_elems:
            d = point_rect_distance(wp["x"], wp["y"], corners_by_name[e["name"]])
            if d < WAYPOINT_MARGIN_M:
                bad_wp.append((wp["name"], e["name"], round(d, 3)))
    ok_wp = len(bad_wp) == 0
    rows.append((f"웨이포인트-장애물/불 거리 >= {WAYPOINT_MARGIN_M}m", "PASS" if ok_wp else f"FAIL: {bad_wp}"))
    ok &= ok_wp

    # 3b) 웨이포인트가 점유 셀(벽/선반) 내부에 있지 않은지
    bad_wp_occ = []
    occ_elems = [e for e in elements if e.get("in_map")]
    for wp in waypoints:
        for e in occ_elems:
            if point_rect_distance(wp["x"], wp["y"], corners_by_name[e["name"]]) < 1e-9:
                bad_wp_occ.append((wp["name"], e["name"]))
    ok_wp_occ = len(bad_wp_occ) == 0
    rows.append(("웨이포인트가 점유칸(벽/선반) 밖에 있는지", "PASS" if ok_wp_occ else f"FAIL: {bad_wp_occ}"))
    ok &= ok_wp_occ

    # 4) 통로 폭 >= 1.8m — 선반이 걸쳐 있는 x 구간을 촘촘히 샘플링해 각 컬럼의 자유 구간(run) 최소 길이를 구함
    shelves = [e for e in elements if e["type"] == "shelf"]
    if shelves:
        xs = [e["pose"]["x"] for e in shelves]
        ls = [e["size"]["l"] for e in shelves]
        x_min = min(x - l / 2.0 for x, l in zip(xs, ls))
        x_max = max(x + l / 2.0 for x, l in zip(xs, ls))
    else:
        x_min, x_max = -1.0, 1.0
    occ_corners = [corners_by_name[e["name"]] for e in occ_elems]
    size_y = layout["world"]["size"]["y"]
    step_y = 0.02
    min_run = float("inf")
    min_run_x = None
    x = x_min
    while x <= x_max:
        occupied_ys = []
        y = -size_y
        while y <= size_y:
            occ = any(point_rect_distance(x, y, c) < 1e-9 for c in occ_corners)
            occupied_ys.append((y, occ))
            y += step_y
        # run 길이 계산 (occ=False 구간)
        run_start = None
        for y_val, occ in occupied_ys:
            if not occ and run_start is None:
                run_start = y_val
            elif occ and run_start is not None:
                run_len = y_val - run_start
                if run_len < min_run:
                    min_run, min_run_x = run_len, x
                run_start = None
        x += 0.2
    ok_aisle = min_run >= MIN_AISLE_WIDTH_M
    rows.append((f"통로 폭 >= {MIN_AISLE_WIDTH_M}m (최소값)",
                 f"PASS ({min_run:.2f}m @ x={min_run_x})" if ok_aisle else f"FAIL ({min_run:.2f}m @ x={min_run_x})"))
    ok &= ok_aisle

    # 5) hidden_fire 시야 규칙
    hidden = by_name.get("hidden_fire")
    if hidden is not None:
        fx, fy = hidden["pose"]["x"], hidden["pose"]["y"]
        blocking_corners = [corners_by_name[e["name"]] for e in elements if e["type"] in ("shelf", "wall")]
        path = [(p["x"], p["y"]) for p in waypoints] + [(waypoints[0]["x"], waypoints[0]["y"])]

        min_dist = float("inf")
        any_blocked_in_cone = False
        any_visible_in_cone = False
        step = 0.1
        for i in range(len(path) - 1):
            x1, y1 = path[i]
            x2, y2 = path[i + 1]
            seg_len = math.hypot(x2 - x1, y2 - y1)
            if seg_len < 1e-6:
                continue
            dirx, diry = (x2 - x1) / seg_len, (y2 - y1) / seg_len
            n_steps = max(1, int(seg_len / step))
            for k in range(n_steps + 1):
                t = k / n_steps
                px, py = x1 + t * (x2 - x1), y1 + t * (y2 - y1)
                d = math.hypot(fx - px, fy - py)
                min_dist = min(min_dist, d)
                bear_x, bear_y = fx - px, fy - py
                bear_len = math.hypot(bear_x, bear_y)
                if bear_len < 1e-6:
                    continue
                cos_ang = (dirx * bear_x + diry * bear_y) / bear_len
                ang_deg = math.degrees(math.acos(max(-1.0, min(1.0, cos_ang))))
                if ang_deg > FOV_HALF_DEG:
                    continue  # 진행방향 ±90도 밖 → 스윕 카메라 시야 밖으로 취급
                blocked = any(seg_intersects_rect((px, py), (fx, fy), c) for c in blocking_corners)
                if blocked:
                    any_blocked_in_cone = True
                else:
                    any_visible_in_cone = True

        ok_dist = min_dist <= HIDDEN_FIRE_GAS_RANGE_M
        ok_blocked = any_blocked_in_cone
        ok_visible = any_visible_in_cone
        rows.append((f"hidden_fire 경로 최근접 거리 <= {HIDDEN_FIRE_GAS_RANGE_M}m",
                     f"PASS ({min_dist:.2f}m)" if ok_dist else f"FAIL ({min_dist:.2f}m)"))
        rows.append(("hidden_fire: 시야 가려지는 구간 존재", "PASS" if ok_blocked else "FAIL"))
        rows.append(("hidden_fire: 모퉁이를 돈 뒤 시야가 열리는 구간 존재", "PASS" if ok_visible else "FAIL"))
        ok &= ok_dist and ok_blocked and ok_visible
    else:
        rows.append(("hidden_fire 존재", "FAIL: layout 에 hidden_fire 없음"))
        ok = False

    print("\n=== generate_world.py --check 결과 ===")
    name_w = max(len(r[0]) for r in rows) + 2
    for name, result in rows:
        print(f"  {name.ljust(name_w)}{result}")
    print(f"\n총평: {'ALL PASS' if ok else 'FAIL 있음'}")
    return ok


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--layout", default=str(DEFAULT_LAYOUT))
    ap.add_argument("--check", action="store_true", help="검증만 하고 파일은 쓰지 않음")
    ap.add_argument("--world-out", default=str(DEFAULT_WORLD_OUT))
    ap.add_argument("--map-dir", default=str(DEFAULT_MAP_DIR))
    args = ap.parse_args()

    layout = load_layout(args.layout)
    ok = check_layout(layout)

    if args.check:
        sys.exit(0 if ok else 1)

    if not ok:
        print("\n레이아웃 검증 실패 → 월드/맵 생성을 중단합니다. (--check 로 상세 확인)", file=sys.stderr)
        sys.exit(1)

    world_out = Path(args.world_out)
    world_out.parent.mkdir(parents=True, exist_ok=True)
    world_out.write_text(build_sdf(layout), encoding="utf-8")
    print(f"\n월드 생성: {world_out}")

    map_dir = Path(args.map_dir)
    map_dir.mkdir(parents=True, exist_ok=True)
    grid, res, origin_x, origin_y, width, height = build_map(layout)
    write_pgm(map_dir / "warehouse.pgm", grid)
    write_map_yaml(map_dir / "warehouse.yaml", "warehouse.pgm", res, origin_x, origin_y)
    print(f"맵 생성: {map_dir / 'warehouse.pgm'} ({width}x{height}px, {res}m/px, origin=({origin_x},{origin_y}))")

    sys.exit(0)


if __name__ == "__main__":
    main()
