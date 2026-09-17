"""gas_sim_node 의 농도 계산식(target_ppm)과 1차 지연 응답을 순수 함수로 검증한다
(ROS/시뮬 불필요)."""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fire_perception.gas_sim_node import target_ppm  # noqa: E402

REAL_FIRE = {'pose': {'x': 0.0, 'y': 0.0}, 'is_real': True, 'gas_strength': 1.0}
FAKE_FIRE = {'pose': {'x': 5.0, 'y': 5.0}, 'is_real': False, 'gas_strength': 0.0}
BASE, PEAK, SIGMA = 250.0, 1200.0, 1.5


def test_target_ppm_at_fire_is_base_plus_peak():
    ppm = target_ppm((0.0, 0.0), [REAL_FIRE], BASE, PEAK, SIGMA)
    assert abs(ppm - (BASE + PEAK)) < 1e-6


def test_target_ppm_decays_with_distance():
    near = target_ppm((0.5, 0.0), [REAL_FIRE], BASE, PEAK, SIGMA)
    far = target_ppm((5.0, 0.0), [REAL_FIRE], BASE, PEAK, SIGMA)
    assert near > far
    assert far == BASE + PEAK * math.exp(-25.0 / (2 * SIGMA ** 2))


def test_fake_fire_does_not_contribute_gas():
    ppm = target_ppm((5.0, 5.0), [FAKE_FIRE], BASE, PEAK, SIGMA)
    assert abs(ppm - BASE) < 1e-6


def test_far_from_all_fires_is_base():
    ppm = target_ppm((100.0, 100.0), [REAL_FIRE, FAKE_FIRE], BASE, PEAK, SIGMA)
    assert abs(ppm - BASE) < 1e-3


def _first_order_step(state: float, target: float, dt: float, tau: float) -> float:
    return state + (target - state) * min(dt / tau, 1.0)


def test_first_order_lag_approaches_target():
    state = BASE
    target = BASE + PEAK
    tau = 2.0
    for _ in range(150):  # 15s @ dt=0.1 (7.5*tau, 잔차 < 0.06%)
        state = _first_order_step(state, target, 0.1, tau)
    assert abs(state - target) < 2.0


def test_first_order_lag_does_not_jump_instantly():
    state = _first_order_step(BASE, BASE + PEAK, 0.1, 2.0)
    assert state < BASE + PEAK
    assert state > BASE
