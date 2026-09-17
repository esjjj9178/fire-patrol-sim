#!/usr/bin/env python3
"""역할: 통합 시나리오(real/fake/hidden fire) 검증용 기록기(STEP7).
     /fire/event(JSON)와 /ground_truth/pose(SIM ONLY)를 기록해, 순찰 중 발생한 이벤트
     시퀀스와 화재 위치 추정 오차(정답: fire_world/config/warehouse_layout.yaml)를
     data/reports/report_<시간>.md 로 저장한다.

**작성만 함 — /build-all 페이즈에서는 실행하지 않는다(시뮬 필요, /check 7 에서 사용자가 실행).**

사용법(예시, full_demo.launch.py 가 이미 떠 있는 상태에서 별도 터미널):
  source ~/fire_ws/scripts/env.sh
  python3 ~/fire_ws/install/fire_bringup/share/fire_bringup/scripts/scenario_report.py --duration 600

옵션:
  --duration SEC   기록 시간(기본 600초, Ctrl+C 로도 조기 종료 가능 — 그때까지 기록분으로 저장)
  --output PATH    출력 파일(기본 data/reports/report_<타임스탬프>.md, 워크스페이스 루트 기준)
"""
import argparse
import math
import time
from datetime import datetime
from pathlib import Path

import rclpy
import yaml
from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import PoseStamped
from rclpy.node import Node
from std_msgs.msg import String


def _layout_path() -> Path:
    try:
        return Path(get_package_share_directory('fire_world')) / 'config' / 'warehouse_layout.yaml'
    except Exception:
        return Path(__file__).resolve().parents[5] / 'fire_world' / 'config' / 'warehouse_layout.yaml'


def _ground_truth_fires() -> dict:
    with open(_layout_path()) as f:
        layout = yaml.safe_load(f)
    return {e['name']: e for e in layout.get('elements', []) if e.get('type') == 'fire'}


def _workspace_root() -> Path:
    # scenario_report.py 는 install/fire_bringup/share/fire_bringup/scripts/ 아래 설치되므로
    # 워크스페이스 루트(~/fire_ws)를 소스 트리 기준으로 역추적한다. 실패하면 cwd 사용.
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / 'src').is_dir() and (parent / 'scripts' / 'env.sh').exists():
            return parent
    return Path.cwd()


class ScenarioRecorder(Node):

    def __init__(self):
        super().__init__('scenario_report_recorder')
        self._events = []  # (ros_time_sec, event_dict)
        self._latest_gt_pose = None
        self._start_time = time.time()

        self.create_subscription(String, '/fire/event', self._on_event, 20)
        self.create_subscription(PoseStamped, '/ground_truth/pose', self._on_gt_pose, 20)
        self.get_logger().info('scenario_report_recorder 시작 - /fire/event, /ground_truth/pose 기록 중')

    def _on_event(self, msg: String):
        import json
        try:
            payload = json.loads(msg.data)
        except ValueError:
            return
        payload['_recv_wall_time'] = time.time()
        self._events.append(payload)
        self.get_logger().info(f"event: {payload.get('event')} @ {payload.get('position')}")

    def _on_gt_pose(self, msg: PoseStamped):
        self._latest_gt_pose = (msg.pose.position.x, msg.pose.position.y)


def _closest_gt_fire(pos, gt_fires: dict):
    best_name, best_d = None, float('inf')
    for name, fire in gt_fires.items():
        fx, fy = fire['pose']['x'], fire['pose']['y']
        d = math.hypot(pos['x'] - fx, pos['y'] - fy)
        if d < best_d:
            best_name, best_d = name, d
    return best_name, best_d


def _build_report(events: list, gt_fires: dict, duration_s: float) -> str:
    lines = ['# 통합 시나리오 리포트', '',
             f'생성 시각: {datetime.now().isoformat()}',
             f'기록 시간: {duration_s:.0f}s',
             f'기록된 이벤트 수: {len(events)}', '']

    lines.append('## 정답 화재 위치')
    lines.append('| 이름 | x | y | is_real | temperature_k |')
    lines.append('|---|---|---|---|---|')
    for name, fire in gt_fires.items():
        p = fire['pose']
        lines.append(f"| {name} | {p['x']:.2f} | {p['y']:.2f} | "
                      f"{fire.get('is_real')} | {fire.get('temperature_k')} |")
    lines.append('')

    lines.append('## 시나리오별 결과 (CONFIRMED/FALSE_ALARM 이벤트 기준)')
    lines.append('| 이름 | 판정 | 위치 오차(m) | 판정까지 걸린 시간 | reason |')
    lines.append('|---|---|---|---|---|')
    t0 = events[0]['_recv_wall_time'] if events else 0.0
    seen = set()
    for ev in events:
        if ev.get('event') not in ('FIRE_CONFIRMED', 'FALSE_ALARM'):
            continue
        pos = ev.get('position', {'x': 0.0, 'y': 0.0})
        name, err = _closest_gt_fire(pos, gt_fires)
        if name in seen:
            continue
        seen.add(name)
        elapsed = ev['_recv_wall_time'] - t0
        lines.append(f"| {name} | {ev['event']} | {err:.2f} | {elapsed:.1f}s | "
                      f"{ev.get('reason', '')} |")
    missing = set(gt_fires) - seen
    if missing:
        lines.append('')
        lines.append(f"판정 이벤트를 못 받은 화재: {', '.join(sorted(missing))} "
                      "(순찰 루프가 짧게 끝났거나 아직 지나가지 않았을 수 있음)")
    lines.append('')

    lines.append('## 전체 이벤트 로그')
    lines.append('| stamp | event | fire_state | mission_state | position |')
    lines.append('|---|---|---|---|---|')
    for ev in events:
        pos = ev.get('position', {})
        lines.append(f"| {ev.get('stamp')} | {ev.get('event')} | {ev.get('fire_state')} | "
                      f"{ev.get('mission_state')} | ({pos.get('x', 0):.2f}, {pos.get('y', 0):.2f}) |")
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duration', type=float, default=600.0)
    parser.add_argument('--output', type=str, default=None)
    args = parser.parse_args()

    rclpy.init()
    node = ScenarioRecorder()

    start = time.time()
    try:
        while rclpy.ok() and (time.time() - start) < args.duration:
            rclpy.spin_once(node, timeout_sec=0.5)
    except KeyboardInterrupt:
        pass

    duration_s = time.time() - start
    gt_fires = _ground_truth_fires()
    report = _build_report(node._events, gt_fires, duration_s)

    if args.output:
        out_path = Path(args.output)
    else:
        out_dir = _workspace_root() / 'data' / 'reports'
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report)
    print(f'리포트 저장: {out_path}')

    node.destroy_node()
    rclpy.try_shutdown()


if __name__ == '__main__':
    main()
