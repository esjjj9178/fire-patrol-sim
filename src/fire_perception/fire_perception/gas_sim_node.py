#!/usr/bin/env python3
"""역할(SIM ONLY): MQ-2 가스 센서 가상 모델. warehouse_layout.yaml 의 is_real=true 불만
     가스를 낸다(가시선 무관, 확산 가정). 목표농도에 1차 지연(τ)을 걸어 실제 센서 응답
     지연을 흉내내고, 노이즈를 더해 /gas/concentration(ppm), /fire/gas/detection 을 발행한다.
구독: /ground_truth/pose(PoseStamped, SIM ONLY)
발행: /gas/concentration(std_msgs/Float32), /fire/gas/detection(fire_interfaces/FireDetection,
     bearing/range 는 기본 NaN — gradient 힌트 옵션을 켜면 bearing 채움)
파라미터: config/perception.yaml 의 gas_sim_node 절.
"""
import math
from collections import deque

import numpy as np
import rclpy
from fire_interfaces.msg import FireDetection
from geometry_msgs.msg import Point, PoseStamped
from rclpy.node import Node
from std_msgs.msg import Float32

from fire_perception.layout_loader import fire_elements, load_layout
from fire_perception.vision_common import yaw_from_quaternion


def target_ppm(robot_xy, fires, base_ppm: float, peak_ppm: float, sigma_m: float) -> float:
    """base_ppm + Σ (gas_strength * peak_ppm) * exp(-d^2 / (2*sigma^2)), is_real 인 불만 포함."""
    rx, ry = robot_xy
    total = base_ppm
    for fire in fires:
        if not fire.get('is_real', False):
            continue
        fx, fy = fire['pose']['x'], fire['pose']['y']
        d2 = (fx - rx) ** 2 + (fy - ry) ** 2
        strength = float(fire.get('gas_strength', 1.0))
        total += strength * peak_ppm * math.exp(-d2 / (2.0 * sigma_m ** 2))
    return total


class GasSimNode(Node):

    def __init__(self):
        super().__init__('gas_sim_node')

        self.declare_parameter('base_ppm', 250.0)
        self.declare_parameter('peak_ppm', 1200.0)
        self.declare_parameter('sigma_m', 1.5)
        self.declare_parameter('tau_s', 2.0)
        self.declare_parameter('noise_std_ppm', 15.0)
        self.declare_parameter('rate_hz', 10.0)
        self.declare_parameter('score_low_ppm', 400.0)
        self.declare_parameter('score_high_ppm', 1500.0)
        self.declare_parameter('gas_frame', 'base_link')
        self.declare_parameter('enable_gradient_hint', False)
        self.declare_parameter('gradient_history_len', 20)
        self.declare_parameter('gradient_min_norm', 5.0)  # ppm/m 미만이면 방향 신뢰 안 함

        self._robot_xy = None
        self._robot_yaw = 0.0
        self._state_ppm = self.get_parameter('base_ppm').value
        self._history = deque(maxlen=self.get_parameter('gradient_history_len').value)

        layout = load_layout()
        self._fires = fire_elements(layout)

        self._conc_pub = self.create_publisher(Float32, '/gas/concentration', 10)
        self._det_pub = self.create_publisher(FireDetection, '/fire/gas/detection', 10)

        self.create_subscription(PoseStamped, '/ground_truth/pose', self._on_pose, 10)

        rate = self.get_parameter('rate_hz').value
        self._dt = 1.0 / rate
        self.create_timer(self._dt, self._tick)

        self.get_logger().info(f'gas_sim_node 시작 — is_real 불 {sum(f.get("is_real", False) for f in self._fires)}개')

    def _on_pose(self, msg):
        p = msg.pose.position
        q = msg.pose.orientation
        self._robot_xy = (p.x, p.y)
        self._robot_yaw = yaw_from_quaternion(q.x, q.y, q.z, q.w)

    def _tick(self):
        if self._robot_xy is None:
            return

        target = target_ppm(
            self._robot_xy, self._fires,
            self.get_parameter('base_ppm').value,
            self.get_parameter('peak_ppm').value,
            self.get_parameter('sigma_m').value)

        tau = self.get_parameter('tau_s').value
        alpha = self._dt / tau if tau > 0 else 1.0
        self._state_ppm += (target - self._state_ppm) * min(alpha, 1.0)

        noise_std = self.get_parameter('noise_std_ppm').value
        measured = self._state_ppm + (np.random.normal(0.0, noise_std) if noise_std > 0 else 0.0)
        measured = max(0.0, measured)

        self._conc_pub.publish(Float32(data=float(measured)))
        self._history.append((self._robot_xy[0], self._robot_xy[1], measured))

        low = self.get_parameter('score_low_ppm').value
        high = self.get_parameter('score_high_ppm').value
        score = float(np.clip((measured - low) / (high - low), 0.0, 1.0))

        det = FireDetection()
        det.header.stamp = self.get_clock().now().to_msg()
        det.header.frame_id = self.get_parameter('gas_frame').value
        det.source = 'gas'
        det.detected = score >= 0.5
        det.confidence = score
        det.raw_value = float(measured)
        det.bearing = float('nan')
        det.range = float('nan')
        det.position = Point()
        det.position_valid = False
        det.bbox = [-1, -1, -1, -1]

        if self.get_parameter('enable_gradient_hint').value:
            bearing = self._gradient_bearing()
            if bearing is not None:
                det.bearing = bearing

        self._det_pub.publish(det)

    def _gradient_bearing(self):
        """최근 이동 중 농도 변화로 대략적 방향(world 기울기)을 최소자승 추정해
        base_link 기준 bearing 으로 변환. 표본이 부족하거나 기울기가 작으면 None."""
        if len(self._history) < 5:
            return None
        pts = np.array(self._history)
        x, y, c = pts[:, 0], pts[:, 1], pts[:, 2]
        if np.ptp(x) < 0.1 and np.ptp(y) < 0.1:
            return None
        A = np.column_stack([x, y, np.ones_like(x)])
        try:
            coef, *_ = np.linalg.lstsq(A, c, rcond=None)
        except np.linalg.LinAlgError:
            return None
        a, b, _ = coef
        grad_norm = math.hypot(a, b)
        if grad_norm < self.get_parameter('gradient_min_norm').value:
            return None
        world_angle = math.atan2(b, a)
        bearing = world_angle - self._robot_yaw
        return math.atan2(math.sin(bearing), math.cos(bearing))


def main(args=None):
    rclpy.init(args=args)
    node = GasSimNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
