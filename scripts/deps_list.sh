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
