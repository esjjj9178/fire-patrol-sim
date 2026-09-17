#!/usr/bin/env bash
# 전체 데모 한 줄 실행: 환경 source + full_demo.launch.py + 종료 시 자동 정리.
# 사용: bash scripts/run_demo.sh [ros2 launch 인자...]
#   예) bash scripts/run_demo.sh headless:=false detector:=yolo virtual_thermal:=true mqtt:=true
set -eo pipefail
cd "$(dirname "$0")/.."
source scripts/env.sh

cleanup() {
  echo "== run_demo.sh 종료 - 정리 중 =="
  bash scripts/kill_sim.sh
}
trap cleanup EXIT INT TERM

ros2 launch fire_bringup full_demo.launch.py "$@"
