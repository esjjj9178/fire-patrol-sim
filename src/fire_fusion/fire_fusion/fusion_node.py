#!/usr/bin/env python3
"""역할: vision/thermal/gas FireDetection 을 가중치 융합해 fire_state 를 판정한다(판단만 하며
     로봇을 직접 움직이지 않는다 — 행동은 mission_manager_node 가 담당). 판정 로직은
     fusion_logic.FusionStateMachine(ROS 비의존, pytest 단위테스트 완료)을 그대로 감싼다.
구독: /fire/vision/detection, /fire/thermal/detection, /fire/gas/detection (fire_interfaces/FireDetection)
      /mission/state (std_msgs/String) - mission_manager_node 가 발행하는 mission_state.
      ARCHITECTURE.md 표에는 없던 내부 배선용 토픽이며, FireStatus.mission_state 필드를 채우기
      위해 STEP6 구현 중 추가했다(ARCHITECTURE.md 3절에 함께 반영).
발행: /fire/status(fire_interfaces/FireStatus, 10Hz)
      /fire/markers(visualization_msgs/MarkerArray: 확정=빨간 구+텍스트, 기각=회색 구,
      의심=로봇 위치 중심 노란 반투명 원)
파라미터: config/fusion.yaml 의 fusion_node 절.
"""
import rclpy
import tf2_ros
from fire_interfaces.msg import FireDetection, FireStatus
from geometry_msgs.msg import Point
from rclpy.node import Node
from rclpy.time import Time
from std_msgs.msg import String
from visualization_msgs.msg import Marker, MarkerArray

from fire_fusion.fusion_logic import STATE_CONFIRMED, STATE_FALSE_ALARM, STATE_SUSPECT, FusionStateMachine


def _stamp_to_sec(stamp) -> float:
    return stamp.sec + stamp.nanosec * 1e-9


