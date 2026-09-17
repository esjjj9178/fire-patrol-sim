#!/usr/bin/env python3
"""STEP7: sim + nav + perception + fusion + RViz + rqt_image_view(+옵션 mqtt) 통합 데모.

노드 시작 순서: sim(월드/로봇/브리지) 즉시 시작 → nav(맵/AMCL/Nav2/순찰) 8초 지연(스폰/브리지
안정화 대기) → perception(비전/열/가스/뷰어) 10초 지연(카메라 토픽 발행 대기) → fusion(융합/임무관리)
15초 지연(Nav2 active 및 코스트맵 발행 대기 — mission_manager 가 /global_costmap/costmap,
navigate_to_pose 액션을 쓰므로).

인자:
  headless        (기본 true)  : sim.launch.py 로 전달
  gui             (기본 false) : sim.launch.py 로 전달 (Gazebo GUI)
  detector        (기본 hsv)   : perception.launch.py 로 전달 (hsv|yolo)
  virtual_thermal (기본 false) : sim.launch.py + perception.launch.py 양쪽에 동일하게 전달
                                   (STEP7 수정 — 둘 중 하나만 켜면 /thermal/image_raw 충돌)
  mqtt            (기본 false) : true 면 fire_iot_bridge/mqtt_bridge_node 를 enabled:=true 로 실행
  rviz            (기본 true)  : full_demo.rviz + rqt_image_view(/fire/debug_image) 실행
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, TimerAction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    headless = LaunchConfiguration('headless')
    gui = LaunchConfiguration('gui')
    detector = LaunchConfiguration('detector')
    virtual_thermal = LaunchConfiguration('virtual_thermal')
    mqtt = LaunchConfiguration('mqtt')
    rviz = LaunchConfiguration('rviz')

    bringup_share = get_package_share_directory('fire_bringup')

    sim_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(bringup_share, 'launch', 'sim.launch.py')),
        launch_arguments={
            'headless': headless,
            'gui': gui,
            'virtual_thermal': virtual_thermal,
        }.items(),
    )

    nav_launch = TimerAction(
        period=8.0,
        actions=[IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(bringup_share, 'launch', 'nav.launch.py')),
            launch_arguments={'autostart_patrol': 'true'}.items(),
        )],
    )

    perception_launch = TimerAction(
        period=10.0,
        actions=[IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(bringup_share, 'launch', 'perception.launch.py')),
            launch_arguments={
                'detector': detector,
                'virtual_thermal': virtual_thermal,
                'show_window': 'false',
            }.items(),
        )],
    )

    fusion_launch = TimerAction(
        period=15.0,
        actions=[IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(bringup_share, 'launch', 'fusion.launch.py')),
        )],
    )

    mqtt_config = PathJoinSubstitution(
        [FindPackageShare('fire_iot_bridge'), 'config', 'mqtt.yaml'])
    mqtt_node = TimerAction(
        period=15.0,
        actions=[Node(
            package='fire_iot_bridge',
            executable='mqtt_bridge_node',
            name='mqtt_bridge_node',
            output='screen',
            parameters=[mqtt_config, {'use_sim_time': True, 'enabled': mqtt}],
            condition=IfCondition(mqtt),
        )],
    )

    rviz_config = PathJoinSubstitution(
        [FindPackageShare('fire_bringup'), 'rviz', 'full_demo.rviz'])
    rviz_node = TimerAction(
        period=10.0,
        actions=[Node(
            package='rviz2',
            executable='rviz2',
            name='rviz2',
            arguments=['-d', rviz_config],
            parameters=[{'use_sim_time': True}],
            output='screen',
            condition=IfCondition(rviz),
        )],
    )

    image_view = TimerAction(
        period=12.0,
        actions=[Node(
            package='rqt_image_view',
            executable='rqt_image_view',
            name='rqt_image_view',
            arguments=['/fire/debug_image'],
            output='screen',
            condition=IfCondition(rviz),
        )],
    )

    return LaunchDescription([
        DeclareLaunchArgument('headless', default_value='true'),
        DeclareLaunchArgument('gui', default_value='false'),
        DeclareLaunchArgument('detector', default_value='hsv'),
        DeclareLaunchArgument('virtual_thermal', default_value='false'),
        DeclareLaunchArgument('mqtt', default_value='false'),
        DeclareLaunchArgument('rviz', default_value='true'),
        sim_launch,
        nav_launch,
        perception_launch,
        fusion_launch,
        mqtt_node,
        rviz_node,
        image_view,
    ])
