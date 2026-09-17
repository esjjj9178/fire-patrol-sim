"""geometry_los 를 warehouse_layout.yaml 의 실제 선반 좌표로 검증한다(ROS/시뮬 불필요)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fire_perception.geometry_los import has_line_of_sight  # noqa: E402

# fire_world/config/warehouse_layout.yaml 의 shelf_2 (y=0, l=8.0 x∈[-4,4], w=0.6)
SHELF_2 = {'x': 0.0, 'y': 0.0, 'yaw': 0.0, 'l': 8.0, 'w': 0.6}
OCCLUDERS = [SHELF_2]


def test_los_clear_when_no_shelf_between():
    # 로봇, 목표 모두 선반 남쪽(y<-0.3) -> 가려지지 않음
    assert has_line_of_sight((-2.0, -2.0), (2.0, -2.0), OCCLUDERS) is True


def test_los_blocked_through_shelf():
    # 선반을 관통하는 선분(남쪽 -> 북쪽, x=0 부근) -> 가려짐
    assert has_line_of_sight((0.0, -2.0), (0.0, 2.0), OCCLUDERS) is False


def test_los_blocked_when_endpoint_inside_shelf():
    # hidden_fire(-4.3, 0.6) 근처: 선반 서쪽 끝(-4.0)을 넘어간 지점에서 선반 내부로 겨냥
    assert has_line_of_sight((-6.0, -3.8), (0.0, 0.0), OCCLUDERS) is False


def test_los_clear_around_shelf_corner():
    # 선반 서쪽 끝(x=-4.0)을 돌아나간 지점끼리는 시야가 열림
    assert has_line_of_sight((-4.3, 0.6), (-4.3, -0.6), OCCLUDERS) is True
