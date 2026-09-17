#!/usr/bin/env bash
# STEP2 확인용: 주요 센서/상태 토픽의 발행 주기(hz)를 표로 출력한다.
# 사용: (sim.launch.py 가 이미 떠 있는 상태에서) bash scripts/check_topics.sh
set -uo pipefail

TOPICS=(
  "/scan"
  "/imu"
  "/odom"
  "/joint_states"
  "/camera/color/image_raw"
  "/camera/depth/image_raw"
  "/thermal/image_raw"
  "/camera/imu"
  "/ground_truth/pose"
)

printf "%-30s %s\n" "topic" "hz (8초 측정)"
printf "%-30s %s\n" "------------------------------" "--------------------------"
for t in "${TOPICS[@]}"; do
  result=$(timeout 8 ros2 topic hz "$t" 2>/dev/null | grep -m1 "average rate")
  if [[ -z "$result" ]]; then
    result="(발행 없음/타임아웃)"
  fi
  printf "%-30s %s\n" "$t" "$result"
done
