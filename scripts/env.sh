#!/usr/bin/env bash
# 사용: source ~/fire_ws/scripts/env.sh
#
# 이 PC 의 로그인 셸에 다른 프로젝트(main_ws)용 Fast-DDS 디스커버리 서버 설정
# (ROS_DISCOVERY_SERVER/ROS_SUPER_CLIENT/FASTRTPS_DEFAULT_PROFILES_FILE)이 이미 export 되어
# 있으면 이 fire_ws 시뮬레이션의 ROS2 노드들이 그 디스커버리 서버에 붙으려다 서로를 못 찾는다
# (ros2 node list/topic list 가 비어 보임). fire_ws 는 이 PC 안에서만 도는 단순 시뮬레이션이므로
# 항상 기본 멀티캐스트 디스커버리로 격리해서 쓴다.
unset ROS_DISCOVERY_SERVER
unset ROS_SUPER_CLIENT
unset FASTRTPS_DEFAULT_PROFILES_FILE

source /opt/ros/humble/setup.bash
_FIRE_WS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ -f "$_FIRE_WS/install/setup.bash" ]] && source "$_FIRE_WS/install/setup.bash"
export ROS_DOMAIN_ID=30
export ROS_LOCALHOST_ONLY=1
export GZ_SIM_RESOURCE_PATH="$_FIRE_WS/src/fire_world/models:$_FIRE_WS/install/fire_description/share:${GZ_SIM_RESOURCE_PATH:-}"
export PATH="$HOME/.local/bin:$PATH"

# 이 PC 는 `gz sim -s --headless-rendering`(off-screen GBM/EGL) 컨텍스트 초기화가 실패해서
# (`eglinfo` 의 "GBM platform: eglInitialize failed" 로 확인) headless 로 띄우면 카메라/열화상
# 센서가 실제 장면 대신 빈 회색 프레임만 준다(런타임 검증 중 발견 - RGB/depth 이미지를 저장해서
# 확인함). CLAUDE.md 의 문서화된 소프트웨어 렌더링 폴백을 기본으로 켠다(GUI 로 띄울 때도 무해함).
export LIBGL_ALWAYS_SOFTWARE=1
