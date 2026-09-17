#!/usr/bin/env python3
"""역할: Nav2 활성화를 기다린 뒤 웨이포인트를 무한 순찰한다. mission_manager(STEP6)가 /patrol/cmd 로
     제어한다.
구독: /patrol/cmd (std_msgs/String: start|pause|resume|stop)
발행: /patrol/state (std_msgs/String: "IDLE|RUNNING|PAUSED|STOPPED:<현재 웨이포인트 인덱스>")
파라미터:
  waypoints_file (string): 웨이포인트 yaml 경로. 기본값은 fire_navigation 공유 디렉터리의
                            config/waypoints.yaml (fire_world/warehouse_layout.yaml 에서 자동 생성됨).
  autostart      (bool)  : 노드 시작 시 바로 RUNNING 으로 진입할지.
  speed_scale    (double): 1.0=정상 속도. SUSPECT 등 감속 상황에서 mission_manager 가 낮춰
                            velocity_smoother 의 max_velocity/min_velocity 를 동적으로 재조정한다.
  goal_retry     (int)   : 목표 실패 시 같은 웨이포인트 재시도 횟수(기본 1).
"""
import math
from pathlib import Path

import rclpy
import yaml
from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import PoseStamped
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult
from rcl_interfaces.msg import Parameter as ParameterMsg
from rcl_interfaces.msg import ParameterType, ParameterValue
from rcl_interfaces.srv import SetParameters
from std_msgs.msg import String

STATE_IDLE = 'IDLE'
STATE_RUNNING = 'RUNNING'
STATE_PAUSED = 'PAUSED'
STATE_STOPPED = 'STOPPED'


def _default_waypoints_file() -> str:
    try:
        return str(Path(get_package_share_directory('fire_navigation')) / 'config' / 'waypoints.yaml')
    except Exception:
        return str(Path(__file__).resolve().parent.parent / 'config' / 'waypoints.yaml')


def _load_waypoints(path: str):
    with open(path) as f:
        doc = yaml.safe_load(f)
    return doc['waypoints']


