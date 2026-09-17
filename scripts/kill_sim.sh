#!/usr/bin/env bash
# 남은 시뮬/ROS 프로세스 정리.
#
# `ros2 launch` 부모 프로세스에 SIGTERM 을 보내는 것만으로는 nav2_bringup 이 직접 띄우는
# controller_server/map_server/... 등 자식 노드가 간혹 안 죽고 남는 경우가 있어(검증 중 발견 —
# verify.sh 2 실행 후 lifecycle_manager_navigation/map_server/waypoint_follower/velocity_smoother 가
# 계속 떠 있는 것을 확인) 각 노드 실행 파일 이름도 직접 매칭해서 정리한다.
PATTERNS=(
  "ruby.*gz"
  "gz sim"
  "parameter_bridge"
  "ros2 launch fire_"
  "rviz2"
  "rqt_image_view"
  "/fire_ws/install/"
  # Nav2 / robot_localization / laser_filters / map_server (nav2_bringup 이 직접 띄우는 노드들)
  "controller_server"
  "planner_server"
  "smoother_server"
  "behavior_server"
  "recoveries_server"
  "bt_navigator"
  "waypoint_follower"
  "velocity_smoother"
  "collision_monitor"
  "lifecycle_manager"
  "nav2_amcl/amcl"
  "nav2_map_server/map_server"
  "robot_localization/ekf_node"
  "laser_filters/scan_to_scan_filter_chain"
  "robot_state_publisher"
)

for pat in "${PATTERNS[@]}"; do
  pkill -f "$pat" 2>/dev/null
done
sleep 1
for pat in "${PATTERNS[@]}"; do
  pkill -9 -f "$pat" 2>/dev/null
done

ros2 daemon stop >/dev/null 2>&1
echo "정리 완료"
