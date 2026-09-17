#!/usr/bin/env python3
"""역할: /camera_pan/mode 에 따라 camera_pan_joint 목표 각도(/camera_pan/cmd)를 생성한다.
     실제 조인트 구동은 Gazebo JointPositionController(gazebo.xacro)가 이 목표를 추종한다.
구독: /camera_pan/mode (std_msgs/String: SWEEP_FRONT|SEARCH_360|TRACK|HOLD)
      /camera_pan/track_bearing (std_msgs/Float32, TRACK 모드 목표 방위[rad], base_link 기준)
발행: /camera_pan/cmd (std_msgs/Float64, camera_pan_joint 목표 위치[rad])
      /camera_pan/search_done (std_msgs/Bool, SEARCH_360 이 -pi->+pi 를 한 번 다 훑으면 1회 발행)
파라미터: config/perception.yaml 의 camera_pan_node 절 참고.
"""
import math

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, Float32, Float64, String

MODE_SWEEP = 'SWEEP_FRONT'
MODE_SEARCH = 'SEARCH_360'
MODE_TRACK = 'TRACK'
MODE_HOLD = 'HOLD'
_VALID_MODES = (MODE_SWEEP, MODE_SEARCH, MODE_TRACK, MODE_HOLD)


class CameraPanNode(Node):

    def __init__(self):
        super().__init__('camera_pan_node')

        self.declare_parameter('sweep_speed_rad_s', 0.5)
        self.declare_parameter('sweep_min_rad', -math.pi / 2)
        self.declare_parameter('sweep_max_rad', math.pi / 2)
        self.declare_parameter('search_speed_rad_s', 0.6)
        self.declare_parameter('search_min_rad', -math.pi)
        self.declare_parameter('search_max_rad', math.pi)
        self.declare_parameter('track_max_rad_s', 1.0)
        self.declare_parameter('publish_rate_hz', 20.0)

        self._mode = MODE_SWEEP
        self._target = 0.0
        self._sweep_dir = 1
        self._search_active = True
        self._track_bearing = 0.0

        self._cmd_pub = self.create_publisher(Float64, '/camera_pan/cmd', 10)
        self._search_done_pub = self.create_publisher(Bool, '/camera_pan/search_done', 10)

        self.create_subscription(String, '/camera_pan/mode', self._on_mode, 10)
        self.create_subscription(Float32, '/camera_pan/track_bearing', self._on_track_bearing, 10)

        rate = self.get_parameter('publish_rate_hz').value
        self._dt = 1.0 / rate
        self._timer = self.create_timer(self._dt, self._tick)

    def _on_mode(self, msg: String):
        new_mode = msg.data.strip().upper()
        if new_mode not in _VALID_MODES:
            self.get_logger().warn(f'알 수 없는 /camera_pan/mode: {msg.data}')
            return
        if new_mode != self._mode:
            self.get_logger().info(f'팬 모드 전환: {self._mode} -> {new_mode}')
            if new_mode == MODE_SEARCH:
                self._target = self.get_parameter('search_min_rad').value
                self._search_active = True
            elif new_mode == MODE_SWEEP:
                self._sweep_dir = 1 if self._target <= 0 else -1
        elif new_mode == MODE_SEARCH and not self._search_active:
            # 이미 SEARCH_360 이고 이전 훑기가 끝난 상태에서 같은 모드를 재요청 -> 재시작.
            # mission_manager_node(STEP6)가 SEARCH_360 을 반복시키는 데 사용한다.
            self.get_logger().info('SEARCH_360 재시작 요청')
            self._target = self.get_parameter('search_min_rad').value
            self._search_active = True
        self._mode = new_mode

    def _on_track_bearing(self, msg: Float32):
        self._track_bearing = float(msg.data)

    def _tick(self):
        if self._mode == MODE_SWEEP:
            self._step_sweep()
        elif self._mode == MODE_SEARCH:
            self._step_search()
        elif self._mode == MODE_TRACK:
            self._step_track()
        # HOLD: _target 그대로 유지

        msg = Float64()
        msg.data = self._target
        self._cmd_pub.publish(msg)

    def _step_sweep(self):
        lo = self.get_parameter('sweep_min_rad').value
        hi = self.get_parameter('sweep_max_rad').value
        speed = self.get_parameter('sweep_speed_rad_s').value
        self._target += self._sweep_dir * speed * self._dt
        if self._target >= hi:
            self._target = hi
            self._sweep_dir = -1
        elif self._target <= lo:
            self._target = lo
            self._sweep_dir = 1

    def _step_search(self):
        if not self._search_active:
            return
        hi = self.get_parameter('search_max_rad').value
        speed = self.get_parameter('search_speed_rad_s').value
        self._target += speed * self._dt
        if self._target >= hi:
            self._target = hi
            self._search_active = False
            self._search_done_pub.publish(Bool(data=True))
            self.get_logger().info('SEARCH_360 완료')

    def _step_track(self):
        max_rate = self.get_parameter('track_max_rad_s').value
        target = max(-math.pi, min(math.pi, self._track_bearing))
        diff = target - self._target
        step = max(-max_rate * self._dt, min(max_rate * self._dt, diff))
        self._target += step


def main(args=None):
    rclpy.init(args=args)
    node = CameraPanNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
