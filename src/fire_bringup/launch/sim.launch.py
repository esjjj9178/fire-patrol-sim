#!/usr/bin/env python3
"""STEP2: 창고 월드 실행 + fire_bot 스폰 + robot_state_publisher + ros_gz_bridge (+옵션 RViz).

인자:
  headless (기본 true)  : true 면 Gazebo -s --headless-rendering (서버만)
  gui      (기본 false) : true 면 Gazebo GUI
  rviz     (기본 false) : true 면 RViz(sim_check.rviz) 실행
  x, y, yaw              : 스폰 위치 (기본값 = fire_world/config/warehouse_layout.yaml 의 robot.spawn)
  virtual_thermal (기본 false) : STEP7 — true 면 Gazebo 실제 thermal 브리지(bridge_thermal.yaml)를
                                   켜지 않는다(perception.launch.py 의 virtual_thermal_node 가
                                   대신 /thermal/image_raw 를 발행하므로 동시에 켜면 두 발행자가
                                   충돌한다. STEP5_VERIFY.md/PROGRESS.md 변경 이력 참고).
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction
from launch.conditions import IfCondition, UnlessCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare

# fire_world/config/warehouse_layout.yaml 의 robot.spawn 값과 동일하게 유지한다.
DEFAULT_SPAWN_X = '-6.0'
DEFAULT_SPAWN_Y = '-3.8'
DEFAULT_SPAWN_YAW = '0.0'


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
    xacro_file = PathJoinSubstitution(
        [FindPackageShare('fire_description'), 'urdf', 'fire_bot.urdf.xacro'])
    robot_description = ParameterValue(Command(['xacro ', xacro_file]), value_type=str)

    robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        parameters=[{'robot_description': robot_description, 'use_sim_time': True}],
    )

    spawn_robot = Node(
        package='ros_gz_sim',
        executable='create',
        name='spawn_fire_bot',
        output='screen',
        arguments=[
            '-topic', 'robot_description',
            '-name', 'fire_bot',
            '-x', LaunchConfiguration('x'),
            '-y', LaunchConfiguration('y'),
            '-z', '0.02',
            '-Y', LaunchConfiguration('yaw'),
        ],
    )

    bridge_config = PathJoinSubstitution(
        [FindPackageShare('fire_bringup'), 'config', 'bridge.yaml'])
    bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='ros_gz_bridge',
        output='screen',
        parameters=[{'config_file': bridge_config, 'use_sim_time': True}],
    )

    thermal_bridge_config = PathJoinSubstitution(
        [FindPackageShare('fire_bringup'), 'config', 'bridge_thermal.yaml'])
    thermal_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='ros_gz_bridge_thermal',
        output='screen',
        parameters=[{'config_file': thermal_bridge_config, 'use_sim_time': True}],
        condition=UnlessCondition(LaunchConfiguration('virtual_thermal')),
    )

    rviz_config = PathJoinSubstitution(
        [FindPackageShare('fire_bringup'), 'rviz', 'sim_check.rviz'])
    rviz = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        arguments=['-d', rviz_config],
        parameters=[{'use_sim_time': True}],
        output='screen',
        condition=IfCondition(LaunchConfiguration('rviz')),
    )

    return LaunchDescription([
        DeclareLaunchArgument('headless', default_value='true'),
        DeclareLaunchArgument('gui', default_value='false'),
        DeclareLaunchArgument('rviz', default_value='false'),
        DeclareLaunchArgument('x', default_value=DEFAULT_SPAWN_X),
        DeclareLaunchArgument('y', default_value=DEFAULT_SPAWN_Y),
        DeclareLaunchArgument('yaw', default_value=DEFAULT_SPAWN_YAW),
        DeclareLaunchArgument('virtual_thermal', default_value='false'),
        OpaqueFunction(function=_launch_gz_sim),
        robot_state_publisher,
        spawn_robot,
        bridge,
        thermal_bridge,
        rviz,
    ])
