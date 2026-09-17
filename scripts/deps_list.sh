#!/usr/bin/env bash
# 설치 대상 목록 (check_deps.sh / install_deps.sh 공용)

ROS_APT=(
  ros-humble-desktop
  ros-humble-ros-gzharmonic
  ros-humble-navigation2
  ros-humble-nav2-bringup
  ros-humble-nav2-simple-commander
  ros-humble-robot-localization
  ros-humble-laser-filters
  ros-humble-xacro
  ros-humble-robot-state-publisher
  ros-humble-joint-state-publisher
  ros-humble-teleop-twist-keyboard
  ros-humble-rqt-image-view
  ros-humble-cv-bridge
  ros-humble-vision-opencv
)

SYS_APT=(
  git curl wget unzip
  python3-pip python3-yaml python3-pil python3-matplotlib python3-pytest
  python3-colcon-common-extensions python3-rosdep
  mosquitto mosquitto-clients python3-paho-mqtt
  mesa-utils
  gh
)

is_apt_installed() {
  dpkg-query -W -f='${Status}' "$1" 2>/dev/null | grep -q "install ok installed"
}

py_numpy_ok()      { python3 -c "import numpy,sys; sys.exit(0 if int(numpy.__version__.split('.')[0])<2 else 1)" 2>/dev/null; }
py_torch_ok()      { python3 -c "import torch" 2>/dev/null; }
py_ultralytics_ok(){ python3 -c "import ultralytics" 2>/dev/null; }
py_cv2_ok()        { python3 -c "import cv2, numpy" 2>/dev/null; }

ros_repo_configured() {
  ls /etc/apt/sources.list.d/ 2>/dev/null | grep -qiE '^ros2(\.list|\.sources)$'
}
osrf_repo_configured() {
  grep -rqs "packages.osrfoundation.org" /etc/apt/sources.list /etc/apt/sources.list.d/
}
gz_harmonic_ok() {
  is_apt_installed gz-sim8-cli && return 0
  command -v gz >/dev/null || return 1
  gz sim --versions 2>/dev/null | grep -q '^8\.' || gz sim --version 2>/dev/null | grep -q 'version 8\.'
}
gh_repo_configured() {
  [[ -f /etc/apt/sources.list.d/github-cli.list ]]
}

# ros-humble-diagnostic-updater 4.0.6(이 PC에 설치된 버전)은 헤더/파이썬만 있고
# libdiagnostic_updater.so 를 만들지 않는데, apt로 함께 깔린 laser_filters(scan_to_scan_filter_chain)와
# robot_localization(ekf_node) 바이너리는 이 .so 에 동적 링크되어 있어 실행 시
# "libdiagnostic_updater.so: cannot open shared object file" 로 죽는다(런타임 검증 중 발견,
# STEP3 EKF/laser_filters 크래시의 근본 원인 — apt 후보 버전(4.0.7+)엔 .so 가 포함되어 upgrade 로 해결됨).
diagnostic_updater_lib_ok() {
  ldconfig -p 2>/dev/null | grep -q libdiagnostic_updater.so && return 0
  find /opt/ros/humble/lib -maxdepth 1 -name 'libdiagnostic_updater.so*' 2>/dev/null | grep -q . && return 0
  return 1
}
