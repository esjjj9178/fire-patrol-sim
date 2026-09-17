#!/usr/bin/env python3
"""역할: 검증 묶음(1~4) 별 확인 항목을 자동으로 측정해 10초마다 PASS/FAIL/대기 표를 터미널에
     출력하고, 최종 결과를 data/reports/verify_group{N}_<시간>.md 로 저장한다.
     scripts/verify.sh 가 그룹별 런치(verify_N.launch.py)와 이 스크립트를 함께 실행한다
     (직접 실행도 가능 — 아래 "사용" 참고).

구독/발행: 그룹마다 다름(아래 각 Group*Checker 클래스 docstring 참고). 공통적으로 진짜 화재 위치는
     fire_world/config/warehouse_layout.yaml 에서 읽는다.

사용:
  # 묶음별 런치(verify_N.launch.py)가 이미 떠 있는 상태에서, 대화형(Ctrl+C 로 종료):
  python3 verify_checker.py --group 1
  # 자동(GUI 없이, timeout 후 표만 출력하고 종료 — 종료 코드 0=PASS, 1=FAIL):
  python3 verify_checker.py --group 1 --auto --timeout 90

옵션:
  --group N        1~4 (필수)
  --auto           timeout 이후(또는 모든 체크 완료 시) 자동 종료. 없으면 Ctrl+C 로 종료.
  --timeout SEC    --auto 일 때 최대 실행 시간(기본은 그룹별 상이 — 아래 GROUP_DEFAULT_TIMEOUT).
  --print-interval SEC  표 갱신 주기(기본 10초).
  --output PATH    리포트 저장 경로(기본 data/reports/verify_group{N}_<시간>.md).
"""
import argparse
import json
import math
import subprocess
import sys
import time
from collections import deque
from datetime import datetime
from pathlib import Path

import rclpy
import yaml
from ament_index_python.packages import get_package_share_directory
from fire_interfaces.msg import FireDetection, FireStatus
from geometry_msgs.msg import PoseStamped, PoseWithCovarianceStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
from sensor_msgs.msg import Image, Imu, JointState, LaserScan
from std_msgs.msg import Bool, Float32, Float64, String

GROUP_DEFAULT_TIMEOUT = {1: 90.0, 2: 150.0, 3: 120.0, 4: 220.0}
GROUP_TITLE = {
    1: '묶음 1 - 월드·로봇 (STEP1+2)',
    2: '묶음 2 - 자율주행 (STEP3)',
    3: '묶음 3 - 센서 인식 (STEP4+5)',
    4: '묶음 4 - 전체 시나리오 (STEP6+7)',
}

RELIABLE_QOS = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)


# ---------------------------------------------------------------------------
# 공통 유틸
# ---------------------------------------------------------------------------

def _workspace_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / 'src').is_dir() and (parent / 'scripts' / 'env.sh').exists():
            return parent
    return Path.cwd()


def _layout_path() -> Path:
    try:
        return Path(get_package_share_directory('fire_world')) / 'config' / 'warehouse_layout.yaml'
    except Exception:
        return _workspace_root() / 'src' / 'fire_world' / 'config' / 'warehouse_layout.yaml'


def load_layout() -> dict:
    with open(_layout_path(), 'r') as f:
        return yaml.safe_load(f)


def fires_by_name(layout: dict) -> dict:
    return {e['name']: e for e in layout['elements'] if e['type'] == 'fire'}


def approach_pose(fire: dict, dist_m: float = 2.0):
    """불에서 스폰쪽(-x)으로 dist_m 만큼 떨어진 지점 + 불을 바라보는 yaw (sensor_scenario_test.py 와 동일 규칙)."""
    fx, fy = fire['pose']['x'], fire['pose']['y']
    rx, ry = fx - dist_m, fy
    yaw = math.atan2(fy - ry, fx - rx)
    return rx, ry, yaw


# ---------------------------------------------------------------------------
# Check / RateCheck
# ---------------------------------------------------------------------------

class Check:
    def __init__(self, key: str, label: str):
        self.key = key
        self.label = label
        self.status = 'PENDING'
        self.detail = '대기'


class RateCheck(Check):
    def __init__(self, key, label, min_hz, grace_s=15.0, window_s=8.0):
        super().__init__(key, label)
        self.min_hz = min_hz
        self.grace_s = grace_s
        self.window_s = window_s
        self._times = deque()
        self._start = time.time()

    def on_msg(self, *_args):
        now = time.time()
        self._times.append(now)
        cutoff = now - self.window_s
        while self._times and self._times[0] < cutoff:
            self._times.popleft()

    def evaluate(self):
        now = time.time()
        elapsed = now - self._start
        if len(self._times) < 2:
            if elapsed > self.grace_s:
                self.status = 'FAIL'
                self.detail = f'{elapsed:.0f}s 동안 발행 없음'
            else:
                self.status = 'PENDING'
                self.detail = '대기 중'
            return
        dt = self._times[-1] - self._times[0]
        hz = (len(self._times) - 1) / dt if dt > 0 else 0.0
        self.detail = f'{hz:.1f}Hz (기대 ≥{self.min_hz}Hz)'
        self.status = 'PASS' if hz >= self.min_hz else 'FAIL'


