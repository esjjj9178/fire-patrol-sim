#!/usr/bin/env python3
"""검증 묶음 3(센서 인식, STEP4+5): sim.launch.py + perception.launch.py(비전/열/가스/팬/뷰어).
   Nav2 는 띄우지 않는다 — verify_checker.py --group 3 이 순간이동(set_pose) 시나리오로
   직접 확인하므로 순찰이 필요 없다.

인자:
  gui      (기본 true)                          : GUI + RViz(sim_check.rviz) + rqt_image_view(/fire/debug_image).
  detector (기본: 학습된 모델 있으면 yolo, 없으면 hsv)
"""
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, TimerAction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
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

    sim_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([FindPackageShare('fire_bringup'), 'launch', 'sim.launch.py'])),
        launch_arguments={'headless': 'true', 'gui': gui, 'rviz': gui}.items(),
    )

    perception_launch = TimerAction(
        period=5.0,
        actions=[IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                PathJoinSubstitution(
                    [FindPackageShare('fire_bringup'), 'launch', 'perception.launch.py'])),
            launch_arguments={
                'detector': detector,
                'virtual_thermal': 'false',
                'show_window': 'false',
            }.items(),
        )],
    )

    image_view = TimerAction(
        period=7.0,
        actions=[Node(
            package='rqt_image_view',
            executable='rqt_image_view',
            name='rqt_image_view',
            arguments=['/fire/debug_image'],
            output='screen',
            condition=IfCondition(gui),
        )],
    )

    return LaunchDescription([
        DeclareLaunchArgument('gui', default_value='true'),
        DeclareLaunchArgument('detector', default_value=_default_detector()),
        sim_launch,
        perception_launch,
        image_view,
    ])
