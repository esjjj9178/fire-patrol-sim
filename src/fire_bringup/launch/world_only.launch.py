#!/usr/bin/env python3
"""STEP1 확인용: 창고 월드만 Gazebo 로 띄우고, 필요하면 Nav2 맵 서버 + RViz 로 맵을 겹쳐 본다.

인자:
  headless   (기본 true)  : true 면 -s --headless-rendering (GUI 없이 서버만)
  gui        (기본 false) : true 면 Gazebo GUI 를 띄움 (headless 와 동시 사용 금지)
  show_map   (기본 false) : true 면 map_server + RViz 로 maps/warehouse.yaml 표시
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def _launch_gz_sim(context, *args, **kwargs):
    headless = LaunchConfiguration('headless').perform(context) == 'true'
    gui = LaunchConfiguration('gui').perform(context) == 'true'
    world_path = PathJoinSubstitution(
        [FindPackageShare('fire_world'), 'worlds', 'warehouse.sdf']).perform(context)

    flags = '-r '
    if headless and not gui:
        flags += '-s --headless-rendering '
    gz_args = flags + world_path

    gz_sim = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([FindPackageShare('ros_gz_sim'), 'launch', 'gz_sim.launch.py'])
        ),
        launch_arguments={'gz_args': gz_args}.items(),
    )
    return [gz_sim]


def generate_launch_description():
    show_map = LaunchConfiguration('show_map')

    map_yaml = PathJoinSubstitution(
        [FindPackageShare('fire_world'), 'maps', 'warehouse.yaml'])
    rviz_config = PathJoinSubstitution(
        [FindPackageShare('fire_bringup'), 'rviz', 'world_check.rviz'])

    map_server = Node(
        package='nav2_map_server',
        executable='map_server',
        name='map_server',
        output='screen',
        parameters=[{'yaml_filename': map_yaml, 'use_sim_time': True}],
        condition=IfCondition(show_map),
    )

    lifecycle_manager = Node(
        package='nav2_lifecycle_manager',
        executable='lifecycle_manager',
        name='lifecycle_manager_map',
        output='screen',
        parameters=[{'use_sim_time': True, 'autostart': True, 'node_names': ['map_server']}],
        condition=IfCondition(show_map),
    )

    rviz = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        arguments=['-d', rviz_config],
        parameters=[{'use_sim_time': True}],
        output='screen',
        condition=IfCondition(show_map),
    )

    return LaunchDescription([
        DeclareLaunchArgument('headless', default_value='true'),
        DeclareLaunchArgument('gui', default_value='false'),
        DeclareLaunchArgument('show_map', default_value='false'),
        OpaqueFunction(function=_launch_gz_sim),
        map_server,
        lifecycle_manager,
        rviz,
    ])
