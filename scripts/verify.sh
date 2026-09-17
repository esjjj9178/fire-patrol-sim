#!/usr/bin/env bash
# 검증 묶음(1~4) 실행 스크립트.
#
# 사용:
#   bash scripts/verify.sh 1            # 대화형: gnome-terminal 탭 2개(런치 + 자동판정)를 띄움 (GUI 있음)
#   bash scripts/verify.sh 1 --auto     # 자동: GUI 없이 timeout 을 걸고 실행, PASS/FAIL 표만 출력 후 정리
#   bash scripts/verify.sh all --auto   # 1~4 순서대로 자동 판정
#   bash scripts/verify.sh stop         # 남은 시뮬/ROS 프로세스 정리(kill_sim.sh)
set -eo pipefail
cd "$(dirname "$0")/.."
WS="$(pwd)"

usage() {
  cat <<'EOF'
사용법:
  bash scripts/verify.sh <1|2|3|4>            대화형(GUI, gnome-terminal 탭 2개)
  bash scripts/verify.sh <1|2|3|4> --auto     자동(headless, timeout, PASS/FAIL 표만)
  bash scripts/verify.sh all --auto           1~4 순서대로 자동
  bash scripts/verify.sh stop                 남은 프로세스 정리
EOF
}

# 그룹별: [체크 시작 전 대기(초, 노드/브리지 안정화)] [checker 자동 timeout(초, verify_checker.py 기본값과 동일)]
declare -A STARTUP_DELAY=( [1]=8 [2]=16 [3]=14 [4]=25 )
declare -A CHECKER_TIMEOUT=( [1]=90 [2]=150 [3]=120 [4]=220 )
declare -A GROUP_TITLE=(
  [1]="월드·로봇 (STEP1+2)"
  [2]="자율주행 (STEP3)"
  [3]="센서 인식 (STEP4+5)"
  [4]="전체 시나리오 (STEP6+7)"
)
declare -A LOOK_FOR=(
  [1]="Gazebo GUI 로 창고/로봇 확인, RViz 에 스캔/RGB/Depth/Thermal 이미지, rqt_image_view 에 카메라 영상이 나오는지 본다."
  [2]="Gazebo+RViz(nav.rviz) 에서 로봇이 8개 웨이포인트를 순찰하며 장애물 2개를 회피하는지, 코스트맵/경로가 그려지는지 본다."
  [3]="RViz(sim_check.rviz)+rqt_image_view(/fire/debug_image) 에서 RGB/열화상 패널이 갱신되는지 본다. 점수표는 터미널 checker 탭에 자동 출력됨."
  [4]="RViz(full_demo.rviz)+rqt_image_view(/fire/debug_image) 에서 마커/디버그영상이 갱신되는지, mosquitto_sub -t 'factory/#' -v 로 MQTT 메시지를 눈으로 본다."
)

cleanup_and_exit() {
  local rc="$1"
  bash scripts/kill_sim.sh >/dev/null 2>&1
  exit "$rc"
}

run_auto_group() {
  local group="$1"
  source scripts/env.sh
  colcon build --symlink-install || return 1
  source install/setup.bash

  local checker="$WS/install/fire_bringup/share/fire_bringup/scripts/verify_checker.py"
  local startup="${STARTUP_DELAY[$group]}"
  local ctimeout="${CHECKER_TIMEOUT[$group]}"
  local safety=$((startup + ctimeout + 60))

  echo "== 묶음 $group (${GROUP_TITLE[$group]}) 자동 검증 시작 (launch 대기 ${startup}s + checker timeout ${ctimeout}s) =="

  ros2 launch fire_bringup "verify_${group}.launch.py" gui:=false > "/tmp/verify_group${group}_launch.log" 2>&1 &
  local launch_pid=$!

  sleep "$startup"

  local rc=0
  timeout "$safety" python3 "$checker" --group "$group" --auto --timeout "$ctimeout" || rc=$?

  kill "$launch_pid" >/dev/null 2>&1 || true
  wait "$launch_pid" 2>/dev/null || true
  bash scripts/kill_sim.sh >/dev/null 2>&1 || true
  sleep 1

  if [[ $rc -ne 0 ]]; then
    echo "== 묶음 $group FAIL (launch 로그: /tmp/verify_group${group}_launch.log) =="
  else
    echo "== 묶음 $group PASS =="
  fi
  return $rc
}

run_interactive_group() {
  local group="$1"
  source scripts/env.sh
  colcon build --symlink-install || return 1
  source install/setup.bash

  local checker="$WS/install/fire_bringup/share/fire_bringup/scripts/verify_checker.py"
  local startup="${STARTUP_DELAY[$group]}"

  echo "== 묶음 $group (${GROUP_TITLE[$group]}) 대화형 검증 =="
  echo "무엇을 보면 되나:"
  echo "  ${LOOK_FOR[$group]}"
  echo "  (checker 탭에 10초마다 PASS/FAIL/대기 표가 자동 출력됩니다. 종료: bash scripts/verify.sh stop)"

  if command -v gnome-terminal >/dev/null 2>&1; then
    gnome-terminal \
      --tab --title="verify_${group} launch" -- bash -c "cd '$WS' && source scripts/env.sh && ros2 launch fire_bringup verify_${group}.launch.py gui:=true; exec bash" \
      --tab --title="verify_${group} checker" -- bash -c "cd '$WS' && sleep ${startup} && source scripts/env.sh && python3 '$checker' --group ${group}; exec bash"
  else
    echo "(gnome-terminal 이 없어 자동으로 탭을 못 엽니다. 터미널 2개를 열고 아래를 각각 실행하세요.)"
    echo "터미널 1: source scripts/env.sh && ros2 launch fire_bringup verify_${group}.launch.py gui:=true"
    echo "터미널 2: source scripts/env.sh && python3 $checker --group ${group}"
  fi
  return 0
}

GROUP="${1:-}"
AUTO=false
[[ "${2:-}" == "--auto" ]] && AUTO=true

case "$GROUP" in
  stop)
    bash scripts/kill_sim.sh
    exit 0
    ;;
  all)
    if [[ "$AUTO" != true ]]; then
      echo "all 은 --auto 와만 함께 사용합니다: bash scripts/verify.sh all --auto"
      exit 1
    fi
    overall=0
    for g in 1 2 3 4; do
      rc=0
      run_auto_group "$g" || rc=$?
      [[ $rc -ne 0 ]] && overall=1
      sleep 2
    done
    echo "== 전체 결과: $([[ $overall -eq 0 ]] && echo PASS || echo FAIL) =="
    exit $overall
    ;;
  1|2|3|4)
    rc=0
    if [[ "$AUTO" == true ]]; then
      run_auto_group "$GROUP" || rc=$?
    else
      run_interactive_group "$GROUP" || rc=$?
    fi
    exit $rc
    ;;
  *)
    usage
    exit 1
    ;;
esac
