#!/usr/bin/env bash
# YOLO 학습 파이프라인 한 번에: sim+nav(headless) 를 띄워 이미지 수집 -> 자동 라벨 -> 학습 -> 평가 -> 정리.
# 중간에 끊기면(Ctrl+C, 오류, 재부팅) 같은 명령으로 다시 실행할 때 이미 끝난 단계는 건너뛰고 이어서 진행한다.
#
# 사용:
#   bash scripts/train_yolo.sh
#   bash scripts/train_yolo.sh --target-images 300 --epochs 30
set -eo pipefail
cd "$(dirname "$0")/.."
WS="$(pwd)"

TARGET_IMAGES=280
EPOCHS=25
while [[ $# -gt 0 ]]; do
  case "$1" in
    --target-images) TARGET_IMAGES="$2"; shift 2 ;;
    --epochs) EPOCHS="$2"; shift 2 ;;
    *) echo "알 수 없는 옵션: $1"; exit 1 ;;
  esac
done

log() { echo "[$(date +%H:%M:%S)] $*"; }

STAGE_FILE="$WS/data/.train_yolo_stage"
mkdir -p "$WS/data/raw"   # find 가 없는 디렉터리에서 실패(pipefail 로 스크립트 조기 종료)하지 않도록 미리 만든다
stage_done() { [[ -f "$STAGE_FILE" ]] && grep -qx "$1" "$STAGE_FILE" 2>/dev/null; }
mark_done() { echo "$1" >> "$STAGE_FILE"; }
count_raw_pngs() { find "$WS/data/raw" -name '*.png' 2>/dev/null | wc -l || true; }

CURRENT_STAGE="0/4 빌드 확인"
LAST_LOG_HINT=""
on_error() {
  local exit_code=$? line=$1
  echo "[$(date +%H:%M:%S)] [${CURRENT_STAGE}] 실패: '${BASH_COMMAND}' (${line}번째 줄, exit=${exit_code})${LAST_LOG_HINT:+ - 로그: $LAST_LOG_HINT}"
}
trap 'on_error $LINENO' ERR

cleanup() {
  bash scripts/kill_sim.sh >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

source scripts/env.sh
log "0/4 빌드 확인"
colcon build --symlink-install
source install/setup.bash

TOTAL_START=$(date +%s)

# ---- 1/4 이미지 수집 ----
CURRENT_STAGE="1/4 이미지 수집"
LAST_LOG_HINT="/tmp/train_yolo_{sim,nav,perception}.log"
RAW_COUNT=$(count_raw_pngs)
if stage_done collect && [[ "$RAW_COUNT" -ge "$TARGET_IMAGES" ]]; then
  log "1/4 건너뜀(이미 ${RAW_COUNT}장 수집됨, 목표 ${TARGET_IMAGES})"
else
  EST_S=$(( (TARGET_IMAGES - RAW_COUNT) * 1 + 30 ))
  log "1/4 이미지 수집 시작 (현재 ${RAW_COUNT}장 -> 목표 ${TARGET_IMAGES}장, 예상 약 $((EST_S/60))분)"

  ros2 launch fire_bringup sim.launch.py headless:=true > /tmp/train_yolo_sim.log 2>&1 &
  SIM_PID=$!
  sleep 10
  ros2 launch fire_bringup nav.launch.py autostart_patrol:=true > /tmp/train_yolo_nav.log 2>&1 &
  NAV_PID=$!
  sleep 8
  ros2 launch fire_bringup perception.launch.py detector:=hsv show_window:=false > /tmp/train_yolo_perception.log 2>&1 &
  PER_PID=$!
  sleep 5

  COLLECT_RC=0
  timeout 600 ros2 run fire_perception collect_images --ros-args -p target_images:="$TARGET_IMAGES" || COLLECT_RC=$?

  kill "$SIM_PID" "$NAV_PID" "$PER_PID" >/dev/null 2>&1 || true
  bash scripts/kill_sim.sh >/dev/null 2>&1 || true
  sleep 2

  NEW_COUNT=$(count_raw_pngs)
  if [[ $COLLECT_RC -ne 0 && "$NEW_COUNT" -lt "$TARGET_IMAGES" ]]; then
    log "1/4 실패(rc=$COLLECT_RC, ${NEW_COUNT}/${TARGET_IMAGES}장) - 로그: /tmp/train_yolo_{sim,nav,perception}.log"
    log "    다시 'bash scripts/train_yolo.sh' 실행하면 ${NEW_COUNT}장부터 이어서 수집합니다."
    exit 1
  fi
  mark_done collect
  log "1/4 완료: ${NEW_COUNT}장 수집"
fi

# ---- 2/4 자동 라벨링 ----
CURRENT_STAGE="2/4 자동 라벨링"
LAST_LOG_HINT=""
if stage_done label && [[ -f "$WS/data/fire_yolo/data.yaml" ]]; then
  log "2/4 건너뜀(이미 data/fire_yolo/data.yaml 존재)"
else
  log "2/4 자동 라벨링 시작 (수십 초 내 완료)"
  if ! ros2 run fire_perception auto_label; then
    log "2/4 실패 - 다시 실행하면 이어서 진행"
    exit 1
  fi
  mark_done label
  log "2/4 완료: data/preview/ 미리보기 육안 확인 권장 (bbox 가 실제 불 위치에 그려져 있는지)"
fi

# ---- 3/4 학습 ----
CURRENT_STAGE="3/4 YOLO 학습"
MODEL_OUT="$WS/src/fire_perception/models/fire_yolov8n.pt"
if stage_done train && [[ -f "$MODEL_OUT" ]]; then
  log "3/4 건너뜀(이미 fire_yolov8n.pt 존재)"
else
  EST_MIN=$(( EPOCHS * 25 / 60 + 1 ))
  RESUME_FLAG=()
  [[ -d "$WS/runs/detect/fire_yolov8n" ]] && RESUME_FLAG=(--resume) && log "이전 체크포인트 발견 - 이어서 학습(--resume)"
  log "3/4 YOLOv8n(CPU) 학습 시작 (epochs=${EPOCHS}, 예상 약 ${EST_MIN}분, CPU 성능에 따라 다름)"
  T0=$(date +%s)
  RC=0
  ros2 run fire_perception train_yolo --epochs "$EPOCHS" "${RESUME_FLAG[@]}" || RC=$?
  ELAPSED=$(( $(date +%s) - T0 ))
  if [[ $RC -ne 0 ]]; then
    log "3/4 실패(rc=$RC, ${ELAPSED}s 경과) - 다시 'bash scripts/train_yolo.sh' 실행하면 체크포인트에서 이어서 학습합니다."
    exit 1
  fi
  mark_done train
  log "3/4 완료 (${ELAPSED}s = $((ELAPSED/60))분)"
fi

# ---- 4/4 평가 ----
CURRENT_STAGE="4/4 평가"
if ! ros2 run fire_perception eval_yolo; then
  log "4/4 실패 - fire_yolov8n.pt 는 이미 만들어져 있으니 eval_yolo 만 다시 실행해도 됩니다."
  exit 1
fi
mark_done eval
log "4/4 완료 - 위 mAP50/CPU FPS 결과 확인(목표 mAP50>=0.8, FPS>=5). 미달 시 STEP4.md 참고해 데이터/epochs 조정 후 재실행."

rm -f "$STAGE_FILE"
TOTAL_ELAPSED=$(( $(date +%s) - TOTAL_START ))
log "전체 파이프라인 완료 (총 $((TOTAL_ELAPSED/60))분)"
