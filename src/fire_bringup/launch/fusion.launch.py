#!/usr/bin/env python3
"""STEP6: fusion_node(가중치 융합 판정) + mission_manager_node(임무 행동 상태머신).

전제: sim.launch.py(로봇/브리지) + nav.launch.py(Nav2/순찰) + perception.launch.py(비전/열/가스)
      가 이미 떠 있어야 한다. mission_manager_node 는 /patrol_node/set_parameters,
      navigate_to_pose 액션, /global_costmap/costmap 을 사용하므로 Nav2 가 active 여야 한다.

인자:
  use_sim_time (기본 true)
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    use_sim_time = LaunchConfiguration('use_sim_time')

    fusion_config = PathJoinSubstitution(
        [FindPackageShare('fire_fusion'), 'config', 'fusion.yaml'])

    return LaunchDescription([
        DeclareLaunchArgument('use_sim_time', default_value='true'),

        Node(
            package='fire_fusion',
            executable='fusion_node',
            name='fusion_node',
            output='screen',
            parameters=[fusion_config, {'use_sim_time': use_sim_time}],
        ),
        Node(
            package='fire_fusion',
            executable='mission_manager_node',
            name='mission_manager_node',
            output='screen',
            parameters=[fusion_config, {'use_sim_time': use_sim_time}],
        ),
    ])
