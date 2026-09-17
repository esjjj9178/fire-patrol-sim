"""fusion_logic.FusionStateMachine 단위 테스트 (ROS 불필요, 순수 파이썬).
STEP6.md 완료 기준의 최소 5개 시나리오: 확정, 오탐 기각, 의심->확정, 의심 해제, 센서 끊김.
ema_alpha=1.0 으로 두어 평활 지연 없이 상태 전이 로직만 검증한다.
"""
from fire_fusion.fusion_logic import (STATE_CONFIRMED, STATE_FALSE_ALARM, STATE_NONE,
                                       STATE_SUSPECT, STATE_VERIFY, FusionStateMachine)

BASE_PARAMS = {
    'weights': {'vision': 0.4, 'thermal': 0.4, 'gas': 0.2},
    'ema_alpha': 1.0,
    'sensor_high': 0.5,
    'confirm_threshold': 0.7,
    'release_threshold': 0.4,
    'stale_timeout_s': 1.0,
    'verify_timeout_s': 6.0,
    'confirm_hold_s': 1.0,
    'false_alarm_radius_m': 1.5,
    'false_alarm_ignore_s': 60.0,
    'position_window': 5,
}


def det(conf, stamp=0.0, pos=None):
    return {'stamp': stamp, 'detected': conf >= 0.5, 'confidence': conf,
            'position': pos, 'position_valid': pos is not None}


def test_confirmed_needs_hold_duration():
    """vision+thermal 이 fused>=0.7 을 만족해도 confirm_hold_s 동안 유지되기 전엔 확정 안 됨."""
    fsm = FusionStateMachine(BASE_PARAMS)
    t = 0.0
    result = None
    for _ in range(4):  # 0.0~0.6s, confirm_hold_s=1.0 미달
        result = fsm.update(t, {'vision': det(0.9, stamp=t, pos=(1.0, 2.0)),
                                 'thermal': det(0.9, stamp=t)})
        t += 0.2
    assert result['fire_state'] != STATE_CONFIRMED

    for _ in range(6):  # 추가 1.2s -> 총 1.0s 이상 연속 유지
        result = fsm.update(t, {'vision': det(0.9, stamp=t, pos=(1.0, 2.0)),
                                 'thermal': det(0.9, stamp=t)})
        t += 0.2

    assert result['fire_state'] == STATE_CONFIRMED
    assert result['position_valid']
    assert result['fire_position'] == (1.0, 2.0)


def test_false_alarm_then_position_ignored_on_revisit():
    """VERIFY 상태에서 verify_timeout_s 동안 열/가스가 반응 안 하면 FALSE_ALARM -> NONE 이고,
    같은 위치(false_alarm_radius_m 이내) 재검출은 false_alarm_ignore_s 동안 VERIFY 로 가지 않는다."""
    fsm = FusionStateMachine(BASE_PARAMS)
    t = 0.0
    r = fsm.update(t, {'vision': det(0.9, stamp=t, pos=(3.0, 3.0))})
    assert r['fire_state'] == STATE_VERIFY

    t += 6.5  # verify_timeout_s(6.0) 초과
    r = fsm.update(t, {'vision': det(0.9, stamp=t, pos=(3.0, 3.0))})
    assert r['fire_state'] == STATE_FALSE_ALARM

    t += 0.2
    r = fsm.update(t, {'vision': det(0.9, stamp=t, pos=(3.0, 3.0))})
    assert r['fire_state'] == STATE_NONE

    t += 0.2  # 같은 위치 근처(0.22m) 재검출
    r = fsm.update(t, {'vision': det(0.9, stamp=t, pos=(3.2, 3.1))})
    assert r['fire_state'] == STATE_NONE


def test_suspect_then_confirmed_after_corner():
    """gas 만 반응(hidden_fire, 모퉁이 뒤)해서 SUSPECT 로 들어간 뒤, 모퉁이를 돌아 vision+thermal
    까지 반응하면 CONFIRMED 로 승격된다."""
    fsm = FusionStateMachine(BASE_PARAMS)
    t = 0.0
    r = fsm.update(t, {'gas': det(0.8, stamp=t)})
    assert r['fire_state'] == STATE_SUSPECT

    for _ in range(6):
        t += 0.2
        r = fsm.update(t, {'vision': det(0.9, stamp=t, pos=(-4.3, 0.6)),
                            'thermal': det(0.85, stamp=t)})
    assert r['fire_state'] == STATE_CONFIRMED


def test_suspect_released_when_scores_drop():
    """SUSPECT 진입 후 열/가스 점수가 release_threshold 아래로 떨어지면 NONE 으로 해제된다."""
    fsm = FusionStateMachine(BASE_PARAMS)
    t = 0.0
    r = fsm.update(t, {'gas': det(0.8, stamp=t)})
    assert r['fire_state'] == STATE_SUSPECT

    t += 0.2
    r = fsm.update(t, {'gas': det(0.05, stamp=t)})
    assert r['fire_state'] == STATE_NONE


def test_sensor_stale_emits_event_and_zeroes_score():
    """stale_timeout_s 동안 새 메시지가 없으면 SENSOR_STALE 이벤트가 나고 해당 점수는 0으로
    수렴하며, 그 결과로 SUSPECT 가 자동 해제될 수 있다."""
    fsm = FusionStateMachine(BASE_PARAMS)
    t = 0.0
    r = fsm.update(t, {'gas': det(0.9, stamp=t)})
    assert r['fire_state'] == STATE_SUSPECT
    assert r['gas_score'] == 0.9

    t += 1.5  # stale_timeout_s(1.0) 초과, 새 gas 메시지 없음
    r = fsm.update(t, {})
    assert 'SENSOR_STALE:gas' in r['events']
    assert r['gas_score'] == 0.0
    assert r['fire_state'] == STATE_NONE
