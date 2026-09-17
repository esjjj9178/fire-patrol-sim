#!/usr/bin/env python3
"""역할(스텁, 기본 비활성): ROS 토픽 <-> MQTT 브리지. `enabled:false`(기본)면 아무 것도
     연결하지 않고 노드만 대기한다. `enabled:true`면 로컬 mosquitto(또는 설정된 브로커)에
     연결해 /fire/event, /fire/status 를 MQTT 로 중계하고 factory/{robot_id}/cmd 를 구독해
     ROS 로 되돌린다. 상세 설계는 docs/MQTT_DESIGN.md 참고.

     **버전 함정 주의**: apt python3-paho-mqtt 는 1.x API(CLAUDE.md). `mqtt.Client(client_id=...)`
     생성자만 쓰고 2.x 전용 `CallbackAPIVersion` 은 쓰지 않는다.

구독: /fire/event(std_msgs/String, JSON) - 즉시 MQTT 로 전달(또는 오프라인이면 버퍼링).
      /fire/status(fire_interfaces/FireStatus) - status_rate_hz 로 MQTT status 페이로드 구성.
      /odometry/filtered(nav_msgs/Odometry) - telemetry_rate_hz 로 MQTT telemetry 페이로드 구성.
발행: /mission/cmd(std_msgs/String) - MQTT factory/{robot_id}/cmd 로 들어온 명령을 ROS 로 중계.
파라미터: config/mqtt.yaml 의 mqtt_bridge_node 절.
"""
import json
from collections import deque
from datetime import datetime, timezone

import rclpy
from fire_interfaces.msg import FireStatus
from nav_msgs.msg import Odometry
from rclpy.node import Node
from std_msgs.msg import String

from fire_iot_bridge.adapters.advantech import LocalMosquittoAdapter

try:
    import paho.mqtt.client as mqtt
except ImportError:  # pragma: no cover - apt python3-paho-mqtt 미설치 시에도 노드는 뜨게 함
    mqtt = None


