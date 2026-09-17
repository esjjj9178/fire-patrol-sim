"""fire_world/config/warehouse_layout.yaml 의 waypoints 와
fire_navigation/config/waypoints.yaml 이 어긋나지 않았는지 정적으로 검사한다(ROS 노드 없이).
"""
from pathlib import Path

import yaml

PKG_ROOT = Path(__file__).resolve().parent.parent
LAYOUT_PATH = PKG_ROOT.parent / 'fire_world' / 'config' / 'warehouse_layout.yaml'
WAYPOINTS_PATH = PKG_ROOT / 'config' / 'waypoints.yaml'


def test_waypoints_match_layout():
    layout = yaml.safe_load(LAYOUT_PATH.read_text())
    waypoints_doc = yaml.safe_load(WAYPOINTS_PATH.read_text())

    layout_wps = layout['waypoints']
    synced_wps = waypoints_doc['waypoints']

    assert len(layout_wps) == len(synced_wps) >= 3, \
        'waypoints.yaml 이 warehouse_layout.yaml 과 개수가 다름 - sync_waypoints 재실행 필요'

    for lw, sw in zip(layout_wps, synced_wps):
        assert lw['name'] == sw['name']
        assert abs(float(lw['x']) - float(sw['x'])) < 1e-9
        assert abs(float(lw['y']) - float(sw['y'])) < 1e-9


def test_waypoints_not_too_close_to_walls_or_shelves():
    """월드 경계(±7.4, ±4.9)와 선반(±0.3+0.4 여유) 안쪽에 있는지 대략 검사."""
    layout = yaml.safe_load(LAYOUT_PATH.read_text())
    half_x = layout['world']['size']['x'] / 2.0 - layout['world']['wall_thickness']
    half_y = layout['world']['size']['y'] / 2.0 - layout['world']['wall_thickness']

    for wp in layout['waypoints']:
        assert -half_x < wp['x'] < half_x, f"{wp['name']} 가 월드 x범위를 벗어남"
        assert -half_y < wp['y'] < half_y, f"{wp['name']} 가 월드 y범위를 벗어남"