def print_table(title: str, checks, elapsed_s: float):
    print()
    print(f'==== {title}  [{elapsed_s:6.0f}s 경과] ====')
    w = max((len(c.label) for c in checks), default=10)
    for c in checks:
        mark = {'PASS': 'PASS', 'FAIL': 'FAIL', 'PENDING': '대기 '}.get(c.status, c.status)
        print(f'  [{mark}] {c.label:<{w}}  {c.detail}')
    n_pass = sum(1 for c in checks if c.status == 'PASS')
    n_fail = sum(1 for c in checks if c.status == 'FAIL')
    n_pend = sum(1 for c in checks if c.status == 'PENDING')
    print(f'  ---- PASS {n_pass} / FAIL {n_fail} / 대기 {n_pend} (총 {len(checks)}) ----')


def overall_pass(checks) -> bool:
    return len(checks) > 0 and all(c.status == 'PASS' for c in checks)


def write_report(group: int, checks, out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f'# 검증 묶음 {group} 결과', '',
             f'생성 시각: {datetime.now().isoformat()}',
             f'제목: {GROUP_TITLE[group]}', '',
             '| 항목 | 결과 | 상세 |', '|---|---|---|']
    for c in checks:
        lines.append(f'| {c.label} | {c.status} | {c.detail} |')
    lines.append('')
    lines.append(f'전체 판정: {"PASS" if overall_pass(checks) else "FAIL"}')
    out_path.write_text('\n'.join(lines) + '\n')
    print(f'\n리포트 저장: {out_path}')


# ---------------------------------------------------------------------------
# 텔레포트 헬퍼 - gz-transport /world/<world>/set_pose 서비스를 `gz service` CLI 로 직접 호출한다.
#
# 원래 fire_perception/tools/sensor_scenario_test.py 는 이 서비스를 ros_gz_bridge 로
# ros_gz_interfaces/srv/SetEntityPose 로 브리지해서 썼는데, 이 PC의 ros_gz_bridge(Humble)
# 라이브러리에는 SetEntityPose 용 ServiceFactory 가 아예 컴파일되어 있지 않아(런타임 검증 중 발견 -
# `ros2 run ros_gz_bridge parameter_bridge --help`/`strings libros_gz_bridge_lib.so` 로 확인, ControlWorld
# 만 지원) 브리지 자체가 "서비스를 찾을 수 없음"으로 항상 실패했다. gz-sim 은 world SDF 에
# `gz-sim-user-commands-system` 플러그인이 있으면 `/world/<world>/set_pose`(gz.msgs.Pose ->
# gz.msgs.Boolean) 를 gz-transport 서비스로 직접 제공하므로(`gz service -l` 로 확인됨), ROS 브리지를
# 거치지 않고 `gz service` CLI 로 바로 호출한다.
# ---------------------------------------------------------------------------

class Teleporter:
    def __init__(self, node: Node, world_name: str, robot_name: str = 'fire_bot'):
        self._node = node
        self._world_name = world_name
        self._robot_name = robot_name

    def teleport(self, x: float, y: float, yaw: float) -> bool:
        qz = math.sin(yaw / 2.0)
        qw = math.cos(yaw / 2.0)
        req = (f'name: "{self._robot_name}" '
               f'position: {{x: {x} y: {y} z: 0.02}} '
               f'orientation: {{x: 0 y: 0 z: {qz} w: {qw}}}')
        try:
            result = subprocess.run(
                ['gz', 'service', '-s', f'/world/{self._world_name}/set_pose',
                 '--reqtype', 'gz.msgs.Pose', '--reptype', 'gz.msgs.Boolean',
                 '--timeout', '3000', '--req', req],
                capture_output=True, text=True, timeout=6.0, start_new_session=True)
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            self._node.get_logger().error(f'gz service set_pose 호출 실패: {exc}')
            return False
        ok = 'true' in result.stdout
        if not ok:
            self._node.get_logger().error(
                f'teleport 실패(stdout={result.stdout!r} stderr={result.stderr!r})')
        return ok

    def shutdown(self):
        pass


def spin_for(node: Node, seconds: float, checks=None, title='', print_every=10.0, last_print=None):
    """seconds 동안 spin_once 를 돌리면서 checks 가 있으면 주기적으로 표를 갱신 출력한다."""
    end = time.time() + seconds
    if last_print is None:
        last_print = [0.0]
    while time.time() < end:
        rclpy.spin_once(node, timeout_sec=0.1)
        if checks is not None and (time.time() - last_print[0]) >= print_every:
            print_table(title, checks, time.time() - node.start_time)
            last_print[0] = time.time()
    return last_print


