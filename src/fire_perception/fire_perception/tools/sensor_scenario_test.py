#!/usr/bin/env python3
"""역할(SIM ONLY 검증 도구): STEP5.md의 "기대 결과 표"를 재현한다. Gazebo 의 world
     set_pose 서비스로 로봇을 각 불(real/fake/hidden) 근처 + "불 없는 곳"으로 순간이동시키고
     팬을 불 방향으로 맞춘 뒤 3초간 vision/thermal/gas 점수 평균을 표로 출력한다.
     **/check 5 에서 sim(+perception) 이 이미 떠 있는 상태에서 사용자가 직접 실행**
     (/build-all 구현 단계에서는 실행하지 않음).

사용:
  # 터미널: sim.launch.py + perception.launch.py(+ thermal/gas) 실행 중인 상태에서
  ros2 run fire_perception sensor_scenario_test

내부에서 `ros2 run ros_gz_bridge parameter_bridge
/world/<world>/set_pose@ros_gz_interfaces/srv/SetEntityPose` 를 임시로 띄워 텔레포트 서비스를
연결한다(bridge.yaml 에는 서비스 브리지가 없어 이 스크립트가 직접 띄우고 끝나면 종료한다).
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
from geometry_msgs.msg import Pose
from rclpy.node import Node
from ros_gz_interfaces.msg import Entity
from ros_gz_interfaces.srv import SetEntityPose
from std_msgs.msg import Float64, String


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
        self._scores = {'vision': [], 'thermal': [], 'gas': []}

        self.create_subscription(FireDetection, '/fire/vision/detection',
                                  lambda m: self._on_det('vision', m), 10)
        self.create_subscription(FireDetection, '/fire/thermal/detection',
                                  lambda m: self._on_det('thermal', m), 10)
        self.create_subscription(FireDetection, '/fire/gas/detection',
                                  lambda m: self._on_det('gas', m), 10)

        self._pan_cmd_pub = self.create_publisher(Float64, '/camera_pan/cmd', 10)
        self._pan_mode_pub = self.create_publisher(String, '/camera_pan/mode', 10)
        self._set_pose_cli = self.create_client(SetEntityPose, self._set_pose_service_name())

    def _set_pose_service_name(self) -> str:
        world = load_layout()['world']['name']
        return f'/world/{world}/set_pose'

    def _on_det(self, source: str, msg: FireDetection):
        self._scores[source].append(msg.confidence)

    def teleport(self, x: float, y: float, yaw: float) -> bool:
        if not self._set_pose_cli.wait_for_service(timeout_sec=5.0):
            self.get_logger().error('set_pose 서비스를 찾을 수 없음(브리지 확인)')
            return False
        req = SetEntityPose.Request()
        req.entity = Entity(name=self._robot_name, type=Entity.MODEL)
        pose = Pose()
        pose.position.x, pose.position.y, pose.position.z = x, y, 0.02
        pose.orientation.z = math.sin(yaw / 2.0)
        pose.orientation.w = math.cos(yaw / 2.0)
        req.pose = pose
        future = self._set_pose_cli.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)
        return bool(future.result() and future.result().success)

    def sample(self) -> dict:
        for key in self._scores:
            self._scores[key].clear()
        self._pan_mode_pub.publish(String(data='HOLD'))
        self._pan_cmd_pub.publish(Float64(data=0.0))
        end = time.time() + self._sample_s
        while time.time() < end:
            rclpy.spin_once(self, timeout_sec=0.1)
        return {k: (sum(v) / len(v) if v else float('nan')) for k, v in self._scores.items()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--robot-name', default='fire_bot')
    parser.add_argument('--sample-s', type=float, default=3.0)
    args = parser.parse_args()

    layout = load_layout()
    scenarios = build_scenarios(layout)

    bridge_proc = subprocess.Popen(
        ['ros2', 'run', 'ros_gz_bridge', 'parameter_bridge',
         f"/world/{layout['world']['name']}/set_pose@ros_gz_interfaces/srv/SetEntityPose"])
    time.sleep(2.0)

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
        bridge_proc.terminate()

    print(f"{'위치':<16}{'vision':>10}{'thermal':>10}{'gas':>10}")
    for label, v, t, g in rows:
        print(f'{label:<16}{v:>10.2f}{t:>10.2f}{g:>10.2f}')


if __name__ == '__main__':
    main()
