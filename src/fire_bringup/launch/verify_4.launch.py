#!/usr/bin/env python3
"""검증 묶음 4(전체 시나리오, STEP6+7): full_demo.launch.py(sim+nav+perception+fusion+RViz+디버그영상)를
   mqtt:=true 로 그대로 재사용한다(파라미터/노드 중복 정의 금지).

인자:
  gui      (기본 true)                          : full_demo.launch.py 의 rviz 인자로 전달.
  detector (기본: 학습된 모델 있으면 yolo, 없으면 hsv)
"""
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def _default_detector() -> str:
    try:
        models_dir = Path(get_package_share_directory('fire_perception')) / 'models'
    except Exception:
        models_dir = Path(__file__).resolve().parents[5] / 'fire_perception' / 'models'
    return 'yolo' if (models_dir / 'fire_yolov8n.pt').is_file() else 'hsv'


def generate_launch_description():
    gui = LaunchConfiguration('gui')
    detector = LaunchConfiguration('detector')

    full_demo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([FindPackageShare('fire_bringup'), 'launch', 'full_demo.launch.py'])),
        launch_arguments={
            'headless': 'true',
            'gui': gui,
            'detector': detector,
            'virtual_thermal': 'false',
            'mqtt': 'true',
            'rviz': gui,
        }.items(),
    )

    return LaunchDescription([
        DeclareLaunchArgument('gui', default_value='true'),
        DeclareLaunchArgument('detector', default_value=_default_detector()),
        full_demo,
    ])