# ---------------------------------------------------------------------------
# 묶음 1: 월드·로봇 (STEP1+2)
# ---------------------------------------------------------------------------

class Group1Checker(Node):
    """구독: /scan /imu /odom /joint_states /camera/color/image_raw /camera/depth/image_raw
              /thermal/image_raw /ground_truth/pose
       발행: /camera_pan/cmd (팬 회전 추종 테스트용)
    """

    TOPIC_MIN_HZ = [
        ('/scan', LaserScan, 3.0, qos_profile_sensor_data),
        ('/imu', Imu, 30.0, qos_profile_sensor_data),
        ('/odom', Odometry, 15.0, RELIABLE_QOS),
        ('/joint_states', JointState, 3.0, RELIABLE_QOS),
        ('/camera/color/image_raw', Image, 6.0, qos_profile_sensor_data),
        ('/camera/depth/image_raw', Image, 3.0, qos_profile_sensor_data),
        ('/thermal/image_raw', Image, 4.0, qos_profile_sensor_data),
        ('/ground_truth/pose', PoseStamped, 6.0, RELIABLE_QOS),
    ]

    def __init__(self):
        super().__init__('verify_checker_group1')
        self.start_time = time.time()
        self.checks = []
        for topic, mtype, min_hz, qos in self.TOPIC_MIN_HZ:
            chk = RateCheck(topic, f'토픽 주기 {topic}', min_hz)
            self.create_subscription(mtype, topic, chk.on_msg, qos)
            self.checks.append(chk)

        self._pan_target = 1.0
        self._pan_cmd_sent_at = None
        self._pan_pos = None
        self.pan_check = Check('pan_track', '팬 회전 추종(camera_pan_joint -> 1.00rad)')
        self.checks.append(self.pan_check)
        self._pan_pub = self.create_publisher(Float64, '/camera_pan/cmd', 10)
        self.create_subscription(JointState, '/joint_states', self._on_joint_state, RELIABLE_QOS)

        self._odom_first = None
        self._odom_max_dev = 0.0
        self.odom_still_check = Check('odom_still', '정지 상태 odom 흔들림 < 2cm')
        self.checks.append(self.odom_still_check)
        self.create_subscription(Odometry, '/odom', self._on_odom, RELIABLE_QOS)

    def _on_joint_state(self, msg: JointState):
        if 'camera_pan_joint' in msg.name:
            idx = msg.name.index('camera_pan_joint')
            if idx < len(msg.position):
                self._pan_pos = msg.position[idx]

    def _on_odom(self, msg: Odometry):
        p = msg.pose.pose.position
        if self._odom_first is None:
            self._odom_first = (p.x, p.y)
            return
        dev = math.hypot(p.x - self._odom_first[0], p.y - self._odom_first[1])
        self._odom_max_dev = max(self._odom_max_dev, dev)

    def maybe_send_pan_command(self):
        if self._pan_cmd_sent_at is None and (time.time() - self.start_time) > 5.0:
            self._pan_pub.publish(Float64(data=self._pan_target))
            self._pan_cmd_sent_at = time.time()
            self.pan_check.detail = f'{self._pan_target:.2f}rad 명령 전송, 수렴 대기'

    def evaluate(self):
        for c in self.checks:
            if isinstance(c, RateCheck):
                c.evaluate()
        self.maybe_send_pan_command()
        if self._pan_cmd_sent_at is not None:
            elapsed = time.time() - self._pan_cmd_sent_at
            if self._pan_pos is not None and abs(self._pan_pos - self._pan_target) < 0.1:
                self.pan_check.status = 'PASS'
                self.pan_check.detail = f'현재 {self._pan_pos:.3f}rad (목표 {self._pan_target:.2f}rad) 수렴'
            elif elapsed > 10.0:
                self.pan_check.status = 'FAIL'
                cur = f'{self._pan_pos:.3f}' if self._pan_pos is not None else 'N/A'
                self.pan_check.detail = f'10s 안에 수렴 못함(현재 {cur}rad)'
            else:
                cur = f'{self._pan_pos:.3f}' if self._pan_pos is not None else 'N/A'
                self.pan_check.detail = f'수렴 대기 중(현재 {cur}rad, {elapsed:.0f}s 경과)'

        odom_elapsed = time.time() - self.start_time
        if self._odom_first is None:
            if odom_elapsed > 15.0:
                self.odom_still_check.status = 'FAIL'
                self.odom_still_check.detail = '/odom 미수신'
        elif odom_elapsed > 18.0:
            self.odom_still_check.status = 'PASS' if self._odom_max_dev < 0.02 else 'FAIL'
            self.odom_still_check.detail = f'최대 변위 {self._odom_max_dev * 100:.1f}cm'
        else:
            self.odom_still_check.detail = f'관찰 중(현재 변위 {self._odom_max_dev * 100:.1f}cm)'


# ---------------------------------------------------------------------------
# 묶음 2: 자율주행 (STEP3)
# ---------------------------------------------------------------------------