class FusionNode(Node):

    def __init__(self):
        super().__init__('fusion_node')

        self.declare_parameter('weight_vision', 0.4)
        self.declare_parameter('weight_thermal', 0.4)
        self.declare_parameter('weight_gas', 0.2)
        self.declare_parameter('ema_alpha', 0.3)
        self.declare_parameter('sensor_high', 0.5)
        self.declare_parameter('confirm_threshold', 0.7)
        self.declare_parameter('release_threshold', 0.4)
        self.declare_parameter('stale_timeout_s', 1.0)
        self.declare_parameter('verify_timeout_s', 6.0)
        self.declare_parameter('confirm_hold_s', 1.0)
        self.declare_parameter('false_alarm_radius_m', 1.5)
        self.declare_parameter('false_alarm_ignore_s', 60.0)
        self.declare_parameter('position_window', 10)
        self.declare_parameter('publish_rate_hz', 10.0)
        self.declare_parameter('map_frame', 'map')
        self.declare_parameter('base_frame', 'base_link')
        self.declare_parameter('suspect_marker_radius_m', 2.0)

        params = {
            'weights': {
                'vision': self.get_parameter('weight_vision').value,
                'thermal': self.get_parameter('weight_thermal').value,
                'gas': self.get_parameter('weight_gas').value,
            },
            'ema_alpha': self.get_parameter('ema_alpha').value,
            'sensor_high': self.get_parameter('sensor_high').value,
            'confirm_threshold': self.get_parameter('confirm_threshold').value,
            'release_threshold': self.get_parameter('release_threshold').value,
            'stale_timeout_s': self.get_parameter('stale_timeout_s').value,
            'verify_timeout_s': self.get_parameter('verify_timeout_s').value,
            'confirm_hold_s': self.get_parameter('confirm_hold_s').value,
            'false_alarm_radius_m': self.get_parameter('false_alarm_radius_m').value,
            'false_alarm_ignore_s': self.get_parameter('false_alarm_ignore_s').value,
            'position_window': self.get_parameter('position_window').value,
        }
        self._logic = FusionStateMachine(params)
        self._map_frame = self.get_parameter('map_frame').value
        self._base_frame = self.get_parameter('base_frame').value

        self._detections = {'vision': None, 'thermal': None, 'gas': None}
        self._mission_state = 'PATROL'

        self._status_pub = self.create_publisher(FireStatus, '/fire/status', 10)
        self._marker_pub = self.create_publisher(MarkerArray, '/fire/markers', 10)

        self.create_subscription(FireDetection, '/fire/vision/detection',
                                  lambda m: self._on_detection('vision', m), 10)
        self.create_subscription(FireDetection, '/fire/thermal/detection',
                                  lambda m: self._on_detection('thermal', m), 10)
        self.create_subscription(FireDetection, '/fire/gas/detection',
                                  lambda m: self._on_detection('gas', m), 10)
        self.create_subscription(String, '/mission/state', self._on_mission_state, 10)

        self._tf_buffer = tf2_ros.Buffer()
        self._tf_listener = tf2_ros.TransformListener(self._tf_buffer, self)

        rate = self.get_parameter('publish_rate_hz').value
        self.create_timer(1.0 / rate, self._tick)

        self.get_logger().info('fusion_node 시작')

    def _on_detection(self, source: str, msg: FireDetection):
        pos = (msg.position.x, msg.position.y) if msg.position_valid else None
        self._detections[source] = {
            'stamp': _stamp_to_sec(msg.header.stamp),
            'detected': msg.detected,
            'confidence': float(msg.confidence),
            'position': pos,
            'position_valid': msg.position_valid,
        }

    def _on_mission_state(self, msg: String):
        self._mission_state = msg.data

    def _lookup_robot_xy(self):
        try:
            tf = self._tf_buffer.lookup_transform(self._map_frame, self._base_frame, Time())
        except Exception:
            return None
        t = tf.transform.translation
        return (t.x, t.y)

    def _tick(self):
        now = self.get_clock().now().nanoseconds * 1e-9
        result = self._logic.update(now, self._detections)

        for event in result['events']:
            if event.startswith('SENSOR_STALE'):
                self.get_logger().warn(f'센서 끊김 감지: {event}')
            elif event.startswith('STATE:'):
                self.get_logger().info(f'fire_state 전이: {event[6:]} ({result["reason"]})')

        status = FireStatus()
        status.header.stamp = self.get_clock().now().to_msg()
        status.header.frame_id = self._map_frame
        status.fire_state = result['fire_state']
        status.mission_state = self._mission_state
        status.fused_score = result['fused_score']
        status.vision_score = result['vision_score']
        status.thermal_score = result['thermal_score']
        status.gas_score = result['gas_score']
        if result['position_valid']:
            status.fire_position = Point(x=result['fire_position'][0],
                                          y=result['fire_position'][1], z=0.0)
        status.position_valid = result['position_valid']
        status.reason = result['reason']
        self._status_pub.publish(status)

        self._publish_markers(result)

    def _publish_markers(self, result):
        markers = MarkerArray()
        state = result['fire_state']
        stamp = self.get_clock().now().to_msg()
        rate = self.get_parameter('publish_rate_hz').value
        lifetime_s = max(0.2, 2.0 / rate)

        def _lifetime():
            from builtin_interfaces.msg import Duration
            return Duration(sec=int(lifetime_s), nanosec=int((lifetime_s % 1.0) * 1e9))

        if state == STATE_SUSPECT:
            robot_xy = self._lookup_robot_xy()
            if robot_xy is not None:
                m = Marker()
                m.header.frame_id = self._map_frame
                m.header.stamp = stamp
                m.ns, m.id = 'fire', 0
                m.type, m.action = Marker.CYLINDER, Marker.ADD
                m.pose.position = Point(x=robot_xy[0], y=robot_xy[1], z=0.02)
                m.pose.orientation.w = 1.0
                r = self.get_parameter('suspect_marker_radius_m').value
                m.scale.x = m.scale.y = 2.0 * r
                m.scale.z = 0.02
                m.color.r, m.color.g, m.color.b, m.color.a = 1.0, 1.0, 0.0, 0.3
                m.lifetime = _lifetime()
                markers.markers.append(m)
        elif state in (STATE_CONFIRMED, STATE_FALSE_ALARM) and result['position_valid']:
            x, y = result['fire_position']
            m = Marker()
            m.header.frame_id = self._map_frame
            m.header.stamp = stamp
            m.ns, m.id = 'fire', 0
            m.type, m.action = Marker.SPHERE, Marker.ADD
            m.pose.position = Point(x=x, y=y, z=0.25)
            m.pose.orientation.w = 1.0
            m.lifetime = _lifetime()
            if state == STATE_CONFIRMED:
                m.scale.x = m.scale.y = m.scale.z = 0.4
                m.color.r, m.color.g, m.color.b, m.color.a = 1.0, 0.0, 0.0, 0.9
                txt = Marker()
                txt.header.frame_id = self._map_frame
                txt.header.stamp = stamp
                txt.ns, txt.id = 'fire_text', 1
                txt.type, txt.action = Marker.TEXT_VIEW_FACING, Marker.ADD
                txt.pose.position = Point(x=x, y=y, z=0.7)
                txt.pose.orientation.w = 1.0
                txt.scale.z = 0.3
                txt.color.r = txt.color.g = txt.color.b = txt.color.a = 1.0
                txt.text = 'CONFIRMED'
                txt.lifetime = _lifetime()
                markers.markers.append(txt)
            else:
                m.scale.x = m.scale.y = m.scale.z = 0.3
                m.color.r = m.color.g = m.color.b = 0.6
                m.color.a = 0.6
            markers.markers.append(m)

        self._marker_pub.publish(markers)


def main(args=None):
    rclpy.init(args=args)
    node = FusionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
