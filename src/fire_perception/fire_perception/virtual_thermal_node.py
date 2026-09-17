#!/usr/bin/env python3
"""역할(SIM ONLY 폴백): Gazebo 열화상 센서가 동작하지 않거나 너무 느릴 때 대신 쓰는
     가상 열화상 영상 생성 노드. warehouse_layout.yaml 의 불 위치/온도 + /ground_truth/pose
     (정답 위치, SIM ONLY) + 팬 각도로 32x24 열화상을 합성해 thermal_node 가 기대하는 것과
     동일한 형식(/thermal/image_raw, mono16)으로 발행한다. 벽/선반에 대한 2D 가시선 검사로
     가려진 불은 보이지 않게 한다. `ros2 launch ... virtual_thermal:=true` 로만 켠다.
구독: /ground_truth/pose(PoseStamped, SIM ONLY), /joint_states(팬 각도)
발행: /thermal/image_raw(mono16)
파라미터: config/perception.yaml 의 virtual_thermal_node 절.
"""
import math

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from geometry_msgs.msg import PoseStamped
from rclpy.node import Node
from sensor_msgs.msg import Image, JointState

from fire_perception.geometry_los import has_line_of_sight
from fire_perception.layout_loader import fire_elements, load_layout, occluder_elements
from fire_perception.vision_common import yaw_from_quaternion


class VirtualThermalNode(Node):

    def __init__(self):
        super().__init__('virtual_thermal_node')

        self.declare_parameter('width', 32)
        self.declare_parameter('height', 24)
        self.declare_parameter('hfov_rad', 0.96)
        self.declare_parameter('update_rate_hz', 8.0)
        self.declare_parameter('linear_resolution', 0.01)
        self.declare_parameter('ambient_k', 293.0)
        self.declare_parameter('max_range_m', 15.0)
        self.declare_parameter('atten_per_m', 0.03)      # 거리 1m 당 온도차 감쇠 비율
        self.declare_parameter('atten_min_factor', 0.35)  # 감쇠 하한(최소 이만큼은 보임)
        self.declare_parameter('blob_base_radius_px', 2.0)
        self.declare_parameter('gaussian_blur_ksize', 3)
        self.declare_parameter('noise_std_k', 1.0)
        self.declare_parameter('thermal_frame', 'thermal_optical_frame')

        self._bridge = CvBridge()
        self._pan_angle = 0.0
        self._robot_xy = None
        self._robot_yaw = 0.0

        layout = load_layout()
        self._fires = fire_elements(layout)
        self._occluders = occluder_elements(layout)

        self._pub = self.create_publisher(Image, '/thermal/image_raw', 5)
        self.create_subscription(PoseStamped, '/ground_truth/pose', self._on_pose, 10)
        self.create_subscription(JointState, '/joint_states', self._on_joint_states, 10)

        rate = self.get_parameter('update_rate_hz').value
        self.create_timer(1.0 / rate, self._tick)

        self.get_logger().warn(
            f'virtual_thermal_node 시작 (SIM ONLY 폴백) — 불 {len(self._fires)}개, '
            f'가림막 {len(self._occluders)}개 로드')

    def _on_pose(self, msg: PoseStamped):
        p = msg.pose.position
        q = msg.pose.orientation
        self._robot_xy = (p.x, p.y)
        self._robot_yaw = yaw_from_quaternion(q.x, q.y, q.z, q.w)

    def _on_joint_states(self, msg: JointState):
        try:
            idx = msg.name.index('camera_pan_joint')
        except ValueError:
            return
        self._pan_angle = msg.position[idx]

    def _tick(self):
        if self._robot_xy is None:
            return

        width = int(self.get_parameter('width').value)
        height = int(self.get_parameter('height').value)
        hfov = self.get_parameter('hfov_rad').value
        ambient = self.get_parameter('ambient_k').value
        max_range = self.get_parameter('max_range_m').value
        atten_per_m = self.get_parameter('atten_per_m').value
        atten_min = self.get_parameter('atten_min_factor').value
        base_r = self.get_parameter('blob_base_radius_px').value

        img = np.full((height, width), ambient, dtype=np.float32)
        f = (width / 2.0) / math.tan(hfov / 2.0)
        camera_heading = self._robot_yaw + self._pan_angle

        rx, ry = self._robot_xy
        for fire in self._fires:
            fx, fy = fire['pose']['x'], fire['pose']['y']
            dx, dy = fx - rx, fy - ry
            dist = math.hypot(dx, dy)
            if dist < 1e-3 or dist > max_range:
                continue
            world_angle = math.atan2(dy, dx)
            cam_angle = world_angle - camera_heading
            cam_angle = math.atan2(math.sin(cam_angle), math.cos(cam_angle))
            if abs(cam_angle) > hfov / 2.0:
                continue
            if not has_line_of_sight((rx, ry), (fx, fy), self._occluders):
                continue

            cx = width / 2.0 - f * math.tan(cam_angle)
            cy = height / 2.0

            fire_k = float(fire.get('temperature_k', ambient))
            atten = max(atten_min, 1.0 - atten_per_m * dist)
            eff_temp = ambient + (fire_k - ambient) * atten

            radius = max(1.0, base_r * (1.0 + 3.0 / max(dist, 0.5)))
            self._stamp_blob(img, cx, cy, radius, eff_temp)

        ksize = int(self.get_parameter('gaussian_blur_ksize').value)
        if ksize >= 3 and ksize % 2 == 1:
            img = cv2.GaussianBlur(img, (ksize, ksize), 0)

        noise_std = self.get_parameter('noise_std_k').value
        if noise_std > 0:
            img = img + np.random.normal(0.0, noise_std, img.shape).astype(np.float32)

        resolution = self.get_parameter('linear_resolution').value
        raw = np.clip(img / resolution, 0, 65535).astype(np.uint16)

        msg = self._bridge.cv2_to_imgmsg(raw, encoding='mono16')
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.get_parameter('thermal_frame').value
        self._pub.publish(msg)

    @staticmethod
    def _stamp_blob(img: np.ndarray, cx: float, cy: float, radius: float, temp: float):
        h, w = img.shape[:2]
        x0, x1 = max(0, int(cx - radius)), min(w, int(cx + radius) + 1)
        y0, y1 = max(0, int(cy - radius)), min(h, int(cy + radius) + 1)
        for y in range(y0, y1):
            for x in range(x0, x1):
                if (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2:
                    if temp > img[y, x]:
                        img[y, x] = temp


def main(args=None):
    rclpy.init(args=args)
    node = VirtualThermalNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
