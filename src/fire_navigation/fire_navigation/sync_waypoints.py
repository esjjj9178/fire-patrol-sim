#!/usr/bin/env python3
"""역할: fire_world/config/warehouse_layout.yaml 의 waypoints 를 유일한 정의로 삼아
       fire_navigation/config/waypoints.yaml 을 생성/동기화한다(웨이포인트는 한 곳에서만 관리).
구독: 없음 (파일 입출력 전용 CLI 도구)
발행: 없음
파라미터: 없음 (인자: --check 이면 파일을 고치지 않고 최신 상태인지만 검사)

사용:
  ros2 run fire_navigation sync_waypoints             # waypoints.yaml 갱신
  ros2 run fire_navigation sync_waypoints --check      # 최신 상태인지 검사만 (CI/빌드용)
"""
import argparse
import sys
from pathlib import Path

import yaml
from ament_index_python.packages import get_package_share_directory


def _layout_path() -> Path:
    return Path(get_package_share_directory('fire_world')) / 'config' / 'warehouse_layout.yaml'


def _output_path() -> Path:
    # 개발 중(빌드 전) 소스 트리에서 실행되는 경우를 위해, 이 파일 기준 상대 경로도 시도한다.
    try:
        return Path(get_package_share_directory('fire_navigation')) / 'config' / 'waypoints.yaml'
    except Exception:
        return Path(__file__).resolve().parent.parent / 'config' / 'waypoints.yaml'


def build_waypoints_doc(layout: dict) -> dict:
    wps = layout.get('waypoints', [])
    out = {
        'waypoints': [
            {'name': wp['name'], 'x': float(wp['x']), 'y': float(wp['y']), 'yaw': float(wp.get('yaw', 0.0))}
            for wp in wps
        ],
        # SIM ONLY 아님: 실차에서도 동일 맵을 쓰는 한 유효
        'source': 'fire_world/config/warehouse_layout.yaml (자동 생성 - 직접 수정 금지, sync_waypoints 로 갱신)',
    }
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true',
                         help='waypoints.yaml 이 warehouse_layout.yaml 과 일치하는지만 검사')
    parser.add_argument('--layout', default=None, help='warehouse_layout.yaml 경로 강제 지정')
    parser.add_argument('--output', default=None, help='waypoints.yaml 출력 경로 강제 지정')
    args = parser.parse_args()

    layout_path = Path(args.layout) if args.layout else _layout_path()
    output_path = Path(args.output) if args.output else _output_path()

    with open(layout_path) as f:
        layout = yaml.safe_load(f)

    new_doc = build_waypoints_doc(layout)
    new_text = yaml.safe_dump(new_doc, allow_unicode=True, sort_keys=False)

    if args.check:
        if not output_path.exists():
            print(f'FAIL: {output_path} 없음. sync_waypoints 실행 필요.')
            sys.exit(1)
        current_text = output_path.read_text()
        if current_text != new_text:
            print(f'FAIL: {output_path} 가 {layout_path} 와 어긋남. sync_waypoints 재실행 필요.')
            sys.exit(1)
        print(f'PASS: {output_path} 최신 상태 ({len(new_doc["waypoints"])}개 웨이포인트)')
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(new_text)
    print(f'OK: {output_path} 갱신 ({len(new_doc["waypoints"])}개 웨이포인트)')


if __name__ == '__main__':
    main()
