#!/usr/bin/env python3
"""역할: RGB(+depth) 영상에서 화재(빨간 박스)를 검출해 /fire/vision/detection 을 발행한다.
     backend 는 파라미터 detector(hsv|yolo)로 선택하며 출력 메시지 형식은 동일하다.
구독: /camera/color/image_raw, /camera/depth/image_raw, /camera/color/camera_info, /joint_states
발행: /fire/vision/detection (fire_interfaces/FireDetection) — 검출 없을 때도
     detected=false 로 publish_rate_hz 주기 발행.
파라미터: config/perception.yaml 의 vision_node/hsv_detector/yolo_detector 절 참고.
"""
import math
from pathlib import Path

import numpy as np
import rclpy
import tf2_ros
from ament_index_python.packages import get_package_share_directory
from cv_bridge import CvBridge
from fire_interfaces.msg import FireDetection
from geometry_msgs.msg import Point
from rclpy.node import Node
from rclpy.time import Time
from sensor_msgs.msg import CameraInfo, Image, JointState

from fire_perception.hsv_detector import HsvDetector
from fire_perception.vision_common import (bbox_to_bearing, bearing_range_to_map,
                                            depth_bbox_range, yaw_from_quaternion)
from fire_perception.yolo_detector import YoloDetector


def _default_model_path() -> str:
    try:
        return str(Path(get_package_share_directory('fire_perception')) / 'models' / 'fire_yolov8n.pt')
    except Exception:
        return str(Path(__file__).resolve().parent.parent / 'models' / 'fire_yolov8n.pt')