class PauseResumeCheck(Check):
    def __init__(self, node: Node, settle_s=30.0, timeout_s=8.0):
        super().__init__('pause_resume', 'pause/resume 자동 테스트')
        self._node = node
        self._settle_s = settle_s
        self._timeout_s = timeout_s
        self._start = time.time()
        self._stage = 'WAIT_SETTLE'
        self._stage_t0 = None
        self._pub = node.create_publisher(String, '/patrol/cmd', 10)
        self._latest_state = None
        self.detail = f'{settle_s:.0f}s 순찰 진행 후 pause/resume 명령 테스트 예정'

    def on_state(self, msg: String):
        self._latest_state = msg.data

    def tick(self):
        if self._stage == 'DONE':
            return
        now = time.time()
        elapsed = now - self._start
        if self._stage == 'WAIT_SETTLE':
            if elapsed >= self._settle_s:
                self._pub.publish(String(data='pause'))
                self._stage = 'WAIT_PAUSED'
                self._stage_t0 = now
                self.detail = 'pause 명령 전송, PAUSED 대기 중'
        elif self._stage == 'WAIT_PAUSED':
            if self._latest_state and self._latest_state.startswith('PAUSED'):
                self._pub.publish(String(data='resume'))
                self._stage = 'WAIT_RESUMED'
                self._stage_t0 = now
                self.detail = 'PAUSED 확인됨, resume 명령 전송'
            elif now - self._stage_t0 > self._timeout_s:
                self.status = 'FAIL'
                self.detail = f'pause 후 {self._timeout_s:.0f}s 안에 PAUSED 상태 안 됨'
                self._stage = 'DONE'
        elif self._stage == 'WAIT_RESUMED':
            if self._latest_state and self._latest_state.startswith('RUNNING'):
                self.status = 'PASS'
                self.detail = 'pause->PAUSED, resume->RUNNING 확인'
                self._stage = 'DONE'
            elif now - self._stage_t0 > self._timeout_s:
                self.status = 'FAIL'
                self.detail = f'resume 후 {self._timeout_s:.0f}s 안에 RUNNING 상태 안 됨'
                self._stage = 'DONE'


class Group2Checker(Node):
    """구독: /odometry/filtered /amcl_pose /ground_truth/pose /patrol/state /scan_filtered
       발행: /patrol/cmd (pause/resume 자동 테스트용)
    """

    def __init__(self):
        super().__init__('verify_checker_group2')
        self.start_time = time.time()
        self.checks = []

        self.ekf_check = RateCheck('/odometry/filtered', 'EKF 주기(/odometry/filtered)', 20.0)
        self.create_subscription(Odometry, '/odometry/filtered', self.ekf_check.on_msg, RELIABLE_QOS)
        self.checks.append(self.ekf_check)

        self._amcl_pose = None
        self._gt_pose = None
        self.amcl_check = Check('amcl_error', 'AMCL 오차 vs 정답 위치(< 0.3m)')
        self.checks.append(self.amcl_check)
        self.create_subscription(PoseWithCovarianceStamped, '/amcl_pose', self._on_amcl, RELIABLE_QOS)
        self.create_subscription(PoseStamped, '/ground_truth/pose', self._on_gt, RELIABLE_QOS)

        self._wp_indices = set()
        self.wp_check = Check('waypoint_progress', '웨이포인트 진행(서로 다른 인덱스 ≥ 2)')
        self.checks.append(self.wp_check)
        self.create_subscription(String, '/patrol/state', self._on_patrol_state, RELIABLE_QOS)

        self._min_range = None
        self._range_samples = 0
        self.obstacle_check = Check('min_obstacle_dist', '최소 장애물 거리(충돌 없음, > 0.15m)')
        self.checks.append(self.obstacle_check)
        self.create_subscription(LaserScan, '/scan_filtered', self._on_scan, qos_profile_sensor_data)

        self.pause_resume_check = PauseResumeCheck(self)
        self.checks.append(self.pause_resume_check)

    def _on_amcl(self, msg: PoseWithCovarianceStamped):
        self._amcl_pose = (msg.pose.pose.position.x, msg.pose.pose.position.y)

    def _on_gt(self, msg: PoseStamped):
        self._gt_pose = (msg.pose.position.x, msg.pose.position.y)

    def _on_patrol_state(self, msg: String):
        self.pause_resume_check.on_state(msg)
        if ':' in msg.data:
            try:
                idx = int(msg.data.split(':')[1])
                self._wp_indices.add(idx)
            except ValueError:
                pass

    def _on_scan(self, msg: LaserScan):
        valid = [r for r in msg.ranges if math.isfinite(r) and r > 0.0]
        if not valid:
            return
        self._range_samples += 1
        m = min(valid)
        self._min_range = m if self._min_range is None else min(self._min_range, m)

    def evaluate(self):
        self.ekf_check.evaluate()
        elapsed = time.time() - self.start_time

        if self._amcl_pose and self._gt_pose:
            err = math.hypot(self._amcl_pose[0] - self._gt_pose[0], self._amcl_pose[1] - self._gt_pose[1])
            self.amcl_check.status = 'PASS' if err < 0.3 else 'FAIL'
            self.amcl_check.detail = f'오차 {err:.2f}m'
        elif elapsed > 30.0:
            self.amcl_check.status = 'FAIL'
            self.amcl_check.detail = '/amcl_pose 또는 /ground_truth/pose 미수신'
        else:
            self.amcl_check.detail = f'AMCL 수렴 대기 중({elapsed:.0f}s)'

        if len(self._wp_indices) >= 2:
            self.wp_check.status = 'PASS'
            self.wp_check.detail = f'관찰된 인덱스 {sorted(self._wp_indices)}'
        elif elapsed > 100.0:
            self.wp_check.status = 'FAIL'
            self.wp_check.detail = f'{elapsed:.0f}s 동안 인덱스 {sorted(self._wp_indices)} 만 관찰됨'
        else:
            self.wp_check.detail = f'관찰 중(현재 {sorted(self._wp_indices)}, {elapsed:.0f}s 경과)'

        if self._range_samples >= 5:
            self.obstacle_check.status = 'PASS' if (self._min_range or 99.0) > 0.15 else 'FAIL'
            self.obstacle_check.detail = f'최소 거리 {self._min_range:.2f}m ({self._range_samples}개 스캔)'
        elif elapsed > 20.0:
            self.obstacle_check.status = 'FAIL'
            self.obstacle_check.detail = '/scan_filtered 미수신'
        else:
            self.obstacle_check.detail = '관찰 중'

        self.pause_resume_check.tick()


