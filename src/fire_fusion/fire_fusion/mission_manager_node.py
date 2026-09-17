#!/usr/bin/env python3
"""역할: fire_state(fusion_node 판정)에 따라 로봇의 행동(mission_state)을 결정한다.
     PATROL(순찰+팬 SWEEP_FRONT) / SEARCH(정지+팬 SEARCH_360, SUSPECT 대응) /
     VERIFY(정지+팬 TRACK, 비전 단독검출 확인) / APPROACH(화재 앞 1.5m로 NavigateToPose) /
     HOLD(도착 후 정지+팬 TRACK, 사용자 resume 대기).
구독: /fire/status(FireStatus), /fire/vision/detection·/fire/thermal/detection·/fire/gas/detection
      (FireDetection - vision 은 TRACK 방위/SEARCH 중 발견용, thermal/gas 는 SENSOR_STALE 감시용),
      /camera_pan/search_done(Bool), /global_costmap/costmap(OccupancyGrid, APPROACH 목표 지점 판단),
      /patrol/cmd, /mission/cmd(String) - HOLD 에서 resume 수신용.
발행: /patrol/cmd(String), /camera_pan/mode(String), /camera_pan/track_bearing(Float32),
      /mission/state(String) - ARCHITECTURE.md 표에 없던 내부 배선 토픽. fusion_node 가
      FireStatus.mission_state 를 채우기 위해 구독한다(STEP6 구현 중 추가, ARCHITECTURE.md 3절 갱신).
      /fire/event(std_msgs/String, JSON) - STEP6.md 스키마 그대로. event 종류: FIRE_SUSPECT,
      FIRE_VERIFY, FIRE_CONFIRMED, FALSE_ALARM, ARRIVED_HOLD, PATROL_RESUMED, SENSOR_STALE.
파라미터: config/fusion.yaml 의 mission_manager_node 절.
"""
import json
import math
from datetime import datetime, timezone

import rclpy
import tf2_ros
from action_msgs.msg import GoalStatus
from fire_interfaces.msg import FireDetection, FireStatus
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import OccupancyGrid
from rcl_interfaces.msg import Parameter as ParameterMsg
from rcl_interfaces.msg import ParameterType, ParameterValue
from rcl_interfaces.srv import SetParameters
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.qos import (DurabilityPolicy, HistoryPolicy, QoSProfile,
                        ReliabilityPolicy)
from rclpy.time import Time
from std_msgs.msg import Bool, Float32, String


def _yaw_from_quaternion(qx, qy, qz, qw) -> float:
    return math.atan2(2.0 * (qw * qz + qx * qy), 1.0 - 2.0 * (qy * qy + qz * qz))


def _norm_angle(a: float) -> float:
    return math.atan2(math.sin(a), math.cos(a))


