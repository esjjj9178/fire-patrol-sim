#!/usr/bin/env python3
"""역할(SIM ONLY 검증 도구): STEP5.md의 "기대 결과 표"를 재현한다. Gazebo 의 world
     set_pose 서비스로 로봇을 각 불(real/fake/hidden) 근처 + "불 없는 곳"으로 순간이동시키고
     팬을 불 방향으로 맞춘 뒤 3초간 vision/thermal/gas 점수 평균을 표로 출력한다.
     **/check 5 에서 sim(+perception) 이 이미 떠 있는 상태에서 사용자가 직접 실행**
     (/build-all 구현 단계에서는 실행하지 않음).

사용:
  # 터미널: sim.launch.py + perception.launch.py(+ thermal/gas) 실행 중인 상태에서
  ros2 run fire_perception sensor_scenario_test

텔레포트는 `gz service` CLI 로 gz-transport `/world/<world>/set_pose`(gz.msgs.Pose ->
gz.msgs.Boolean, world SDF 의 gz-sim-user-commands-system 플러그인이 제공)를 직접 호출한다.
원래는 ros_gz_bridge 로 ros_gz_interfaces/srv/SetEntityPose 를 브리지해서 썼는데, 이 PC의
ros_gz_bridge(Humble) 라이브러리에는 SetEntityPose 용 ServiceFactory 가 컴파일되어 있지 않아
(`strings libros_gz_bridge_lib.so` 로 확인 - ControlWorld 만 지원) 항상 "서비스를 찾을 수 없음"으로
실패했다(런타임 검증 중 발견).
"""
import argparse
import math
import subprocess
import time
from pathlib import Path

import rclpy
import yaml
from ament_index_python.packages import get_package_share_directory
from fire_interfaces.msg import FireDetection
from rclpy.node import Node
from std_msgs.msg import String


def _layout_path() -> Path:
    try:
        return Path(get_package_share_directory('fire_world')) / 'config' / 'warehouse_layout.yaml'
    except Exception:
        return (Path(__file__).resolve().parents[5] / 'fire_world' / 'config'
                / 'warehouse_layout.yaml')


def load_layout() -> dict:
    with open(_layout_path(), 'r') as f:
        return yaml.safe_load(f)


def build_scenarios(layout: dict):
    fires = {e['name']: e for e in layout['elements'] if e['type'] == 'fire'}
    scenarios = []
    for name in ('real_fire', 'fake_fire', 'hidden_fire'):
        fire = fires[name]
        fx, fy = fire['pose']['x'], fire['pose']['y']
        # 불에서 로봇 스폰쪽(-x)으로 2m 떨어진 지점, 불을 바라보는 yaw
        rx, ry = fx - 2.0, fy
        yaw = math.atan2(fy - ry, fx - rx)
        scenarios.append({'label': f'{name} 앞 2m', 'x': rx, 'y': ry, 'yaw': yaw})
    scenarios.append({'label': '불 없는 곳', 'x': layout['robot']['spawn']['x'],
                       'y': layout['robot']['spawn']['y'], 'yaw': 0.0})
    return scenarios


class ScenarioTestNode(Node):

    def __init__(self, robot_name: str, sample_s: float):
        super().__init__('sensor_scenario_test')
        self._sample_s = sample_s
        self._robot_name = robot_name
        self._world_name = load_layout()['world']['name']
        self._scores = {'vision': [], 'thermal': [], 'gas': []}

        self.create_subscription(FireDetection, '/fire/vision/detection',
                                  lambda m: self._on_det('vision', m), 10)
        self.create_subscription(FireDetection, '/fire/thermal/detection',
                                  lambda m: self._on_det('thermal', m), 10)
        self.create_subscription(FireDetection, '/fire/gas/detection',
                                  lambda m: self._on_det('gas', m), 10)

        self._pan_mode_pub = self.create_publisher(String, '/camera_pan/mode', 10)

    def _on_det(self, source: str, msg: FireDetection):
        self._scores[source].append(msg.confidence)

    def teleport(self, x: float, y: float, yaw: float) -> bool:
        qz, qw = math.sin(yaw / 2.0), math.cos(yaw / 2.0)
        req = (f'name: "{self._robot_name}" '
               f'position: {{x: {x} y: {y} z: 0.02}} '
               f'orientation: {{x: 0 y: 0 z: {qz} w: {qw}}}')
        try:
            result = subprocess.run(
                ['gz', 'service', '-s', f'/world/{self._world_name}/set_pose',
                 '--reqtype', 'gz.msgs.Pose', '--reptype', 'gz.msgs.Boolean',
                 '--timeout', '3000', '--req', req],
                capture_output=True, text=True, timeout=6.0, start_new_session=True)
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            self.get_logger().error(f'gz service set_pose 호출 실패: {exc}')
            return False
        ok = 'true' in result.stdout
        if not ok:
            self.get_logger().error(
                f'teleport 실패(stdout={result.stdout!r} stderr={result.stderr!r})')
        return ok

    def sample(self) -> dict:
        """SEARCH_360 으로 한 바퀴 훑으며 각 소스별 최댓값을 기록한다. approach_pose 로 로봇
        yaw 를 불 쪽으로 맞춰도 카메라가 실제로 불을 보려면 팬이 base_link 정면(bearing 0)이
        아니라 상당히 돌아가야 함이 실측으로 확인되어(마운트 경유 각도 차이), 고정 bearing 대신
        전체를 훑어 최댓값을 취하는 방식이 더 견고하다."""
        for key in self._scores:
            self._scores[key].clear()
        self._pan_mode_pub.publish(String(data='SEARCH_360'))
        end = time.time() + self._sample_s
        while time.time() < end:
            rclpy.spin_once(self, timeout_sec=0.1)
        return {k: (max(v) if v else float('nan')) for k, v in self._scores.items()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--robot-name', default='fire_bot')
    parser.add_argument('--sample-s', type=float, default=14.0,
                         help='SEARCH_360 한 바퀴(약 10.5초, search_speed_rad_s=0.6 기준) + 여유')
    args = parser.parse_args()

    layout = load_layout()
    scenarios = build_scenarios(layout)

    rclpy.init()
    node = ScenarioTestNode(args.robot_name, args.sample_s)
    rows = []
    try:
        for sc in scenarios:
            ok = node.teleport(sc['x'], sc['y'], sc['yaw'])
            if not ok:
                node.get_logger().warn(f"{sc['label']} 텔레포트 실패")
            time.sleep(0.5)
            avg = node.sample()
            rows.append((sc['label'], avg['vision'], avg['thermal'], avg['gas']))
    finally:
        node.destroy_node()
        rclpy.try_shutdown()

    print(f"{'위치':<16}{'vision':>10}{'thermal':>10}{'gas':>10}")
    for label, v, t, g in rows:
        print(f'{label:<16}{v:>10.2f}{t:>10.2f}{g:>10.2f}')


if __name__ == '__main__':
    main()
