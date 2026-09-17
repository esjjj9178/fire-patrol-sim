# STEP7 검증

## 이 단계에서 확인하는 것 (2~3줄)
`bash scripts/run_demo.sh` 한 줄로 sim+nav+perception+fusion+RViz+디버그영상이 다 뜨는지,
디버그 영상 세 패널(RGB+bbox / 열화상 컬러맵 / 점수막대+상태)이 실시간 갱신되는지,
real/fake/hidden 3가지 화재 시나리오가 한 번의 순찰 루프 안에서 기대대로 동작하고
`scenario_report.py`로 리포트가 남는지, `mqtt:=true`에서 로컬 mosquitto로 event/status가
실제로 나가고 `cmd resume`이 동작하는지 확인한다. **이 단계가 마지막이므로 STEP1~7 전체
완료 기준을 이 시트에서 함께 되짚는다.**

## 사전 조건
- STEP1~6 전부 `/check N` → `/pass N` 완료 권장(순서대로 확인하는 것이 낫지만, STEP7만 먼저
  통합 확인하고 싶다면 진행 가능 — 앞 단계 문제가 여기서도 드러난다).
- YOLO로 확인하려면 STEP4에서 `train_yolo` 로 `fire_perception/models/fire_yolov8n.pt` 학습 완료.
- `bash scripts/check_deps.sh` 누락 0개.

## 실행 명령

### 터미널 1 — 전체 데모(headless)
```bash
cd ~/fire_ws && source scripts/env.sh
bash scripts/run_demo.sh
# GUI로 보려면: bash scripts/run_demo.sh headless:=false
# YOLO+가상열화상+MQTT까지: bash scripts/run_demo.sh detector:=yolo virtual_thermal:=true mqtt:=true
```
Ctrl+C 로 종료하면 `scripts/kill_sim.sh` 가 자동으로 정리된다(trap).

### 터미널 2 — 디버그 영상 확인
`run_demo.sh` 가 이미 `rqt_image_view /fire/debug_image` 를 띄운다(rviz:=true 기본).
직접 확인하려면:
```bash
source ~/fire_ws/scripts/env.sh
ros2 run rqt_image_view rqt_image_view /fire/debug_image
```

### 터미널 3 — 이벤트/리포트
```bash
source ~/fire_ws/scripts/env.sh
ros2 topic echo /fire/event
# 별도로 통합 시나리오 리포트를 남기려면(순찰 1~2바퀴 돌 시간, 예 600초):
python3 ~/fire_ws/install/fire_bringup/share/fire_bringup/scripts/scenario_report.py --duration 600
```

### 터미널 4 — MQTT 확인 (`mqtt:=true` 로 실행했을 때)
```bash
mosquitto_sub -t 'factory/#' -v
mosquitto_pub -t 'factory/fire_bot_01/cmd' -m '{"cmd":"resume"}'   # HOLD 상태일 때 재개 확인
```

## 무엇을 보면 되나
- RViz: 맵/로봇/스캔/전역·지역 경로/코스트맵/`/fire/markers`/디버그이미지 패널이 모두 갱신.
- `/fire/debug_image`(rqt_image_view): 왼쪽 RGB에 불이 지나갈 때 초록 bbox+conf, 가운데
  열화상 INFERNO 컬러맵에 핫스팟 십자선+Tmax 텍스트, 오른쪽 4개 막대(0.5/0.7 임계선)가
  fire_state/mission_state 변화에 맞춰 움직임.
- `real_fire`: PATROL → VERIFY 또는 SUSPECT → CONFIRMED → APPROACH → HOLD, `/fire/event`
  에 FIRE_CONFIRMED, ARRIVED_HOLD.
- `fake_fire`: VERIFY 진입 후 `verify_timeout_s`(6초) 지나면 FALSE_ALARM, PATROL 복귀,
  60초 내 재진입 안 함.
- `hidden_fire`: 가스 먼저 반응 → SUSPECT(팬 SEARCH_360) → 모퉁이 돈 후 비전도 반응 →
  CONFIRMED → APPROACH → HOLD.
- `scenario_report.py` 출력: `data/reports/report_<시간>.md` 에 정답 위치 대비 오차(m)와
  판정까지 걸린 시간이 표로 남음.
- `mqtt:=true`: `mosquitto_sub -t 'factory/#' -v` 에 `factory/fire_bot_01/fire/status`(1Hz,
  retain), `.../fire/event`(전이 시), `.../fire/telemetry`(1Hz) 가 보임. `cmd resume` 발행 후
  HOLD였던 로봇이 PATROL로 복귀.

## 체크리스트 (STEP7.md 완료 기준)
- [ ] `bash scripts/run_demo.sh` 한 줄로 전체 실행됨
- [ ] 디버그 영상 세 패널 실시간 갱신
- [ ] 세 시나리오(real/fake/hidden)가 한 순찰 루프 안에서 기대대로 동작, 리포트 생성됨
- [ ] `mqtt:=true` 에서 `mosquitto_sub` 로 event/status 수신, `cmd resume` 동작
- [ ] README.md / docs/MQTT_DESIGN.md 내용이 실제 실행과 맞는지 확인
- [ ] **(전체 마무리)** PROGRESS.md 모든 단계 구현+검증 ✅ 확인 후 `git tag -a v0.1-sim -m "..."` →
      push, GitHub 저장소에서 README 렌더링 확인

## 안 될 때 확인할 것
1. **perception/fusion 노드가 안 뜸(TimerAction 지연 부족)** — 이 PC가 느려서 8/10/15초 안에
   Nav2/브리지가 안 떠 있으면 늦게 붙는 노드들이 첫 몇 초 메시지를 놓칠 수 있다. 로그에서
   `navigate_to_pose` 액션 서버 대기 경고가 계속 보이면 `full_demo.launch.py`의 TimerAction
   `period` 값을 늘려서 재시도.
2. **`virtual_thermal:=true`인데 열화상이 두 소스에서 겹쳐 보임** — `ros2 topic info
   /thermal/image_raw -v` 로 발행자가 1개(virtual_thermal_node)인지 확인. 2개면
   `sim.launch.py`가 `virtual_thermal` 인자를 못 받은 것(런치 인자 오탈자 확인) — STEP7에서
   `bridge_thermal.yaml`을 분리하고 `UnlessCondition(virtual_thermal)`로 껐으니 정상이면 1개여야 함.
3. **MQTT가 안 붙음** — `systemctl status mosquitto`(또는 `mosquitto -v`로 수동 실행), 방화벽 없음
   확인. `enabled:=true`인데 연결 안 되면 mqtt_bridge_node 로그의 `MQTT 연결 실패 rc=...` 확인.
4. **디버그 영상이 회색/빈 패널** — `/camera/color/image_raw`, `/thermal/temperature_image`,
   `/fire/status`, `/gas/concentration` 각각 `ros2 topic hz`로 발행 확인. 열화상 패널만
   비면 STEP5 열화상 스케일/브리지 문제일 가능성.
5. **scenario_report.py가 이벤트를 못 받음** — `/fire/event`가 실제로 발행되는지 먼저
   `ros2 topic echo`로 확인(순찰 경로가 화재 3개를 다 지나가는 데 몇 분 걸릴 수 있음 —
   `--duration`을 충분히 크게).

## 종료 방법
```bash
# run_demo.sh 를 Ctrl+C 로 끄면 자동 정리되지만, 남았으면:
bash ~/fire_ws/scripts/kill_sim.sh
```