class PatrolNode(BasicNavigator):

    def __init__(self):
        super().__init__(node_name='patrol_node')

        self.declare_parameter('waypoints_file', _default_waypoints_file())
        self.declare_parameter('autostart', True)
        self.declare_parameter('speed_scale', 1.0)
        self.declare_parameter('goal_retry', 1)
        self.declare_parameter('max_speed_mps', 0.18)   # nav2_params.yaml 의 FollowPath.max_vel_x 와 일치시킬 것

        wp_path = self.get_parameter('waypoints_file').value
        self._waypoints = _load_waypoints(wp_path)
        if not self._waypoints:
            raise RuntimeError(f'웨이포인트가 비어 있음: {wp_path}')
        self.get_logger().info(f'{len(self._waypoints)}개 웨이포인트 로드: {wp_path}')

        self._state = STATE_IDLE
        self._index = 0
        self._retry_count = 0
        self._goal_in_flight = False
        self._last_speed_scale = 1.0

        self._state_pub = self.create_publisher(String, '/patrol/state', 10)
        self.create_subscription(String, '/patrol/cmd', self._on_cmd, 10)

        self._vel_smoother_client = self.create_client(
            SetParameters, '/velocity_smoother/set_parameters')

        self.add_on_set_parameters_callback(self._on_param_change)

        self._timer = self.create_timer(0.2, self._tick)
        self._state_timer = self.create_timer(0.5, self._publish_state)

    # ---------------- 명령 처리 ----------------
    def _on_cmd(self, msg: String):
        cmd = msg.data.strip().lower()
        if cmd == 'start':
            if self._state in (STATE_IDLE, STATE_STOPPED):
                self._index = 0
            self._state = STATE_RUNNING
            self._retry_count = 0
            self._send_goal(self._index)
        elif cmd == 'pause':
            if self._state == STATE_RUNNING:
                if self._goal_in_flight:
                    self.cancelTask()
                    self._goal_in_flight = False
                self._state = STATE_PAUSED
                self.get_logger().info(f'순찰 일시정지 (웨이포인트 {self._index})')
        elif cmd == 'resume':
            if self._state == STATE_PAUSED:
                self._state = STATE_RUNNING
                self._send_goal(self._index)
                self.get_logger().info(f'순찰 재개 (웨이포인트 {self._index})')
        elif cmd == 'stop':
            if self._goal_in_flight:
                self.cancelTask()
                self._goal_in_flight = False
            self._state = STATE_STOPPED
            self._index = 0
        else:
            self.get_logger().warn(f'알 수 없는 /patrol/cmd: {msg.data}')

    # ---------------- 목표 전송/진행 ----------------
    def _pose_for(self, wp_index: int) -> PoseStamped:
        wp = self._waypoints[wp_index]
        nxt = self._waypoints[(wp_index + 1) % len(self._waypoints)]
        yaw = wp.get('yaw', 0.0) or math.atan2(nxt['y'] - wp['y'], nxt['x'] - wp['x'])

        pose = PoseStamped()
        pose.header.frame_id = 'map'
        pose.header.stamp = self.get_clock().now().to_msg()
        pose.pose.position.x = float(wp['x'])
        pose.pose.position.y = float(wp['y'])
        # 순수 yaw 회전이므로 쿼터니언을 직접 계산(tf_transformations 의존성 회피).
        pose.pose.orientation.z = math.sin(yaw / 2.0)
        pose.pose.orientation.w = math.cos(yaw / 2.0)
        return pose

    def _send_goal(self, wp_index: int):
        pose = self._pose_for(wp_index)
        self.goToPose(pose)
        self._goal_in_flight = True
        self.get_logger().info(
            f"-> {self._waypoints[wp_index]['name']} "
            f"({pose.pose.position.x:.2f}, {pose.pose.position.y:.2f})")

    def _tick(self):
        if self._state != STATE_RUNNING or not self._goal_in_flight:
            return
        if not self.isTaskComplete():
            return

        self._goal_in_flight = False
        result = self.getResult()
        if result == TaskResult.SUCCEEDED:
            self._retry_count = 0
            self._index = (self._index + 1) % len(self._waypoints)
            if self._state == STATE_RUNNING:
                self._send_goal(self._index)
        else:
            goal_retry = self.get_parameter('goal_retry').value
            if self._retry_count < goal_retry:
                self._retry_count += 1
                self.get_logger().warn(
                    f'웨이포인트 {self._index} 실패({result}), 재시도 {self._retry_count}/{goal_retry}')
                if self._state == STATE_RUNNING:
                    self._send_goal(self._index)
            else:
                self.get_logger().warn(f'웨이포인트 {self._index} 실패, 다음으로 건너뜀')
                self._retry_count = 0
                self._index = (self._index + 1) % len(self._waypoints)
                if self._state == STATE_RUNNING:
                    self._send_goal(self._index)

    def _publish_state(self):
        msg = String()
        msg.data = f'{self._state}:{self._index}'
        self._state_pub.publish(msg)

    # ---------------- speed_scale -> velocity_smoother 동적 반영 ----------------
    def _on_param_change(self, params):
        from rcl_interfaces.msg import SetParametersResult
        for p in params:
            if p.name == 'speed_scale':
                self._apply_speed_scale(p.value)
        return SetParametersResult(successful=True)

    def _apply_speed_scale(self, scale: float):
        scale = max(0.05, min(1.0, float(scale)))
        if abs(scale - self._last_speed_scale) < 1e-3:
            return
        self._last_speed_scale = scale
        max_v = self.get_parameter('max_speed_mps').value * scale
        if not self._vel_smoother_client.service_is_ready():
            self.get_logger().warn(
                '/velocity_smoother/set_parameters 서비스 대기 중 - speed_scale 적용 보류')
            return
        req = SetParameters.Request()
        for name, values in (('max_velocity', [max_v, 0.0, 1.5]),
                              ('min_velocity', [-max_v, 0.0, -1.5])):
            pv = ParameterValue(type=ParameterType.PARAMETER_DOUBLE_ARRAY,
                                 double_array_value=values)
            req.parameters.append(ParameterMsg(name=name, value=pv))
        self._vel_smoother_client.call_async(req)
        self.get_logger().info(f'speed_scale={scale:.2f} -> velocity_smoother max={max_v:.3f} m/s')


def main(args=None):
    rclpy.init(args=args)
    node = PatrolNode()

    node.get_logger().info('Nav2 활성화 대기 중...')
    node.waitUntilNav2Active()
    node.get_logger().info('Nav2 활성화 완료')

    if node.get_parameter('autostart').value:
        node._state = STATE_RUNNING
        node._send_goal(0)

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
