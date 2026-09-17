#!/usr/bin/env python3
"""STEP4/STEP5: camera_pan_node + vision_node + thermal_node(또는 virtual_thermal_node) + gas_sim_node.

전제: fire_bringup/launch/sim.launch.py 로 월드/로봇/브리지가 이미 떠 있어야 한다
      (/camera/... , /joint_states, /camera_pan/cmd, /ground_truth/pose 토픽 필요).

인자:
  detector          (기본 hsv)   : vision_node 의 detector 파라미터(hsv|yolo)
  virtual_thermal   (기본 false) : true 면 Gazebo thermal 대신 virtual_thermal_node(SIM ONLY
                                    폴백)가 /thermal/image_raw 를 발행한다. sim.launch.py 도 같은
                                    이름의 인자를 받아 true 일 때 Gazebo thermal 브리지
                                    (bridge_thermal.yaml)를 끄므로, full_demo.launch.py 처럼 두
                                    런치를 함께 쓸 때는 반드시 같은 값을 넘겨야 한다(STEP7 수정).
  use_sim_time      (기본 true)
"""
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    use_sim_time = LaunchConfiguration('use_sim_time')
    detector = LaunchConfiguration('detector')
    virtual_thermal = LaunchConfiguration('virtual_thermal')
    show_window = LaunchConfiguration('show_window')

    perception_config = PathJoinSubstitution(
        [FindPackageShare('fire_perception'), 'config', 'perception.yaml'])

    return LaunchDescription([
        DeclareLaunchArgument('detector', default_value='hsv',
                               description='vision_node backend: hsv|yolo'),
        DeclareLaunchArgument('virtual_thermal', default_value='false',
                               description='true면 가상 열화상 노드로 폴백'),
        DeclareLaunchArgument('show_window', default_value='false',
                               description='true면 viewer_node 가 cv2.imshow 창도 띄운다'),
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
        Node(
            package='fire_perception',
            executable='thermal_node',
            name='thermal_node',
            output='screen',
            parameters=[perception_config, {'use_sim_time': use_sim_time}],
        ),
        Node(
            package='fire_perception',
            executable='virtual_thermal_node',
            name='virtual_thermal_node',
            output='screen',
            condition=IfCondition(virtual_thermal),
            parameters=[perception_config, {'use_sim_time': use_sim_time}],
        ),
        Node(
            package='fire_perception',
            executable='gas_sim_node',
            name='gas_sim_node',
            output='screen',
            parameters=[perception_config, {'use_sim_time': use_sim_time}],
        ),
        Node(
            package='fire_perception',
            executable='viewer_node',
            name='viewer_node',
            output='screen',
            parameters=[perception_config, {
                'use_sim_time': use_sim_time,
                'show_window': show_window,
            }],
        ),
    ])
