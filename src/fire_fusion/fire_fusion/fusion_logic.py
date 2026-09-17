"""역할: 화재 판단 상태머신의 순수 로직(ROS 비의존). fusion_node.py 가 이를 얇게 감싸 ROS 노드로
     만든다. rclpy 없이 pytest 로 단위 테스트하기 위해 로직을 분리했다(ARCHITECTURE.md 6절, STEP6.md).

판정 규칙(ARCHITECTURE.md 6절 / STEP6.md 그대로):
  fused = weight_vision*vision + weight_thermal*thermal + weight_gas*gas (EMA 평활)
  NONE -> VERIFY   : vision 높음, thermal/gas 낮음 (무시 목록 안이면 진입 안 함)
  * -> CONFIRMED   : fused >= confirm_threshold and vision 높음 and (thermal 높음 or gas 높음),
                      이 조건이 confirm_hold_s 동안 연속 유지되어야 확정
  NONE -> SUSPECT  : vision 낮음 and (thermal 높음 or gas 높음)
  VERIFY -> FALSE_ALARM : verify_timeout_s 동안 확정 안 되면 기각, 위치를 무시 목록에 등록
                          (false_alarm_radius_m 반경, false_alarm_ignore_s 동안 그 근처 vision
                          단독검출은 VERIFY 로 진입하지 않음)
  해제(VERIFY/SUSPECT/CONFIRMED -> NONE) : release_threshold 히스테리시스
"""
import math
from collections import deque

STATE_NONE = 'NONE'
STATE_SUSPECT = 'SUSPECT'
STATE_VERIFY = 'VERIFY'
STATE_CONFIRMED = 'CONFIRMED'
STATE_FALSE_ALARM = 'FALSE_ALARM'

SOURCES = ('vision', 'thermal', 'gas')

DEFAULT_PARAMS = {
    'weights': {'vision': 0.4, 'thermal': 0.4, 'gas': 0.2},
    'ema_alpha': 0.3,
    'sensor_high': 0.5,
    'confirm_threshold': 0.7,
    'release_threshold': 0.4,
    'stale_timeout_s': 1.0,
    'verify_timeout_s': 6.0,
    'confirm_hold_s': 1.0,
    'false_alarm_radius_m': 1.5,
    'false_alarm_ignore_s': 60.0,
    'position_window': 10,
}


