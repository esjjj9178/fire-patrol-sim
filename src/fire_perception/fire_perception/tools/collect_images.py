#!/usr/bin/env python3
"""역할: 순찰/teleop 주행 중 RGB 프레임을 collect_interval_s 마다 저장해 YOLO 학습용
     원본 이미지셋(~/fire_ws/data/raw/)을 만든다. **/check 4 에서 사용자가 직접 실행**
     (시뮬 필요 — /build-all 구현 단계에서는 실행하지 않음).
구독: /camera/color/image_raw (sensor_msgs/Image)
발행: 없음 (파일 저장 전용)
파라미터(ROS): raw_dir, target_images, collect_interval_s, rgb_topic
     — 기본값은 fire_perception/config/perception.yaml 의 dataset_tools 절.

사용:
  # 터미널: sim + nav(순찰) 실행 중인 상태에서
  ros2 run fire_perception collect_images
  ros2 run fire_perception collect_images --ros-args -p target_images:=300

목표 250~300장, 불 3개가 다양한 거리/각도로 찍히도록 순찰 경로를 활용하고
(팬은 perception.launch.py 의 camera_pan_node 가 SWEEP_FRONT 로 자동으로 돌림),
배경(불 없음) 장면도 자연히 섞인다(순찰 중 불이 안 보이는 구간이 대부분이므로
목표 대비 20% 이상은 저절로 확보됨 — 부족하면 --ros-args -p target_images 를 늘려 보충).
"""
import time
from pathlib import Path

import cv2
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from sensor_msgs.msg import Image


def _default_workspace_dir() -> Path:
    return Path.home() / 'fire_ws'


class CollectImagesNode(Node):

    def __init__(self):
        super().__init__('collect_images')
        self.declare_parameter('raw_dir', 'data/raw')
        self.declare_parameter('target_images', 280)
        self.declare_parameter('collect_interval_s', 0.5)
        self.declare_parameter('rgb_topic', '/camera/color/image_raw')

        raw_dir = self.get_parameter('raw_dir').value
        raw_path = Path(raw_dir)
        self._out_dir = raw_path if raw_path.is_absolute() else _default_workspace_dir() / raw_dir
        self._out_dir.mkdir(parents=True, exist_ok=True)
        self._target = int(self.get_parameter('target_images').value)
        self._interval = float(self.get_parameter('collect_interval_s').value)

        self._bridge = CvBridge()
        self._count = len(list(self._out_dir.glob('img_*.png')))
        self._last_save = 0.0

        self.create_subscription(Image, self.get_parameter('rgb_topic').value, self._on_image, 5)
        self.get_logger().info(
            f'저장 목표 {self._target}장 (기존 {self._count}장 포함) -> {self._out_dir}')

    def _on_image(self, msg: Image):
        now = time.time()
        if now - self._last_save < self._interval:
            return
        self._last_save = now

        img = self._bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        path = self._out_dir / f'img_{self._count:05d}.png'
        cv2.imwrite(str(path), img)
        self._count += 1
        if self._count % 20 == 0 or self._count >= self._target:
            self.get_logger().info(f'{self._count}/{self._target} 저장됨')

        if self._count >= self._target:
            self.get_logger().info('목표 수량 도달 - 종료합니다')
            rclpy.shutdown()


def main(args=None):
    rclpy.init(args=args)
    node = CollectImagesNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if rclpy.ok():
            node.destroy_node()
            rclpy.try_shutdown()


if __name__ == '__main__':
    main()