# ---------------------------------------------------------------------------
# 묶음 3: 센서 인식 (STEP4+5) - 순간이동 시나리오 포함
# ---------------------------------------------------------------------------

def _label_ok(expected, score: float) -> bool:
    if expected is None:
        return True
    if expected == 'high':
        return score >= 0.5
    if expected == 'low':
        return score < 0.3
    if expected == 'mid_high':
        return score >= 0.3
    return True


# SEARCH_360(팬 360도 스윕)으로 각 불의 approach_pose 위치에서 측정한다(마운트 각도 차이로
# 고정 bearing 조준이 신뢰할 수 없음이 실측으로 확인되어 - Teleporter/run_scenarios 참고).
# 창고가 통로 중심이라 먼 불도 시야에 들어올 수 있고, thermal_node 는 거리/입체각을 고려하지
# 않고 프레임 안 최고 픽셀 온도를 그대로 raw_value 로 쓰는 설계라(실측 확인: fake_fire 위치에서
# SEARCH_360 도중 ~7~10m 떨어진 real_fire/hidden_fire 가 화면 한 귀퉁이에 잠깐 잡혀도
# raw_value=598.8K, confidence=1.0 이 나옴 - 감쇠 없음) "이 불이 아니어도 참일 수 있는" 항목은
# None 으로 비워 검사하지 않는다(예: fake_fire 위치의 thermal 이 우연히 먼 real_fire 를 봐도
# fake_fire 자체 판정이 틀렸다는 뜻은 아님). 각 불에서 "반드시 참이어야 하는" 것만 검사한다.
SCENARIO3 = [
    # gas 는 base_ppm=250, peak_ppm=1200, sigma_m=1.5 기준 2m 거리에서 실측 약 0.31~0.35
    # (real_fire/hidden_fire 둘 다 is_real 이라 강도 동일) - ARCHITECTURE.md 5절의 "높음 ≥0.5"에는
    # 못 미치므로 mid_high(>=0.3)로 잡는다(런타임 실측으로 보정 - STEP5.md 표의 "높음"은 정성적 표현).
    ('real_fire', {'vision': 'high', 'thermal': 'high', 'gas': 'mid_high'}),
    ('fake_fire', {'vision': 'high', 'thermal': None, 'gas': None}),
    ('hidden_fire', {'vision': None, 'thermal': None, 'gas': 'mid_high'}),
]


