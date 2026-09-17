#!/usr/bin/env python3
"""역할: Gazebo 열화상 카메라 원시 영상(/thermal/image_raw, mono16)을 켈빈으로 변환하고
     최고온도 기반으로 /fire/thermal/detection 을 발행한다.
구독: /thermal/image_raw(mono16), /joint_states(팬 각도), /camera/depth/image_raw(옵션)
발행: /thermal/temperature_image(32FC1, K), /fire/thermal/detection(fire_interfaces/FireDetection)
파라미터: config/perception.yaml 의 thermal_node 절.

열화상 스케일: gz-sensors8 ThermalCameraSensor 는 기본 linear_resolution=0.01(10mK)이며
(BaseThermalCamera.hh: "Linear resolution. Defaults to 10mK." / ThermalCameraSensor.hh
SetLinearResolution 문서: "temperature in kelvin / resolution"), min/max_temp 기본값은
-inf/+inf 라 클리핑 없이 raw(uint16, L16→ros mono16) = K / resolution 이 그대로 나온다.
fire_description/urdf/gazebo.xacro 의 thermal 센서에 <plugin ThermalSensor> 오버라이드가
없으므로 이 기본값이 적용된다 → K = raw * linear_resolution(기본 0.01).
"""
import math

import numpy as np
import rclpy
import tf2_ros
from cv_bridge import CvBridge
from fire_interfaces.msg import FireDetection
from geometry_msgs.msg import Point
from rclpy.node import Node
from rclpy.time import Time
from sensor_msgs.msg import Image, JointState

from fire_perception.vision_common import (bearing_range_to_map, camera_angle_to_bearing,
                                             depth_bbox_range, pixel_to_camera_angle,
                                             yaw_from_quaternion)


class ThermalNode(Node):

    def __init__(self):
        super().__init__('thermal_node')

        self.declare_parameter('linear_resolution', 0.01)   # K = raw * resolution
        self.declare_parameter('hfov_rad', 0.96)
        self.declare_parameter('score_low_k', 330.0)
        self.declare_parameter('score_high_k', 450.0)
        self.declare_parameter('thermal_frame', 'thermal_optical_frame')
        self.declare_parameter('map_frame', 'map')
        self.declare_parameter('base_frame', 'base_link')
        self.declare_parameter('use_depth_for_range', False)
        self.declare_parameter('depth_topic', '/camera/depth/image_raw')
        self.declare_parameter('depth_hfov_rad', 1.204)

        self._bridge = CvBridge()
        self._pan_angle = 0.0
        self._latest_depth = None

        self._temp_pub = self.create_publisher(Image, '/thermal/temperature_image', 5)
        self._det_pub = self.create_publisher(FireDetection, '/fire/thermal/detection', 10)

        self.create_subscription(Image, '/thermal/image_raw', self._on_thermal, 5)
        self.create_subscription(JointState, '/joint_states', self._on_joint_states, 10)
        if self.get_parameter('use_depth_for_range').value:
            self.create_subscription(Image, self.get_parameter('depth_topic').value,
                                      self._on_depth, 5)

        self._tf_buffer = tf2_ros.Buffer()
        self._tf_listener = tf2_ros.TransformListener(self._tf_buffer, self)

        self.get_logger().info('thermal_node 시작')

    def _on_joint_states(self, msg: JointState):
        try:
            idx = msg.name.index('camera_pan_joint')
        except ValueError:
            return
        self._pan_angle = msg.position[idx]

    def _on_depth(self, msg: Image):
        self._latest_depth = msg

    def _on_thermal(self, msg: Image):
        raw = self._bridge.imgmsg_to_cv2(msg, desired_encoding='passthrough')
        raw = np.asarray(raw).astype(np.float32)
        resolution = self.get_parameter('linear_resolution').value
        kelvin = raw * resolution

        temp_msg = self._bridge.cv2_to_imgmsg(kelvin, encoding='32FC1')
        temp_msg.header = msg.header
        temp_msg.header.frame_id = self.get_parameter('thermal_frame').value
        self._temp_pub.publish(temp_msg)

        height, width = kelvin.shape[:2]
        flat_idx = int(np.argmax(kelvin))
        hot_y, hot_x = divmod(flat_idx, width)
        t_max = float(kelvin[hot_y, hot_x])

        low = self.get_parameter('score_low_k').value
        high = self.get_parameter('score_high_k').value
        score = float(np.clip((t_max - low) / (high - low), 0.0, 1.0))
        detected = score >= 0.5

        hfov = self.get_parameter('hfov_rad').value
        cam_angle = pixel_to_camera_angle(float(hot_x), width, hfov)
        bearing = camera_angle_to_bearing(cam_angle, self._pan_angle)

        det = FireDetection()
        det.header.stamp = msg.header.stamp
        det.header.frame_id = self.get_parameter('thermal_frame').value
        det.source = 'thermal'
        det.detected = detected
        det.confidence = score
        det.raw_value = t_max
        det.bearing = bearing
        det.range = float('nan')
        det.position = Point()
        det.position_valid = False
        det.bbox = [-1, -1, -1, -1]

        if self.get_parameter('use_depth_for_range').value and self._latest_depth is not None:
            self._fill_range_and_position(det, bearing, cam_angle, hot_y, height)

        self._det_pub.publish(det)

    def _fill_range_and_position(self, det: FireDetection, bearing: float,
                                  cam_angle: float, hot_y: int, thermal_h: int):
        depth = self._bridge.imgmsg_to_cv2(self._latest_depth, desired_encoding='32FC1')
        depth = np.asarray(depth)
        dh, dw = depth.shape[:2]
        depth_hfov = self.get_parameter('depth_hfov_rad').value
        f = (dw / 2.0) / math.tan(depth_hfov / 2.0)
        dx = dw / 2.0 - f * math.tan(cam_angle)
        dx = int(np.clip(dx, 0, dw - 1))
        dy = int(np.clip(dh * (hot_y / max(thermal_h, 1)), 0, dh - 1))
        half = 4
        y1, y2 = max(0, dy - half), min(dh, dy + half + 1)
        x1, x2 = max(0, dx - half), min(dw, dx + half + 1)
        range_m = depth_bbox_range(depth, (x1, y1, x2, y2))
        if range_m is None:
            return
        det.range = range_m
        try:
            tf = self._tf_buffer.lookup_transform(
                self.get_parameter('map_frame').value,
                self.get_parameter('base_frame').value, Time())
        except Exception:
            return
        t = tf.transform.translation
        q = tf.transform.rotation
        yaw = yaw_from_quaternion(q.x, q.y, q.z, q.w)
        mx, my = bearing_range_to_map(t.x, t.y, yaw, bearing, range_m)
        det.position = Point(x=mx, y=my, z=0.0)
        det.position_valid = True


def main(args=None):
    rclpy.init(args=args)
    node = ThermalNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