class FusionStateMachine:
    """센서별 FireDetection 스냅샷을 받아 fire_state 를 판정하는 순수 상태머신.

    update() 의 detections 인자 형식(소스별로 없으면 키 자체를 생략하거나 None):
      {'vision': {'stamp': float, 'detected': bool, 'confidence': float,
                   'position': (x, y) or None, 'position_valid': bool}, ...}
    """

    def __init__(self, params: dict = None):
        self.params = {**DEFAULT_PARAMS, **(params or {})}
        if 'weights' in (params or {}):
            self.params['weights'] = {**DEFAULT_PARAMS['weights'], **params['weights']}

        self.state = STATE_NONE
        self._ema = {s: 0.0 for s in SOURCES}
        self._last_stamp = {s: None for s in SOURCES}
        self._stale_prev = {s: True for s in SOURCES}
        self.stale_now = {s: True for s in SOURCES}

        self._confirm_since = None
        self._verify_since = None
        self._ignored = []  # [(x, y, until_time)]
        self._position_hist = deque(maxlen=int(self.params['position_window']))
        self._last_fire_position = None

    # ---------------- 내부 유틸 ----------------
    def _prune_ignored(self, now: float):
        self._ignored = [e for e in self._ignored if e[2] > now]

    def _in_ignore_list(self, pos) -> bool:
        r = self.params['false_alarm_radius_m']
        return any(math.hypot(pos[0] - x, pos[1] - y) <= r for (x, y, _) in self._ignored)

    def _estimate_position(self, detections: dict):
        vision = detections.get('vision')
        if vision and vision.get('position_valid') and vision.get('position'):
            return vision['position']
        thermal = detections.get('thermal')
        if thermal and thermal.get('position_valid') and thermal.get('position'):
            return thermal['position']
        return None

    def _average_position(self):
        if not self._position_hist:
            return self._last_fire_position
        xs = [p[0] for p in self._position_hist]
        ys = [p[1] for p in self._position_hist]
        avg = (sum(xs) / len(xs), sum(ys) / len(ys))
        self._last_fire_position = avg
        return avg

    # ---------------- 메인 ----------------
    def update(self, now: float, detections: dict) -> dict:
        events = []
        alpha = self.params['ema_alpha']
        stale_timeout = self.params['stale_timeout_s']
        high_th = self.params['sensor_high']

        for s in SOURCES:
            det = detections.get(s)
            if det is not None:
                self._last_stamp[s] = det['stamp']
            stale = (self._last_stamp[s] is None) or (now - self._last_stamp[s] > stale_timeout)
            self.stale_now[s] = stale
            if stale and not self._stale_prev[s]:
                events.append(f'SENSOR_STALE:{s}')
            self._stale_prev[s] = stale

            instant = 0.0
            if not stale and det is not None:
                instant = float(det.get('confidence', 0.0))
            elif not stale and det is None:
                # 이번 틱엔 새 메시지가 없었지만 아직 stale_timeout 이내 -> 직전 값 유지
                instant = self._ema[s]
            self._ema[s] = self._ema[s] + alpha * (instant - self._ema[s])

        vision, thermal, gas = self._ema['vision'], self._ema['thermal'], self._ema['gas']
        w = self.params['weights']
        fused = w['vision'] * vision + w['thermal'] * thermal + w['gas'] * gas

        vision_high = vision >= high_th
        thermal_high = thermal >= high_th
        gas_high = gas >= high_th

        position = self._estimate_position(detections)
        if position is not None:
            self._position_hist.append(position)
        avg_position = self._average_position()

        self._prune_ignored(now)
        ignored_here = avg_position is not None and self._in_ignore_list(avg_position)

        confirm_ok = (fused >= self.params['confirm_threshold'] and vision_high
                      and (thermal_high or gas_high))
        if confirm_ok:
            if self._confirm_since is None:
                self._confirm_since = now
        else:
            self._confirm_since = None

        prev_state = self.state
        new_state = prev_state
        reason = ''
        release_th = self.params['release_threshold']

        if confirm_ok and self._confirm_since is not None and \
                (now - self._confirm_since) >= self.params['confirm_hold_s']:
            new_state = STATE_CONFIRMED
            reason = (f'vision {vision:.2f} + thermal {thermal:.2f}/gas {gas:.2f} -> '
                      f'fused {fused:.2f} >= {self.params["confirm_threshold"]:.2f} '
                      f'({self.params["confirm_hold_s"]:.1f}s 유지) -> 확정')
        elif prev_state == STATE_NONE:
            if vision_high and not thermal_high and not gas_high and not ignored_here:
                new_state = STATE_VERIFY
                self._verify_since = now
                reason = f'vision {vision:.2f} 높음, 열/가스 낮음 -> 육안 검증(VERIFY) 진입'
            elif (not vision_high) and (thermal_high or gas_high):
                new_state = STATE_SUSPECT
                reason = f'vision {vision:.2f} 낮음, thermal {thermal:.2f}/gas {gas:.2f} 높음 -> 의심(SUSPECT)'
            elif ignored_here and vision_high:
                reason = f'무시 목록 반경 {self.params["false_alarm_radius_m"]:.1f}m 안 -> VERIFY 진입 안 함'
        elif prev_state == STATE_VERIFY:
            if not vision_high and fused < release_th:
                new_state = STATE_NONE
                reason = f'vision {vision:.2f} 하락, fused {fused:.2f} < {release_th:.2f} -> 해제'
            elif (now - (self._verify_since if self._verify_since is not None else now)) \
                    >= self.params['verify_timeout_s']:
                new_state = STATE_FALSE_ALARM
                if avg_position is not None:
                    self._ignored.append((avg_position[0], avg_position[1],
                                           now + self.params['false_alarm_ignore_s']))
                reason = (f'{self.params["verify_timeout_s"]:.0f}s 동안 열/가스 미반응 '
                          '-> 오탐(FALSE_ALARM) 기각, 위치 무시 목록 등록')
        elif prev_state == STATE_SUSPECT:
            if fused < release_th and not thermal_high and not gas_high:
                new_state = STATE_NONE
                reason = f'thermal {thermal:.2f}/gas {gas:.2f} 하락, fused {fused:.2f} < {release_th:.2f} -> 의심 해제'
        elif prev_state == STATE_CONFIRMED:
            if fused < release_th:
                new_state = STATE_NONE
                reason = f'fused {fused:.2f} < {release_th:.2f} -> 확정 해제'
        elif prev_state == STATE_FALSE_ALARM:
            # FALSE_ALARM 은 1틱만 유지하는 전이 상태 -> 바로 NONE 복귀(무시 목록은 별도 유지).
            new_state = STATE_NONE

        if new_state != prev_state:
            events.append(f'STATE:{prev_state}->{new_state}')
        self.state = new_state

        if not reason:
            reason = (f'vision {vision:.2f} thermal {thermal:.2f} gas {gas:.2f} '
                      f'fused {fused:.2f} (state={self.state})')

        return {
            'fire_state': self.state,
            'fused_score': fused,
            'vision_score': vision,
            'thermal_score': thermal,
            'gas_score': gas,
            'fire_position': avg_position,
            'position_valid': avg_position is not None,
            'reason': reason,
            'events': events,
            'stale': dict(self.stale_now),
        }
