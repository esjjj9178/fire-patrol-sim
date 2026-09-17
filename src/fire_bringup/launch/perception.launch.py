#!/usr/bin/env python3
"""STEP4: camera_pan_node + vision_node.

전제: fire_bringup/launch/sim.launch.py 로 월드/로봇/브리지가 이미 떠 있어야 한다
      (/camera/... , /joint_states, /camera_pan/cmd 토픽 필요).

인자:
  detector      (기본 hsv)  : vision_node 의 detector 파라미터(hsv|yolo)
  use_sim_time  (기본 true)
"""
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    use_sim_time = LaunchConfiguration('use_sim_time')
    detector = LaunchConfiguration('detector')

    perception_config = PathJoinSubstitution(
        [FindPackageShare('fire_perception'), 'config', 'perception.yaml'])

    return LaunchDescription([
        DeclareLaunchArgument('detector', default_value='hsv',
                               description='vision_node backend: hsv|yolo'),
        DeclareLaunchArgument('use_sim_time', default_value='true'),

        Node(
            package='fire_perception',
            executable='camera_pan_node',
            name='camera_pan_node',
            output='screen',
            parameters=[perception_config, {'use_sim_time': use_sim_time}],
        ),
        Node(
            package='fire_perception',
            executable='vision_node',
            name='vision_node',
            output='screen',
            parameters=[perception_config, {
                'use_sim_time': use_sim_time,
                'detector': detector,
            }],
        ),
    ])
