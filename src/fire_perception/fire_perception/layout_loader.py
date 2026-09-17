"""역할: fire_world/config/warehouse_layout.yaml 을 읽는 공용 헬퍼.
     gas_sim_node/virtual_thermal_node(둘 다 SIM ONLY)가 불 위치/온도와 벽/선반 가림막
     정보를 얻는 데 사용한다. 단일 정의 파일 원칙(ARCHITECTURE.md)을 유지하기 위해
     레이아웃을 다시 정의하지 않고 이 파일 하나만 읽는다.
"""
from pathlib import Path
from typing import List

import yaml
from ament_index_python.packages import get_package_share_directory


def layout_path() -> Path:
    try:
        return Path(get_package_share_directory('fire_world')) / 'config' / 'warehouse_layout.yaml'
    except Exception:
        # 빌드 전 소스 트리에서 직접 실행하는 경우의 폴백
        return (Path(__file__).resolve().parents[4] / 'fire_world' / 'config'
                / 'warehouse_layout.yaml')


def load_layout(path: Path = None) -> dict:
    with open(path or layout_path(), 'r') as f:
        return yaml.safe_load(f)


def fire_elements(layout: dict) -> List[dict]:
    return [e for e in layout.get('elements', []) if e.get('type') == 'fire']


def occluder_elements(layout: dict) -> List[dict]:
    """가시선을 막는 요소(벽/선반)를 rect_corners 에 바로 쓸 수 있는 형태로 변환."""
    out = []
    for e in layout.get('elements', []):
        if e.get('type') not in ('wall', 'shelf'):
            continue
        pose = e['pose']
        size = e['size']
        out.append({'x': pose['x'], 'y': pose['y'], 'yaw': pose.get('yaw', 0.0),
                     'l': size['l'], 'w': size['w']})
    return out