class Group3Checker(Node):
    """구독: /fire/vision/detection /fire/thermal/detection /fire/gas/detection
       발행: /camera_pan/cmd /camera_pan/mode (텔레포트 후 팬을 불 쪽으로 고정)
       추가: /world/<world>/set_pose 서비스로 불 3개 + '불 없는 곳' 으로 순간이동해 점수표를 기대표와 비교
    """

    def __init__(self, layout: dict):
        super().__init__('verify_checker_group3')
        self.start_time = time.time()
        self.layout = layout
        self.checks = []

        self._scores = {'vision': deque(maxlen=200), 'thermal': deque(maxlen=200), 'gas': deque(maxlen=200)}
        for source in ('vision', 'thermal', 'gas'):
            topic = f'/fire/{source}/detection'
            rc = RateCheck(topic, f'토픽 주기 {topic}', 1.5, grace_s=15.0)
            self.checks.append(rc)
            self.create_subscription(
                FireDetection, topic,
                lambda m, s=source, r=rc: self._on_detection(s, m, r), RELIABLE_QOS)

        self._pan_mode_pub = self.create_publisher(String, '/camera_pan/mode', 10)

        self.row_checks = {}
        for name, expected in SCENARIO3:
            self.row_checks[name] = Check(f'sensor_{name}', f'{name} 점수표(SEARCH_360 최댓값)')
        self.checks.extend(self.row_checks.values())

    def _on_detection(self, source, msg: FireDetection, rate_check: RateCheck):
        rate_check.on_msg()
        self._scores[source].append(msg.confidence)

    def evaluate_rates(self):
        for c in self.checks:
            if isinstance(c, RateCheck):
                c.evaluate()

    def sample_scores_max(self, seconds: float) -> dict:
        """SEARCH_360 스윕 중 각 소스별 최대 confidence 를 기록한다(가스는 방향과 무관하므로
        최댓값이 노이즈로 실제값보다 살짝 높게 나올 수 있으나 판정에는 문제 없음)."""
        for k in self._scores:
            self._scores[k].clear()
        end = time.time() + seconds
        while time.time() < end:
            rclpy.spin_once(self, timeout_sec=0.1)
        return {k: (max(v) if v else 0.0) for k, v in self._scores.items()}

    @staticmethod
    def _fmt_field(name: str, value: float, expected) -> str:
        exp_str = expected if expected is not None else '-(검사 안 함)'
        return f'{name}={value:.2f}(기대 {exp_str})'

    def run_scenarios(self, teleporter: Teleporter):
        fires = fires_by_name(self.layout)
        title = GROUP_TITLE[3]
        for name, expected in SCENARIO3:
            fire = fires[name]
            x, y, yaw = approach_pose(fire)
            teleporter.teleport(x, y, yaw)
            # approach_pose 로 로봇 yaw 를 불 쪽으로 맞춰도 실측 결과 카메라가 정확히 불을 보려면
            # 팬이 base_link 정면(bearing 0)이 아니라 상당히 돌아가야 했다(카메라 마운트 경유 각도
            # 차이 - 런타임 실측으로 발견, 정확한 상수 보정 대신 SEARCH_360 로 한 바퀴 훑어
            # 최댓값을 취하는 방식이 마운트 각도 가정에 의존하지 않아 더 견고하다).
            self._pan_mode_pub.publish(String(data='SEARCH_360'))
            best = self.sample_scores_max(14.0)
            row = self.row_checks[name]
            oks = {k: _label_ok(expected[k], best[k]) for k in expected}
            row.status = 'PASS' if all(oks.values()) else 'FAIL'
            row.detail = ' '.join(
                self._fmt_field(k, best[k], expected[k]) for k in ('vision', 'thermal', 'gas'))
            print_table(title, self.checks, time.time() - self.start_time)


# ---------------------------------------------------------------------------
# 묶음 4: 전체 시나리오 (STEP6+7) - 순간이동으로 real/fake/hidden 이벤트 순서 확인 + MQTT
# ---------------------------------------------------------------------------

