#!/usr/bin/env python3
"""STEP3: laser filter + EKF + map_server/AMCL(localization) + Nav2(controller/planner/...) + 순찰.

전제: fire_bringup/launch/sim.launch.py 로 월드/로봇/브리지가 이미 떠 있어야 한다
      (map->odom 은 AMCL, odom->base_footprint 는 EKF 가 발행하므로 Gazebo DiffDrive 의 TF는 쓰지 않는다).

인자:
  autostart_patrol (기본 true) : patrol_node 를 /patrol/cmd start 로 자동 시작할지
                                   (false 면 노드만 띄우고 사용자가 /patrol/cmd 로 제어)
  use_sim_time      (기본 true)
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    nav2_bringup_dir = get_package_share_directory('nav2_bringup')

    use_sim_time = LaunchConfiguration('use_sim_time')
    autostart_patrol = LaunchConfiguration('autostart_patrol')
    rviz = LaunchConfiguration('rviz')

    laser_filter_config = PathJoinSubstitution(
        [FindPackageShare('fire_navigation'), 'config', 'laser_filter.yaml'])
    ekf_config = PathJoinSubstitution(
        [FindPackageShare('fire_navigation'), 'config', 'ekf.yaml'])
    nav2_params = PathJoinSubstitution(
        [FindPackageShare('fire_navigation'), 'config', 'nav2_params.yaml'])
    map_yaml = PathJoinSubstitution(
        [FindPackageShare('fire_world'), 'maps', 'warehouse.yaml'])
    rviz_config = PathJoinSubstitution(
        [FindPackageShare('fire_bringup'), 'rviz', 'nav.rviz'])

    laser_filter_node = Node(
        package='laser_filters',
        executable='scan_to_scan_filter_chain',
        name='scan_to_scan_filter_chain',
        output='screen',
        parameters=[laser_filter_config, {'use_sim_time': use_sim_time}],
    )

    ekf_node = Node(
        package='robot_localization',
        executable='ekf_node',
        name='ekf_filter_node',
        output='screen',
        parameters=[ekf_config, {'use_sim_time': use_sim_time}],
    )

    localization = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(nav2_bringup_dir, 'launch', 'localization_launch.py')),
        launch_arguments={
            'map': map_yaml,
            'use_sim_time': use_sim_time,
            'params_file': nav2_params,
            'autostart': 'true',
        }.items(),
    )

    navigation = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(nav2_bringup_dir, 'launch', 'navigation_launch.py')),
        launch_arguments={
            'use_sim_time': use_sim_time,
            'params_file': nav2_params,
            'autostart': 'true',
        }.items(),
    )

    patrol_node = Node(
        package='fire_navigation',
        executable='patrol_node',
        name='patrol_node',
        output='screen',
        parameters=[{
            'use_sim_time': use_sim_time,
            'autostart': autostart_patrol,
        }],
    )

    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        arguments=['-d', rviz_config],
        parameters=[{'use_sim_time': use_sim_time}],
        output='screen',
        condition=IfCondition(rviz),
    )

    return LaunchDescription([
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        DeclareLaunchArgument('autostart_patrol', default_value='true'),
        DeclareLaunchArgument('rviz', default_value='false'),
        laser_filter_node,
        ekf_node,
        localization,
        navigation,
        patrol_node,
        rviz_node,
    ])
