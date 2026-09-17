#!/usr/bin/env bash
# 사용: source ~/fire_ws/scripts/env.sh
source /opt/ros/humble/setup.bash
_FIRE_WS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ -f "$_FIRE_WS/install/setup.bash" ]] && source "$_FIRE_WS/install/setup.bash"
export ROS_DOMAIN_ID=30
export GZ_SIM_RESOURCE_PATH="$_FIRE_WS/src/fire_world/models:$_FIRE_WS/install/fire_description/share:${GZ_SIM_RESOURCE_PATH:-}"
export PATH="$HOME/.local/bin:$PATH"