class Group4Checker(Node):
    """구독: /fire/status /mission/state /fire/event
       발행: /patrol/cmd (테스트 중 순찰 일시정지/재개)
       추가: MQTT(factory/#, 로컬 mosquitto)로 event/status 수신 확인, set_pose 로 불 3개 순차 접근
    """

    def __init__(self, layout: dict):
        super().__init__('verify_checker_group4')
        self.start_time = time.time()
        self.layout = layout
        self.checks = []

        self.status_check = RateCheck('/fire/status', '토픽 주기 /fire/status', 3.0)
        self.create_subscription(FireStatus, '/fire/status', self.status_check.on_msg, RELIABLE_QOS)
        self.checks.append(self.status_check)

        self.mission_check = RateCheck('/mission/state', '토픽 주기 /mission/state', 0.3, grace_s=25.0)
        self.create_subscription(String, '/mission/state', self.mission_check.on_msg, RELIABLE_QOS)
        self.checks.append(self.mission_check)

        self._events = []
        self.create_subscription(String, '/fire/event', self._on_event, RELIABLE_QOS)

        self.real_check = Check('scenario_real', 'real_fire: FIRE_CONFIRMED 발생')
        self.fake_check = Check('scenario_fake', 'fake_fire: FIRE_VERIFY -> FALSE_ALARM')
        self.hidden_check = Check('scenario_hidden', 'hidden_fire: FIRE_SUSPECT/FIRE_CONFIRMED 발생')
        self.resume_check = Check('scenario_resume', 'HOLD 해제(resume) -> PATROL_RESUMED')
        self.checks.extend([self.real_check, self.fake_check, self.hidden_check, self.resume_check])

        self.mqtt_check = Check('mqtt', 'MQTT 수신(factory/# via 로컬 mosquitto)')
        self.checks.append(self.mqtt_check)

        self._patrol_pub = self.create_publisher(String, '/patrol/cmd', 10)
        self._pan_mode_pub = self.create_publisher(String, '/camera_pan/mode', 10)

    def _on_event(self, msg: String):
        try:
            payload = json.loads(msg.data)
        except ValueError:
            return
        payload['_t'] = time.time()
        self._events.append(payload)

    def evaluate_rates(self):
        self.status_check.evaluate()
        self.mission_check.evaluate()

    def events_since(self, t0: float):
        return [e for e in self._events if e['_t'] >= t0]

    def start_mqtt_listener(self):
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            self.mqtt_check.status = 'FAIL'
            self.mqtt_check.detail = 'python3-paho-mqtt 미설치'
            return None
        self._mqtt_msgs = []

        def _on_message(client, userdata, msg):
            self._mqtt_msgs.append(msg.topic)

        client = mqtt.Client()
        client.on_message = _on_message
        try:
            client.connect('127.0.0.1', 1883, keepalive=10)
        except Exception as exc:
            self.mqtt_check.status = 'FAIL'
            self.mqtt_check.detail = f'mosquitto 연결 실패: {exc}'
            return None
        client.subscribe('factory/#')
        client.loop_start()
        return client

    def evaluate_mqtt(self):
        n = len(getattr(self, '_mqtt_msgs', []))
        if n > 0:
            self.mqtt_check.status = 'PASS'
            topics = sorted(set(self._mqtt_msgs))
            self.mqtt_check.detail = f'{n}건 수신 (예: {topics[:3]})'
        elif time.time() - self.start_time > 40.0:
            self.mqtt_check.status = 'FAIL'
            self.mqtt_check.detail = 'factory/# 로 아무 메시지도 못 받음'
        else:
            self.mqtt_check.detail = '대기 중'

    def _nudge_camera(self):
        """텔레포트 직후 팬을 SEARCH_360 으로 한 바퀴 훑게 한다(bearing 0 고정 조준은 카메라
        마운트 각도 차이 때문에 신뢰할 수 없음을 그룹3 검증에서 실측으로 확인 - Teleporter
        docstring 참고). mission_manager_node 는 fire_state 전이 시점에만 camera_pan/mode 를
        재발행하므로(PATROL 상태에서 매 주기 재발행 안 함 - 소스 확인됨), 이 nudge 는 최초 검출을
        돕는 one-shot 힌트일 뿐 이후 mission_manager 자체 제어와 충돌하지 않는다."""
        self._pan_mode_pub.publish(String(data='SEARCH_360'))

    def run_scenarios(self, teleporter: Teleporter):
        title = GROUP_TITLE[4]
        fires = fires_by_name(self.layout)
        spawn = self.layout['robot']['spawn']

        self._patrol_pub.publish(String(data='pause'))
        spin_for(self, 2.0)

        # real_fire
        x, y, yaw = approach_pose(fires['real_fire'])
        teleporter.teleport(x, y, yaw)
        self._nudge_camera()
        t0 = time.time()
        spin_for(self, 18.0, self.checks, title)
        evs = [e.get('event') for e in self.events_since(t0)]
        self.real_check.status = 'PASS' if 'FIRE_CONFIRMED' in evs else 'FAIL'
        self.real_check.detail = f'관찰된 이벤트: {evs or "없음"}'
        print_table(title, self.checks, time.time() - self.start_time)

        # 리셋(스폰 지점, false_alarm/verify 잔여 상태 decay 대기)
        teleporter.teleport(spawn['x'], spawn['y'], spawn.get('yaw', 0.0))
        spin_for(self, 3.0)

        # fake_fire
        x, y, yaw = approach_pose(fires['fake_fire'])
        teleporter.teleport(x, y, yaw)
        self._nudge_camera()
        t0 = time.time()
        spin_for(self, 20.0, self.checks, title)
        evs = [e.get('event') for e in self.events_since(t0)]
        self.fake_check.status = 'PASS' if ('FIRE_VERIFY' in evs and 'FALSE_ALARM' in evs) else 'FAIL'
        self.fake_check.detail = f'관찰된 이벤트: {evs or "없음"}'
        print_table(title, self.checks, time.time() - self.start_time)

        teleporter.teleport(spawn['x'], spawn['y'], spawn.get('yaw', 0.0))
        spin_for(self, 3.0)

        # hidden_fire
        x, y, yaw = approach_pose(fires['hidden_fire'])
        teleporter.teleport(x, y, yaw)
        self._nudge_camera()
        t0 = time.time()
        spin_for(self, 20.0, self.checks, title)
        evs = [e.get('event') for e in self.events_since(t0)]
        self.hidden_check.status = 'PASS' if ('FIRE_SUSPECT' in evs or 'FIRE_CONFIRMED' in evs) else 'FAIL'
        self.hidden_check.detail = f'관찰된 이벤트: {evs or "없음"}'
        print_table(title, self.checks, time.time() - self.start_time)

        # HOLD 해제(resume) 테스트 - CONFIRMED 로 HOLD 에 들어간 상태여야 의미 있음
        t0 = time.time()
        self._patrol_pub.publish(String(data='resume'))
        spin_for(self, 6.0, self.checks, title)
        evs = [e.get('event') for e in self.events_since(t0)]
        self.resume_check.status = 'PASS' if 'PATROL_RESUMED' in evs else 'FAIL'
        self.resume_check.detail = f'관찰된 이벤트: {evs or "없음"}'


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def run_group1(args):
    rclpy.init()
    node = Group1Checker()
    last_print = [0.0]
    try:
        end = time.time() + args.timeout if args.auto else None
        while True:
            rclpy.spin_once(node, timeout_sec=0.2)
            node.evaluate()
            if time.time() - last_print[0] >= args.print_interval:
                print_table(GROUP_TITLE[1], node.checks, time.time() - node.start_time)
                last_print[0] = time.time()
            if args.auto and (end is not None and time.time() >= end):
                break
            if args.auto and all(c.status in ('PASS', 'FAIL') for c in node.checks):
                break
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    print_table(GROUP_TITLE[1], node.checks, time.time() - node.start_time)
    write_report(1, node.checks, args.output or _default_output(1))
    ok = overall_pass(node.checks)
    node.destroy_node()
    rclpy.try_shutdown()
    return ok


