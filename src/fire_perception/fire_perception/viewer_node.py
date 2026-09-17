#!/usr/bin/env python3
"""역할: RGB+bbox / 열화상 컬러맵 / 점수막대+상태 세 패널을 한 장으로 합성해
     /fire/debug_image 로 발행한다(rqt_image_view 로 확인).
구독: /camera/color/image_raw(RGB), /thermal/temperature_image(32FC1, K),
      /fire/vision/detection(bbox+confidence 오버레이), /fire/status(점수/상태),
      /gas/concentration(ppm 표시용)
발행: /fire/debug_image(sensor_msgs/Image, bgr8, 기본 640x300, 5Hz)
파라미터: config/perception.yaml 의 viewer_node 절.
"""
import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from fire_interfaces.msg import FireDetection, FireStatus
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import Float32


def draw_score_bars(width: int, height: int, scores: dict, fire_state: str,
                     mission_state: str, gas_ppm: float) -> np.ndarray:
    """오른쪽 패널: vision/thermal/gas/fused 막대(임계선 0.5/0.7) + 상태 텍스트. 순수 함수(테스트용)."""
    panel = np.full((height, width, 3), (30, 30, 30), dtype=np.uint8)
    names = ['vision', 'thermal', 'gas', 'fused']
    bar_top, bar_bottom = 90, height - 60
    bar_h = bar_bottom - bar_top
    bar_w = max(1, (width - 40) // len(names))

    def _thresh_y(v: float) -> int:
        return int(bar_bottom - v * bar_h)

    cv2.line(panel, (10, _thresh_y(0.5)), (width - 10, _thresh_y(0.5)), (0, 255, 255), 1)
    cv2.line(panel, (10, _thresh_y(0.7)), (width - 10, _thresh_y(0.7)), (0, 0, 255), 1)

    for i, name in enumerate(names):
        v = float(np.clip(scores.get(name, 0.0), 0.0, 1.0))
        x1 = 20 + i * bar_w
        x2 = x1 + bar_w - 10
        y1 = _thresh_y(v)
        color = (0, 0, 255) if v >= 0.7 else ((0, 255, 255) if v >= 0.5 else (120, 200, 120))
        cv2.rectangle(panel, (x1, y1), (x2, bar_bottom), color, -1)
        cv2.rectangle(panel, (x1, bar_top), (x2, bar_bottom), (90, 90, 90), 1)
        cv2.putText(panel, name, (x1, bar_bottom + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.35,
                    (220, 220, 220), 1, cv2.LINE_AA)
        cv2.putText(panel, f'{v:.2f}', (x1, y1 - 4 if y1 > 12 else y1 + 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1, cv2.LINE_AA)

    cv2.putText(panel, f'fire: {fire_state}', (10, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(panel, f'mission: {mission_state}', (10, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(panel, f'gas: {gas_ppm:.0f} ppm', (10, 54), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                (255, 255, 255), 1, cv2.LINE_AA)
    return panel


def thermal_to_colormap(kelvin: np.ndarray, low_k: float, high_k: float,
                         out_w: int, out_h: int) -> tuple:
    """32FC1 켈빈 이미지 -> INFERNO 컬러맵(out_w x out_h)으로 확대, (image, tmax, hot_xy) 반환."""
    norm = np.clip((kelvin - low_k) / max(high_k - low_k, 1e-6), 0.0, 1.0)
    gray = (norm * 255.0).astype(np.uint8)
    color = cv2.applyColorMap(gray, cv2.COLORMAP_INFERNO)
    color = cv2.resize(color, (out_w, out_h), interpolation=cv2.INTER_NEAREST)
    flat_idx = int(np.argmax(kelvin))
    hy, hx = divmod(flat_idx, kelvin.shape[1])
    tmax = float(kelvin[hy, hx])
    scale_x = out_w / kelvin.shape[1]
    scale_y = out_h / kelvin.shape[0]
    hot_xy = (int(hx * scale_x), int(hy * scale_y))
    return color, tmax, hot_xy


class ViewerNode(Node):

    def __init__(self):
        super().__init__('viewer_node')

        self.declare_parameter('publish_rate_hz', 5.0)
        self.declare_parameter('panel_width', 213)
        self.declare_parameter('panel_height', 300)
        self.declare_parameter('score_low_k', 330.0)
        self.declare_parameter('score_high_k', 450.0)
        self.declare_parameter('show_window', False)

        self._bridge = CvBridge()
        self._latest_rgb = None
        self._latest_thermal_k = None
        self._latest_bbox = None
        self._latest_vision_conf = 0.0
        self._latest_vision_detected = False
        self._gas_ppm = 0.0
        self._status = FireStatus()
        self._window_ok = self.get_parameter('show_window').value
        self._window_name = 'fire_debug'

        self._pub = self.create_publisher(Image, '/fire/debug_image', 5)
        self.create_subscription(Image, '/camera/color/image_raw', self._on_rgb, 5)
        self.create_subscription(Image, '/thermal/temperature_image', self._on_thermal, 5)
        self.create_subscription(FireDetection, '/fire/vision/detection', self._on_vision, 10)
        self.create_subscription(FireStatus, '/fire/status', self._on_status, 10)
        self.create_subscription(Float32, '/gas/concentration', self._on_gas, 10)

        rate = self.get_parameter('publish_rate_hz').value
        self.create_timer(1.0 / rate, self._tick)

        self.get_logger().info('viewer_node 시작')

    def _on_rgb(self, msg: Image):
        self._latest_rgb = self._bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')

    def _on_thermal(self, msg: Image):
        img = self._bridge.imgmsg_to_cv2(msg, desired_encoding='32FC1')
        self._latest_thermal_k = np.asarray(img)

    def _on_vision(self, msg: FireDetection):
        self._latest_vision_detected = msg.detected
        self._latest_vision_conf = msg.confidence
        self._latest_bbox = list(msg.bbox) if msg.detected and msg.bbox[0] >= 0 else None

    def _on_status(self, msg: FireStatus):
        self._status = msg

    def _on_gas(self, msg: Float32):
        self._gas_ppm = msg.data

    def _left_panel(self, w: int, h: int) -> np.ndarray:
        if self._latest_rgb is None:
            return np.full((h, w, 3), (20, 20, 20), dtype=np.uint8)
        img = cv2.resize(self._latest_rgb, (w, h))
        if self._latest_bbox is not None:
            sx = w / max(self._latest_rgb.shape[1], 1)
            sy = h / max(self._latest_rgb.shape[0], 1)
            x1, y1, x2, y2 = self._latest_bbox
            p1 = (int(x1 * sx), int(y1 * sy))
            p2 = (int(x2 * sx), int(y2 * sy))
            cv2.rectangle(img, p1, p2, (0, 255, 0), 2)
            cv2.putText(img, f'fire {self._latest_vision_conf:.2f}',
                        (p1[0], max(0, p1[1] - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                        (0, 255, 0), 1, cv2.LINE_AA)
        return img

    def _mid_panel(self, w: int, h: int) -> np.ndarray:
        if self._latest_thermal_k is None:
            return np.full((h, w, 3), (20, 20, 20), dtype=np.uint8)
        low = self.get_parameter('score_low_k').value
        high = self.get_parameter('score_high_k').value
        color, tmax, hot_xy = thermal_to_colormap(self._latest_thermal_k, low, high, w, h)
        cv2.drawMarker(color, hot_xy, (255, 255, 255), cv2.MARKER_CROSS, 12, 1)
        cv2.putText(color, f'Tmax {tmax:.0f}K', (8, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (255, 255, 255), 1, cv2.LINE_AA)
        return color

    def _tick(self):
        w = self.get_parameter('panel_width').value
        h = self.get_parameter('panel_height').value

        left = self._left_panel(w, h)
        mid = self._mid_panel(w, h)
        scores = {
            'vision': self._status.vision_score,
            'thermal': self._status.thermal_score,
            'gas': self._status.gas_score,
            'fused': self._status.fused_score,
        }
        right = draw_score_bars(w, h, scores,
                                 self._status.fire_state or 'NONE',
                                 self._status.mission_state or 'PATROL',
                                 self._gas_ppm)

        combined = np.hstack([left, mid, right])
        msg = self._bridge.cv2_to_imgmsg(combined, encoding='bgr8')
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'camera_color_optical_frame'
        self._pub.publish(msg)

        if self._window_ok:
            try:
                cv2.imshow(self._window_name, combined)
                cv2.waitKey(1)
            except cv2.error as e:
                self.get_logger().warn(f'cv2.imshow 실패(Qt 문제 가능) - show_window 끔: {e}')
                self._window_ok = False


def main(args=None):
    rclpy.init(args=args)
    node = ViewerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