class MqttBridgeNode(Node):

    def __init__(self):
        super().__init__('mqtt_bridge_node')

        self.declare_parameter('enabled', False)
        self.declare_parameter('robot_id', 'fire_bot_01')
        self.declare_parameter('broker_host', '127.0.0.1')
        self.declare_parameter('broker_port', 1883)
        self.declare_parameter('keepalive_s', 30)
        self.declare_parameter('status_rate_hz', 1.0)
        self.declare_parameter('telemetry_rate_hz', 1.0)
        self.declare_parameter('reconnect_min_delay_s', 1.0)
        self.declare_parameter('reconnect_max_delay_s', 30.0)
        self.declare_parameter('offline_buffer_max', 200)
        self.declare_parameter('map_frame', 'map')
        self.declare_parameter('base_frame', 'base_link')

        self._enabled = self.get_parameter('enabled').value
        self._robot_id = self.get_parameter('robot_id').value
        self._adapter = LocalMosquittoAdapter()
        self._connected = False
        self._buffer = deque(maxlen=self.get_parameter('offline_buffer_max').value)
        self._status = None
        self._odom = None
        self._client = None

        self._cmd_pub = self.create_publisher(String, '/mission/cmd', 10)
        self.create_subscription(String, '/fire/event', self._on_event, 10)
        self.create_subscription(FireStatus, '/fire/status', self._on_status, 10)
        self.create_subscription(Odometry, '/odometry/filtered', self._on_odom, 10)

        if not self._enabled:
            self.get_logger().info('mqtt_bridge_node: enabled:=false — 연결 안 함(스텁)')
            return

        if mqtt is None:
            self.get_logger().error(
                'enabled:=true 인데 paho-mqtt 를 import 할 수 없음 (apt install python3-paho-mqtt)')
            return

        self._setup_mqtt()

        status_hz = self.get_parameter('status_rate_hz').value
        self.create_timer(1.0 / status_hz, self._publish_status)
        telem_hz = self.get_parameter('telemetry_rate_hz').value
        self.create_timer(1.0 / telem_hz, self._publish_telemetry)

    # ---------------- MQTT 연결 ----------------
    def _setup_mqtt(self):
        self._client = mqtt.Client(client_id=f'fire_bringup_{self._robot_id}')
        status_topic = self._adapter.map_status_topic(self._robot_id)
        offline_payload = json.dumps({'status': 'offline'}, ensure_ascii=False)
        self._client.will_set(status_topic, offline_payload, qos=0, retain=True)
        self._client.reconnect_delay_set(
            min_delay=self.get_parameter('reconnect_min_delay_s').value,
            max_delay=self.get_parameter('reconnect_max_delay_s').value)

        self._client.on_connect = self._on_mqtt_connect
        self._client.on_disconnect = self._on_mqtt_disconnect
        self._client.on_message = self._on_mqtt_message

        host = self.get_parameter('broker_host').value
        port = self.get_parameter('broker_port').value
        keepalive = self.get_parameter('keepalive_s').value
        try:
            self._client.connect_async(host, port, keepalive)
            self._client.loop_start()
            self.get_logger().info(f'mqtt_bridge_node: {host}:{port} 연결 시도 (robot_id={self._robot_id})')
        except Exception as e:
            self.get_logger().error(f'MQTT 연결 실패: {e}')

    def _on_mqtt_connect(self, client, userdata, flags, rc):
        self._connected = (rc == 0)
        if not self._connected:
            self.get_logger().warn(f'MQTT 연결 실패 rc={rc}')
            return
        self.get_logger().info('MQTT 연결됨')
        online_topic = self._adapter.map_status_topic(self._robot_id)
        client.publish(online_topic, json.dumps({'status': 'online'}, ensure_ascii=False),
                        qos=0, retain=True)
        cmd_topic = self._adapter.map_command_topic(self._robot_id)
        client.subscribe(cmd_topic, qos=1)
        self._flush_buffer()

    def _on_mqtt_disconnect(self, client, userdata, rc):
        self._connected = False
        self.get_logger().warn(f'MQTT 연결 끊김 rc={rc} — 재접속 시도 중, event 는 버퍼링됨')

    def _on_mqtt_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode('utf-8'))
            cmd = payload.get('cmd', '') if isinstance(payload, dict) else str(payload)
        except (ValueError, UnicodeDecodeError):
            cmd = msg.payload.decode('utf-8', errors='ignore').strip()
        self.get_logger().info(f'MQTT cmd 수신: {cmd}')
        # resume / pause / return_home(예약) -> ROS 로 중계. return_home 은 아직 mission_manager
        # 쪽에 대응 동작이 없어(STEP6 범위 밖) 로그만 남기고 topic 은 그대로 전달한다.
        self._cmd_pub.publish(String(data=cmd))

    # ---------------- ROS -> MQTT ----------------
    def _publish_or_buffer(self, topic: str, payload_dict: dict, qos: int, retain: bool = False):
        payload = json.dumps(payload_dict, ensure_ascii=False)
        if self._connected and self._client is not None:
            self._client.publish(topic, payload, qos=qos, retain=retain)
        else:
            self._buffer.append((topic, payload, qos, retain))

    def _flush_buffer(self):
        while self._buffer:
            topic, payload, qos, retain = self._buffer.popleft()
            self._client.publish(topic, payload, qos=qos, retain=retain)

    def _on_event(self, msg: String):
        if not self._enabled:
            return
        try:
            payload = json.loads(msg.data)
        except ValueError:
            payload = {'raw': msg.data}
        topic = self._adapter.map_event_topic(self._robot_id)
        payload = self._adapter.transform_payload('event', payload)
        self._publish_or_buffer(topic, payload, qos=1)

    def _on_status(self, msg: FireStatus):
        self._status = msg

    def _on_odom(self, msg: Odometry):
        self._odom = msg

    def _publish_status(self):
        if not self._enabled or self._status is None:
            return
        topic = self._adapter.map_status_topic(self._robot_id)
        payload = {
            'robot_id': self._robot_id,
            'stamp': datetime.now(timezone.utc).isoformat(),
            'status': 'online',
            'fire_state': self._status.fire_state,
            'mission_state': self._status.mission_state,
        }
        payload = self._adapter.transform_payload('status', payload)
        self._publish_or_buffer(topic, payload, qos=0, retain=True)

    def _publish_telemetry(self):
        if not self._enabled:
            return
        pose = {'x': 0.0, 'y': 0.0, 'yaw': 0.0}
        if self._odom is not None:
            p = self._odom.pose.pose.position
            pose = {'x': p.x, 'y': p.y}
        topic = self._adapter.map_telemetry_topic(self._robot_id)
        payload = {
            'robot_id': self._robot_id,
            'stamp': datetime.now(timezone.utc).isoformat(),
            'pose': {**pose, 'frame': self.get_parameter('map_frame').value},
            'battery': None,  # SIM ONLY: 시뮬에는 배터리 모델이 없어 자리만 예약
            'scores': {
                'fused': self._status.fused_score if self._status else 0.0,
                'vision': self._status.vision_score if self._status else 0.0,
                'thermal': self._status.thermal_score if self._status else 0.0,
                'gas': self._status.gas_score if self._status else 0.0,
            } if self._status else {},
        }
        payload = self._adapter.transform_payload('telemetry', payload)
        self._publish_or_buffer(topic, payload, qos=0)

    def destroy_node(self):
        if self._client is not None:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:
                pass
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = MqttBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