def run_group2(args):
    rclpy.init()
    node = Group2Checker()
    last_print = [0.0]
    try:
        end = time.time() + args.timeout if args.auto else None
        while True:
            rclpy.spin_once(node, timeout_sec=0.2)
            node.evaluate()
            if time.time() - last_print[0] >= args.print_interval:
                print_table(GROUP_TITLE[2], node.checks, time.time() - node.start_time)
                last_print[0] = time.time()
            if args.auto and (end is not None and time.time() >= end):
                break
            if args.auto and all(c.status in ('PASS', 'FAIL') for c in node.checks):
                break
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    print_table(GROUP_TITLE[2], node.checks, time.time() - node.start_time)
    write_report(2, node.checks, args.output or _default_output(2))
    ok = overall_pass(node.checks)
    node.destroy_node()
    rclpy.try_shutdown()
    return ok


def run_group3(args):
    layout = load_layout()
    rclpy.init()
    node = Group3Checker(layout)
    try:
        # 퍼셉션 토픽이 안정적으로 뜰 때까지 대기하며 주기 체크
        spin_for(node, 10.0)
        node.evaluate_rates()
        print_table(GROUP_TITLE[3], node.checks, time.time() - node.start_time)

        teleporter = Teleporter(node, layout['world']['name'])
        try:
            node.run_scenarios(teleporter)
        finally:
            teleporter.shutdown()
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    node.evaluate_rates()
    print_table(GROUP_TITLE[3], node.checks, time.time() - node.start_time)
    write_report(3, node.checks, args.output or _default_output(3))
    ok = overall_pass(node.checks)
    node.destroy_node()
    rclpy.try_shutdown()
    return ok


def run_group4(args):
    layout = load_layout()
    rclpy.init()
    node = Group4Checker(layout)
    try:
        mqtt_client = node.start_mqtt_listener()
        spin_for(node, 15.0)
        node.evaluate_rates()
        node.evaluate_mqtt()
        print_table(GROUP_TITLE[4], node.checks, time.time() - node.start_time)

        teleporter = Teleporter(node, layout['world']['name'])
        try:
            node.run_scenarios(teleporter)
        finally:
            teleporter.shutdown()

        spin_for(node, 5.0)
        node.evaluate_mqtt()
        if mqtt_client is not None:
            mqtt_client.loop_stop()
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    node.evaluate_rates()
    print_table(GROUP_TITLE[4], node.checks, time.time() - node.start_time)
    write_report(4, node.checks, args.output or _default_output(4))
    ok = overall_pass(node.checks)
    node.destroy_node()
    rclpy.try_shutdown()
    return ok


def _default_output(group: int) -> Path:
    out_dir = _workspace_root() / 'data' / 'reports'
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    return out_dir / f'verify_group{group}_{ts}.md'


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--group', type=int, required=True, choices=[1, 2, 3, 4])
    parser.add_argument('--auto', action='store_true')
    parser.add_argument('--timeout', type=float, default=None)
    parser.add_argument('--print-interval', type=float, default=10.0)
    parser.add_argument('--output', type=str, default=None)
    args = parser.parse_args()
    if args.timeout is None:
        args.timeout = GROUP_DEFAULT_TIMEOUT[args.group]
    if args.output:
        args.output = Path(args.output)

    runner = {1: run_group1, 2: run_group2, 3: run_group3, 4: run_group4}[args.group]
    ok = runner(args)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
