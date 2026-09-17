#!/usr/bin/env bash
# 남은 시뮬/ROS 프로세스 정리
pkill -f "ruby.*gz" 2>/dev/null
pkill -f "gz sim" 2>/dev/null
pkill -f "parameter_bridge" 2>/dev/null
pkill -f "ros2 launch fire_" 2>/dev/null
pkill -f "rviz2" 2>/dev/null
pkill -f "rqt_image_view" 2>/dev/null
pkill -f "/fire_ws/install/" 2>/dev/null
sleep 1
ros2 daemon stop >/dev/null 2>&1
echo "정리 완료"
