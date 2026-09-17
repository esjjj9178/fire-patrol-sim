#!/usr/bin/env python3
"""검증 묶음 2(자율주행, STEP3): sim.launch.py + nav.launch.py(순찰 자동 시작) + RViz(nav.rviz).
   sim이 뜨고 브리지가 안정화될 시간을 두려고 nav.launch.py 는 8초 지연 후 시작한다
   (full_demo.launch.py 와 동일한 패턴, 파라미터 중복 정의 없이 include 만 사용).

인자:
  gui (기본 true) : true 면 Gazebo GUI + RViz 까지 띄움. false 면 headless(--auto 자동 판정용).
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    gui = LaunchConfiguration('gui')

    sim_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([FindPackageShare('fire_bringup'), 'launch', 'sim.launch.py'])),
        launch_arguments={'headless': 'true', 'gui': gui}.items(),
    )

    nav_launch = TimerAction(
        period=8.0,
        actions=[IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                PathJoinSubstitution([FindPackageShare('fire_bringup'), 'launch', 'nav.launch.py'])),
            launch_arguments={'autostart_patrol': 'true', 'rviz': gui}.items(),
        )],
    )

    return LaunchDescription([
        DeclareLaunchArgument('gui', default_value='true'),
        sim_launch,
        nav_launch,
    ])