class VisionNode(Node):

    def __init__(self):
        super().__init__('vision_node')

        self.declare_parameter('detector', 'hsv')
        self.declare_parameter('publish_rate_hz', 5.0)
        self.declare_parameter('camera_frame', 'camera_color_optical_frame')
        self.declare_parameter('rgb_topic', '/camera/color/image_raw')
        self.declare_parameter('depth_topic', '/camera/depth/image_raw')
        self.declare_parameter('camera_info_topic', '/camera/color/camera_info')
        self.declare_parameter('map_frame', 'map')
        self.declare_parameter('base_frame', 'base_link')
        self.declare_parameter('min_confidence', 0.3)

        self.declare_parameter('hue_low1', 0)
        self.declare_parameter('hue_low2', 10)
        self.declare_parameter('hue_high1', 170)
        self.declare_parameter('hue_high2', 179)
        self.declare_parameter('sat_min', 120)
        self.declare_parameter('val_min', 80)
        self.declare_parameter('min_area_px', 60)
        self.declare_parameter('morph_kernel', 5)

        self.declare_parameter('model_path', '')
        self.declare_parameter('imgsz', 320)
        self.declare_parameter('conf_threshold', 0.4)
        self.declare_parameter('device', 'cpu')
        self.declare_parameter('class_name', 'fire')

        self._bridge = CvBridge()
        self._latest_rgb = None
        self._latest_depth = None
        self._latest_camera_info = None
        self._pan_angle = 0.0

        hsv = HsvDetector(
            hue_low1=self.get_parameter('hue_low1').value,
            hue_low2=self.get_parameter('hue_low2').value,
            hue_high1=self.get_parameter('hue_high1').value,
            hue_high2=self.get_parameter('hue_high2').value,
            sat_min=self.get_parameter('sat_min').value,
            val_min=self.get_parameter('val_min').value,
            min_area_px=self.get_parameter('min_area_px').value,
            morph_kernel=self.get_parameter('morph_kernel').value,
        )

        detector_kind = self.get_parameter('detector').value
        if detector_kind == 'yolo':
            model_path = self.get_parameter('model_path').value or _default_model_path()
            self._detector = YoloDetector(
                model_path=model_path,
                imgsz=self.get_parameter('imgsz').value,
                conf_threshold=self.get_parameter('conf_threshold').value,
                device=self.get_parameter('device').value,
                class_name=self.get_parameter('class_name').value,
                fallback=hsv,
                logger=self.get_logger(),
            )
        else:
            self._detector = hsv

        self._tf_buffer = tf2_ros.Buffer()
        self._tf_listener = tf2_ros.TransformListener(self._tf_buffer, self)

        self._pub = self.create_publisher(FireDetection, '/fire/vision/detection', 10)

        self.create_subscription(Image, self.get_parameter('rgb_topic').value, self._on_rgb, 5)
        self.create_subscription(Image, self.get_parameter('depth_topic').value, self._on_depth, 5)
        self.create_subscription(CameraInfo, self.get_parameter('camera_info_topic').value,
                                  self._on_camera_info, 5)
        self.create_subscription(JointState, '/joint_states', self._on_joint_states, 10)

        rate = self.get_parameter('publish_rate_hz').value
        self.create_timer(1.0 / rate, self._tick)

        backend = 'hsv' if getattr(self._detector, 'using_fallback', False) else detector_kind
        self.get_logger().info(f'vision_node 시작: backend={backend}')

    def _on_rgb(self, msg: Image):
        self._latest_rgb = msg

    def _on_depth(self, msg: Image):
        self._latest_depth = msg

    def _on_camera_info(self, msg: CameraInfo):
        self._latest_camera_info = msg

    def _on_joint_states(self, msg: JointState):
        try:
            idx = msg.name.index('camera_pan_joint')
        except ValueError:
            return
        self._pan_angle = msg.position[idx]

    def _tick(self):
        if self._latest_rgb is None or self._latest_camera_info is None:
            return

        rgb = self._bridge.imgmsg_to_cv2(self._latest_rgb, desired_encoding='bgr8')
        detections = self._detector.detect(rgb)
        min_conf = self.get_parameter('min_confidence').value
        detections = [d for d in detections if d[1] >= min_conf]

        msg = FireDetection()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.get_parameter('camera_frame').value
        msg.source = 'vision'
        msg.bearing = float('nan')
        msg.range = float('nan')
        msg.position = Point()
        msg.position_valid = False
        msg.bbox = [-1, -1, -1, -1]

        if not detections:
            msg.detected = False
            msg.confidence = 0.0
            msg.raw_value = 0.0
            self._pub.publish(msg)
            return

        bbox, confidence = detections[0]
        msg.detected = True
        msg.confidence = confidence
        msg.raw_value = confidence
        msg.bbox = list(bbox)

        width = self._latest_camera_info.width
        fx = self._latest_camera_info.k[0]
        hfov = 2.0 * math.atan(width / (2.0 * fx)) if fx > 0 else 1.204
        bearing = bbox_to_bearing(bbox, width, hfov, self._pan_angle)
        msg.bearing = bearing

        range_m = None
        if self._latest_depth is not None:
            depth = self._bridge.imgmsg_to_cv2(self._latest_depth, desired_encoding='32FC1')
            range_m = depth_bbox_range(np.asarray(depth), bbox)
        if range_m is not None:
            msg.range = range_m
            self._fill_map_position(msg, bearing, range_m)

        self._pub.publish(msg)

    def _fill_map_position(self, msg: FireDetection, bearing: float, range_m: float):
        map_frame = self.get_parameter('map_frame').value
        base_frame = self.get_parameter('base_frame').value
        try:
            tf = self._tf_buffer.lookup_transform(map_frame, base_frame, Time())
        except Exception:
            return
        t = tf.transform.translation
        q = tf.transform.rotation
        yaw = yaw_from_quaternion(q.x, q.y, q.z, q.w)
        mx, my = bearing_range_to_map(t.x, t.y, yaw, bearing, range_m)
        msg.position = Point(x=mx, y=my, z=0.0)
        msg.position_valid = True


def main(args=None):
    rclpy.init(args=args)
    node = VisionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
