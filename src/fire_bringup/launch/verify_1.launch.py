#!/usr/bin/env python3
"""검증 묶음 1(월드·로봇, STEP1+2): sim.launch.py(월드+로봇+브리지)를 그대로 include 하고,
   gui:=true 일 때만 RViz(sim_check.rviz)와 rqt_image_view(/camera/color/image_raw)를 함께 띄운다.
   scripts/verify.sh 1 이 이 런치 + verify_checker.py --group 1 을 같이 실행한다(직접 실행도 가능).

인자:
  gui (기본 true) : true 면 Gazebo GUI + RViz + rqt_image_view 까지 띄움(사람이 눈으로 확인).
                     false 면 Gazebo headless만(--auto 자동 판정용, verify_checker.py 가 토픽으로 확인).
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    gui = LaunchConfiguration('gui')

    sim_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([FindPackageShare('fire_bringup'), 'launch', 'sim.launch.py'])),
        launch_arguments={
            'headless': 'true',
            'gui': gui,
            'rviz': gui,
        }.items(),
    )

    image_view = Node(
        package='rqt_image_view',
        executable='rqt_image_view',
        name='rqt_image_view',
        arguments=['/camera/color/image_raw'],
        output='screen',
        condition=IfCondition(gui),
    )

    return LaunchDescription([
        DeclareLaunchArgument('gui', default_value='true'),
        sim_launch,
        image_view,
    ])