class MissionManagerNode(Node):

    def __init__(self):
        super().__init__('mission_manager_node')

        self.declare_parameter('robot_id', 'fire_bot_01')
        self.declare_parameter('map_frame', 'map')
        self.declare_parameter('base_frame', 'base_link')
        self.declare_parameter('stale_timeout_s', 1.0)
        self.declare_parameter('approach_distance_m', 1.5)
        self.declare_parameter('suspect_release_s', 15.0)
        self.declare_parameter('sensor_high', 0.5)
        self.declare_parameter('search_speed_scale', 0.5)
        self.declare_parameter('patrol_speed_scale', 1.0)
        self.declare_parameter('costmap_topic', '/global_costmap/costmap')
        self.declare_parameter('occupied_threshold', 50)
        self.declare_parameter('approach_candidates', 8)
        self.declare_parameter('watchdog_rate_hz', 2.0)
        self.declare_parameter('tracking_rate_hz', 5.0)
        self.declare_parameter('resume_ignore_s', 5.0)
        self.declare_parameter('track_lost_grace_s', 2.0)
        self.declare_parameter('max_approach_retries', 3)

        self._map_frame = self.get_parameter('map_frame').value
        self._base_frame = self.get_parameter('base_frame').value

        # ---- 상태 ----
        self._mission_state = 'PATROL'
        self._fire_state = 'NONE'
        self._fused = self._vision_score = self._thermal_score = self._gas_score = 0.0
        self._fire_position = None
        self._reason = ''
        self._camera_mode_cmd = None
        self._vision_bearing = None
        self._vision_last_seen = 0.0
        self._gas_low_since = None
        self._last_speed_scale = 1.0
        self._last_resolved_pos = None
        self._last_resolved_time = None
        self._last_seen = {'vision': None, 'thermal': None, 'gas': None}
        self._stale_prev = {'vision': True, 'thermal': True, 'gas': True}
        self._costmap = None
        self._nav_goal_in_flight = False
        self._approach_retries = 0

        # ---- 발행 ----
        self._patrol_cmd_pub = self.create_publisher(String, '/patrol/cmd', 10)
        self._cam_mode_pub = self.create_publisher(String, '/camera_pan/mode', 10)
        self._track_bearing_pub = self.create_publisher(Float32, '/camera_pan/track_bearing', 10)
        self._mission_state_pub = self.create_publisher(String, '/mission/state', 10)
        self._event_pub = self.create_publisher(String, '/fire/event', 10)

        # ---- 구독 ----
        self.create_subscription(FireStatus, '/fire/status', self._on_fire_status, 10)
        self.create_subscription(FireDetection, '/fire/vision/detection', self._on_vision_detection, 10)
        self.create_subscription(FireDetection, '/fire/thermal/detection',
                                  lambda m: self._mark_seen('thermal'), 10)
        self.create_subscription(FireDetection, '/fire/gas/detection',
                                  lambda m: self._mark_seen('gas'), 10)
        self.create_subscription(Bool, '/camera_pan/search_done', self._on_search_done, 10)
        self.create_subscription(String, '/patrol/cmd', self._on_external_cmd, 10)
        self.create_subscription(String, '/mission/cmd', self._on_external_cmd, 10)

        costmap_qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                                  durability=DurabilityPolicy.TRANSIENT_LOCAL,
                                  history=HistoryPolicy.KEEP_LAST)
        self.create_subscription(OccupancyGrid, self.get_parameter('costmap_topic').value,
                                  self._on_costmap, costmap_qos)

        # ---- TF / Nav2 액션 클라이언트 / 속도 파라미터 클라이언트 ----
        self._tf_buffer = tf2_ros.Buffer()
        self._tf_listener = tf2_ros.TransformListener(self._tf_buffer, self)
        self._nav_client = ActionClient(self, NavigateToPose, 'navigate_to_pose')
        self._patrol_param_client = self.create_client(SetParameters, '/patrol_node/set_parameters')

        self._camera_mode('SWEEP_FRONT')
        self._publish_mission_state()

        watchdog_hz = self.get_parameter('watchdog_rate_hz').value
        self.create_timer(1.0 / watchdog_hz, self._watchdog_tick)
        tracking_hz = self.get_parameter('tracking_rate_hz').value
        self.create_timer(1.0 / tracking_hz, self._tracking_tick)

        self.get_logger().info('mission_manager_node 시작 (PATROL)')

    # ---------------- 유틸 ----------------
    def _now(self) -> float:
        return self.get_clock().now().nanoseconds * 1e-9

    def _mark_seen(self, source: str):
        self._last_seen[source] = self._now()

    def _lookup_robot_xy(self):
        pose = self._lookup_robot_pose()
        return None if pose is None else (pose[0], pose[1])

    def _lookup_robot_pose(self):
        try:
            tf = self._tf_buffer.lookup_transform(self._map_frame, self._base_frame, Time())
        except Exception:
            return None
        t, q = tf.transform.translation, tf.transform.rotation
        return (t.x, t.y, _yaw_from_quaternion(q.x, q.y, q.z, q.w))

    def _camera_mode(self, mode: str):
        self._cam_mode_pub.publish(String(data=mode))
        self._camera_mode_cmd = mode

    def _patrol_cmd(self, cmd: str):
        self._patrol_cmd_pub.publish(String(data=cmd))

    def _publish_mission_state(self):
        self._mission_state_pub.publish(String(data=self._mission_state))

    def _set_speed_scale(self, scale: float):
        if abs(scale - self._last_speed_scale) < 1e-3:
            return
        self._last_speed_scale = scale
        if not self._patrol_param_client.service_is_ready():
            return
        req = SetParameters.Request()
        pv = ParameterValue(type=ParameterType.PARAMETER_DOUBLE, double_value=float(scale))
        req.parameters = [ParameterMsg(name='speed_scale', value=pv)]
        self._patrol_param_client.call_async(req)

    def _publish_event(self, event: str, reason: str = None):
        fx, fy = self._fire_position if self._fire_position else (0.0, 0.0)
        payload = {
            'robot_id': self.get_parameter('robot_id').value,
            'event': event,
            'stamp': datetime.now(timezone.utc).isoformat(),
            'fire_state': self._fire_state,
            'mission_state': self._mission_state,
            'position': {'x': fx, 'y': fy, 'frame': self._map_frame},
            'scores': {'fused': self._fused, 'vision': self._vision_score,
                       'thermal': self._thermal_score, 'gas': self._gas_score},
            'reason': reason if reason is not None else self._reason,
        }
        self._event_pub.publish(String(data=json.dumps(payload, ensure_ascii=False)))
        self.get_logger().info(f'/fire/event {event}: {payload["reason"]}')

    def _is_recently_resolved(self, now: float) -> bool:
        if self._last_resolved_pos is None or self._fire_position is None:
            return False
        if now - self._last_resolved_time > self.get_parameter('resume_ignore_s').value:
            return False
        dx = self._fire_position[0] - self._last_resolved_pos[0]
        dy = self._fire_position[1] - self._last_resolved_pos[1]
        return math.hypot(dx, dy) < self.get_parameter('approach_distance_m').value * 1.5

    # ---------------- 콜백 ----------------
    def _on_fire_status(self, msg: FireStatus):
        self._fused = msg.fused_score
        self._vision_score = msg.vision_score
        self._thermal_score = msg.thermal_score
        self._gas_score = msg.gas_score
        self._reason = msg.reason
        if msg.position_valid:
            self._fire_position = (msg.fire_position.x, msg.fire_position.y)

        prev, new = self._fire_state, msg.fire_state
        self._fire_state = new
        if new != prev:
            self._on_fire_state_changed(prev, new)

    def _on_fire_state_changed(self, prev: str, new: str):
        self.get_logger().info(f'fire_state 전이: {prev} -> {new} ({self._reason})')
        if new == 'VERIFY':
            self._enter_verify()
        elif new == 'SUSPECT':
            self._enter_search()
        elif new == 'CONFIRMED':
            if self._is_recently_resolved(self._now()):
                self.get_logger().info('최근 처리된 화재 위치 재확정 -> APPROACH 재진입 생략')
                return
            self._enter_approach()
        elif new == 'NONE':
            if self._mission_state in ('VERIFY', 'SEARCH'):
                self._return_to_patrol()
        elif new == 'FALSE_ALARM':
            self._publish_event('FALSE_ALARM')

    def _on_vision_detection(self, msg: FireDetection):
        now = self._now()
        self._last_seen['vision'] = now
        if msg.detected:
            self._vision_bearing = msg.bearing
            self._vision_last_seen = now
            if self._mission_state == 'SEARCH' and self._camera_mode_cmd != 'TRACK':
                self._camera_mode('TRACK')
                self._track_bearing_pub.publish(Float32(data=msg.bearing))

    def _on_search_done(self, msg: Bool):
        if not msg.data or self._mission_state != 'SEARCH' or self._camera_mode_cmd != 'SEARCH_360':
            return
        self.get_logger().info('SEARCH_360 완료, 미발견 -> 감속 순찰 재개 + 재탐색')
        self._patrol_cmd('resume')
        self._set_speed_scale(self.get_parameter('search_speed_scale').value)
        self._camera_mode('SEARCH_360')  # 같은 모드 재발행 -> camera_pan_node 가 재시작(아래 STEP4 수정 참고)

    def _on_external_cmd(self, msg: String):
        cmd = msg.data.strip().lower()
        if cmd == 'resume' and self._mission_state == 'HOLD':
            self._last_resolved_pos = self._fire_position
            self._last_resolved_time = self._now()
            self.get_logger().info('resume 명령 수신 -> 화재 처리됨으로 기록 후 PATROL 복귀')
            self._return_to_patrol()

    def _on_costmap(self, msg: OccupancyGrid):
        self._costmap = msg

    # ---------------- mission_state 전이 ----------------
    def _enter_verify(self):
        self._mission_state = 'VERIFY'
        self._publish_mission_state()
        self._patrol_cmd('pause')
        self._camera_mode('TRACK')
        self._publish_event('FIRE_VERIFY')

    def _enter_search(self):
        self._mission_state = 'SEARCH'
        self._publish_mission_state()
        self._patrol_cmd('pause')
        self._camera_mode('SEARCH_360')
        self._gas_low_since = None
        self._publish_event('FIRE_SUSPECT')

    def _enter_approach(self):
        self._mission_state = 'APPROACH'
        self._publish_mission_state()
        self._patrol_cmd('pause')
        self._approach_retries = 0
        self._nav_goal_in_flight = False
        self._publish_event('FIRE_CONFIRMED')

    def _enter_hold(self):
        self._mission_state = 'HOLD'
        self._publish_mission_state()
        self._camera_mode('TRACK')
        self._publish_event('ARRIVED_HOLD')

    def _return_to_patrol(self):
        was_active = self._mission_state != 'PATROL'
        self._mission_state = 'PATROL'
        self._publish_mission_state()
        self._camera_mode('SWEEP_FRONT')
        self._patrol_cmd('resume')
        self._set_speed_scale(self.get_parameter('patrol_speed_scale').value)
        if was_active:
            self._publish_event('PATROL_RESUMED')

    # ---------------- 주기 처리 ----------------
    def _tracking_tick(self):
        now = self._now()
        if self._mission_state == 'VERIFY':
            if self._vision_bearing is not None and (now - self._vision_last_seen) < 1.0:
                self._track_bearing_pub.publish(Float32(data=self._vision_bearing))
        elif self._mission_state == 'SEARCH' and self._camera_mode_cmd == 'TRACK':
            grace = self.get_parameter('track_lost_grace_s').value
            if self._vision_bearing is not None and (now - self._vision_last_seen) < grace:
                self._track_bearing_pub.publish(Float32(data=self._vision_bearing))
            else:
                self.get_logger().info('추적 대상 놓침 -> SEARCH_360 재개')
                self._camera_mode('SEARCH_360')
        elif self._mission_state == 'HOLD':
            robot = self._lookup_robot_pose()
            if robot is not None and self._fire_position is not None:
                rx, ry, ryaw = robot
                fx, fy = self._fire_position
                bearing = _norm_angle(math.atan2(fy - ry, fx - rx) - ryaw)
                self._track_bearing_pub.publish(Float32(data=bearing))

    def _watchdog_tick(self):
        now = self._now()
        stale_timeout = self.get_parameter('stale_timeout_s').value
        for s in ('vision', 'thermal', 'gas'):
            last = self._last_seen[s]
            stale = last is None or (now - last) > stale_timeout
            if stale and not self._stale_prev[s]:
                self._publish_event('SENSOR_STALE', reason=f'{s} 센서 {stale_timeout:.1f}s 이상 끊김')
            self._stale_prev[s] = stale

        if self._mission_state == 'SEARCH':
            high = self.get_parameter('sensor_high').value
            if self._gas_score < high:
                if self._gas_low_since is None:
                    self._gas_low_since = now
                elif now - self._gas_low_since >= self.get_parameter('suspect_release_s').value:
                    self._set_speed_scale(self.get_parameter('patrol_speed_scale').value)
            else:
                self._gas_low_since = None
                self._set_speed_scale(self.get_parameter('search_speed_scale').value)

        if self._mission_state == 'APPROACH' and not self._nav_goal_in_flight:
            self._try_send_approach_goal()

    # ---------------- APPROACH: NavigateToPose ----------------
    def _is_free(self, xy) -> bool:
        if self._costmap is None:
            return True
        info = self._costmap.info
        gx = int((xy[0] - info.origin.position.x) / info.resolution)
        gy = int((xy[1] - info.origin.position.y) / info.resolution)
        if gx < 0 or gy < 0 or gx >= info.width or gy >= info.height:
            return True
        val = self._costmap.data[gy * info.width + gx]
        if val < 0:
            return True
        return val < self.get_parameter('occupied_threshold').value

    def _compute_approach_pose(self, robot_xy) -> PoseStamped:
        fx, fy = self._fire_position
        approach_dist = self.get_parameter('approach_distance_m').value
        dx, dy = robot_xy[0] - fx, robot_xy[1] - fy
        base_angle = math.atan2(dy, dx) if math.hypot(dx, dy) > 1e-3 else 0.0
        candidate = (fx + approach_dist * math.cos(base_angle),
                     fy + approach_dist * math.sin(base_angle))

        if not self._is_free(candidate):
            n = self.get_parameter('approach_candidates').value
            best, best_d = None, float('inf')
            for k in range(n):
                ang = k * (2.0 * math.pi / n)
                cxy = (fx + approach_dist * math.cos(ang), fy + approach_dist * math.sin(ang))
                if self._is_free(cxy):
                    d = math.hypot(cxy[0] - robot_xy[0], cxy[1] - robot_xy[1])
                    if d < best_d:
                        best_d, best = d, cxy
            if best is not None:
                candidate = best
            else:
                self.get_logger().warn('APPROACH 후보 8곳 모두 막힘 - 원래 후보로 시도')

        yaw = math.atan2(fy - candidate[1], fx - candidate[0])
        pose = PoseStamped()
        pose.header.frame_id = self._map_frame
        pose.header.stamp = self.get_clock().now().to_msg()
        pose.pose.position.x, pose.pose.position.y = candidate
        pose.pose.orientation.z = math.sin(yaw / 2.0)
        pose.pose.orientation.w = math.cos(yaw / 2.0)
        return pose

    def _try_send_approach_goal(self):
        if self._fire_position is None:
            return
        robot_xy = self._lookup_robot_xy()
        if robot_xy is None:
            return
        if not self._nav_client.server_is_ready():
            return

        goal_msg = NavigateToPose.Goal()
        goal_msg.pose = self._compute_approach_pose(robot_xy)
        self._nav_goal_in_flight = True
        self.get_logger().info(
            f'APPROACH 목표 전송: ({goal_msg.pose.pose.position.x:.2f}, '
            f'{goal_msg.pose.pose.position.y:.2f})')
        future = self._nav_client.send_goal_async(goal_msg)
        future.add_done_callback(self._on_goal_response)

    def _on_goal_response(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().warn('NavigateToPose 목표 거부됨 - 다음 watchdog tick 에서 재시도')
            self._nav_goal_in_flight = False
            return
        result_future = goal_handle.get_result_future()
        result_future.add_done_callback(self._on_goal_result)

    def _on_goal_result(self, future):
        self._nav_goal_in_flight = False
        if self._mission_state != 'APPROACH':
            return
        status = future.result().status
        if status == GoalStatus.STATUS_SUCCEEDED:
            self._enter_hold()
            return
        self._approach_retries += 1
        max_retries = self.get_parameter('max_approach_retries').value
        if self._approach_retries > max_retries:
            self.get_logger().warn('APPROACH 재시도 초과 - 현재 위치에서 HOLD 전환(최선 노력)')
            self._enter_hold()
        else:
            self.get_logger().warn(
                f'APPROACH 실패(status={status}), 재시도 {self._approach_retries}/{max_retries}')


def main(args=None):
    rclpy.init(args=args)
    node = MissionManagerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
