# STEP6 검증

## 이 단계에서 확인하는 것 (2~3줄)
`fusion_node`(가중치 융합 판정, `/fire/status` `/fire/markers`)와 `mission_manager_node`
(PATROL/SEARCH/VERIFY/APPROACH/HOLD 상태머신, `/fire/event`)가 real_fire(확정)·fake_fire(오탐
기각)·hidden_fire(의심→탐색→확정) 3가지 시나리오에서 STEP6.md "완료 기준"대로 동작하는지 확인한다.

## 사전 조건 (이전 단계, 필요한 파일/모델)
- STEP1~5 완료(`sim.launch.py` / `nav.launch.py` / `perception.launch.py` 정상 동작, 특히
  `/fire/vision/detection` `/fire/thermal/detection` `/fire/gas/detection` 이 STEP5 기대 표대로 나옴).
- `colcon build --symlink-install` 성공(9 패키지 — fire_fusion 신설).
- pytest(`test_fusion_logic.py`) 5건 통과 — 확정/오탐 기각/의심→확정/의심 해제/센서 끊김을
  ROS 없이 순수 로직(`FusionStateMachine`)으로 검증(아래 "정적 검증 결과" 참고).

## 정적 검증 결과 (이번 페이즈에서 실행 완료)
- `colcon build --symlink-install` 전체 9패키지 성공(경고만).
- `python3 -m pytest src/fire_fusion/test/ src/fire_perception/test/ src/fire_navigation/test/`
  → 26건 전부 통과(fire_fusion 5건 포함, 기존 21건 회귀 없음).
- `ros2 run fire_fusion fusion_node`, `ros2 run fire_fusion mission_manager_node` 를 각각
  `use_sim_time:=false` 로 3~4초 실행 → 크래시 없이 정상 초기화 로그 확인
  (`fusion_node 시작`, `mission_manager_node 시작 (PATROL)`).
- `ros2 launch fire_bringup fusion.launch.py --show-args` 정상 로드.
- **실제 Gazebo/Nav2/센서 연동, 3가지 시나리오 전체 동작은 이 페이즈에서 실행하지 않았다** — 아래
  절차로 `/check 6` 에서 확인.

## 구현 중 내린 주요 결정 (검증 시 유의)
1. **`/mission/state`, `/mission/cmd` 토픽 신설**(ARCHITECTURE.md 3절에 반영). `FireStatus.mission_state`
   를 채우려면 mission_manager 의 mission_state 를 fusion_node 가 알아야 해서 추가했다.
   `/mission/cmd resume` 은 `/patrol/cmd resume` 과 동일하게 HOLD 해제 용도로 동작한다(둘 다 구독).
2. **`/fire/event` 는 mission_manager_node 만 발행**(ARCHITECTURE.md 표 그대로). SENSOR_STALE 은
   fusion_node 내부에서도 로그만 남기고(중복 계산이지만 발행은 안 함), mission_manager 가
   `/fire/vision·thermal·gas/detection` 을 직접 구독해 독립적으로 끊김을 감시하고 이벤트를 낸다.
3. **SUSPECT 마커는 "로봇 위치" 중심**(STEP6.md 대로) — `fusion_node` 가 TF(`map`→`base_link`)로
   로봇 위치를 조회한다. AMCL 이 아직 수렴 전이면(TF 없음) 마커가 안 나올 수 있음(정상).
4. **APPROACH 목표 지점의 "코스트맵상 비어있음" 판정**은 `/global_costmap/costmap`
   (OccupancyGrid, TRANSIENT_LOCAL QoS)을 구독해 판정한다. Nav2 가 아직 코스트맵을 한 번도
   못 냈으면(구독 전) **항상 비어있다고 가정**하고 진행한다(최선 노력) — 실제 장애물 회피는
   최종적으로 Nav2 로컬플래너가 처리하므로 안전하지만, 8방향 후보 로직 자체의 검증은 `/check 6`
   에서 선반 뒤 화재(hidden_fire) 접근으로 확인 필요.
5. **STEP4 `camera_pan_node.py` 최소 수정**: 이미 SEARCH_360 이고 이전 훑기가 끝난 상태에서 같은
   모드(`SEARCH_360`)를 재요청하면 재시작하도록 조건 하나를 추가했다(`elif new_mode == MODE_SEARCH
   and not self._search_active:`). 기존 동작(모드가 실제로 바뀔 때의 리셋)은 그대로 유지되므로
   STEP4 완료 기준에는 영향 없음 — mission_manager 가 "못 찾음 → 재탐색" 시 이 경로를 사용한다.
6. **resume 직후 같은 화재 재확정 방지**: HOLD 에서 resume 받으면 그 위치를 기록해두고,
   `resume_ignore_s`(기본 5s) 동안 `approach_distance_m*1.5` 이내에서 다시 CONFIRMED 가 떠도
   APPROACH 로 재진입하지 않는다(fusion 의 히스테리시스가 아직 안 풀렸을 때의 플래핑 방지).
7. **`/fire/event` 의 `stamp` 는 실제(wall-clock) UTC ISO8601**이다(`use_sim_time` 과 무관) —
   MQTT/로그가 시뮬 종료 후에도 의미 있는 시각을 갖도록 한 설계 선택.

## 실행 명령

### 터미널 1 — 시뮬(월드+로봇+브리지)
```bash
source ~/fire_ws/scripts/env.sh
cd ~/fire_ws && colcon build --symlink-install && source install/setup.bash
ros2 launch fire_bringup sim.launch.py headless:=true
```

### 터미널 2 — 내비게이션(순찰)
```bash
source ~/fire_ws/scripts/env.sh && source ~/fire_ws/install/setup.bash
ros2 launch fire_bringup nav.launch.py autostart_patrol:=true
```

### 터미널 3 — 인식 전체(비전 + 열화상 + 가스)
```bash
source ~/fire_ws/scripts/env.sh && source ~/fire_ws/install/setup.bash
ros2 launch fire_bringup perception.launch.py detector:=hsv
```

### 터미널 4 — 융합 + 임무 관리
```bash
source ~/fire_ws/scripts/env.sh && source ~/fire_ws/install/setup.bash
ros2 launch fire_bringup fusion.launch.py
```

### 터미널 5 — 상태/이벤트 관찰
```bash
source ~/fire_ws/scripts/env.sh && source ~/fire_ws/install/setup.bash
ros2 topic echo /fire/status
# 다른 창에서:
ros2 topic echo /fire/event
ros2 topic echo /mission/state
```

### 터미널 6 — RViz(선택, GUI 필요)
```bash
rviz2 -d ~/fire_ws/src/fire_bringup/rviz/nav.rviz
# /fire/markers 를 MarkerArray 디스플레이로 추가해서 확인
```

### 3가지 시나리오 확인 순서
로봇이 순찰하며 자연스럽게 지나가도 되고, 빠르게 보려면 `teleop_twist_keyboard` 로 해당 불
근처로 옮겨도 된다(단, mission_manager 가 `/patrol/cmd pause` 를 보낸 상태에서는 teleop 이
코스트맵 회피와 충돌할 수 있으니 PATROL 상태일 때만 수동 이동).

1. **real_fire** (남쪽 통로, -3.0, -4.3): 비전으로 먼저 보이면 `NONE→VERIFY`, 곧이어 열/가스도
   반응하면 `VERIFY→CONFIRMED`(또는 셋이 거의 동시면 바로 `NONE→CONFIRMED`) → `mission_state
   PATROL→VERIFY→APPROACH→HOLD` 로 전이하는지, 로봇이 real_fire 앞 약 1.5m 지점에 정지하는지 확인.
   `/fire/event` 에 `FIRE_VERIFY`(있었다면) → `FIRE_CONFIRMED` → `ARRIVED_HOLD` 가 순서대로 찍히는지.
2. **fake_fire** (북쪽 통로, 2.0, 4.3): 비전만 반응 → `NONE→VERIFY` → 6초(verify_timeout_s) 동안
   열/가스 안 뜸 → `VERIFY→FALSE_ALARM→NONE`, `mission_state VERIFY→PATROL`. `/fire/event` 에
   `FIRE_VERIFY` 후 `FALSE_ALARM`, `PATROL_RESUMED`. 이후 60초(false_alarm_ignore_s) 안에
   같은 자리를 다시 지나가도 `VERIFY` 로 재진입하지 않는지 확인(`/fire/status` fire_state 가
   계속 NONE).
3. **hidden_fire** (2번 선반 서쪽 모서리 뒤, -4.3, 0.6): 가스가 먼저 반응 → `NONE→SUSPECT`,
   `mission_state PATROL→SEARCH`(순찰 정지, 팬 SEARCH_360). 한 바퀴 돌아도 안 보이면
   `/camera_pan/search_done` 후 감속 순찰 재개 + 재탐색 로그(`SEARCH_360 완료, 미발견 -> 감속
   순찰 재개 + 재탐색`) 확인. 모퉁이를 돌아 비전도 잡히면 `SUSPECT→CONFIRMED`,
   `mission_state SEARCH→APPROACH→HOLD`.
4. **HOLD 해제**: 세 시나리오 중 하나가 HOLD 에 도달하면
   `ros2 topic pub --once /patrol/cmd std_msgs/String "{data: resume}"` (또는 `/mission/cmd`)
   실행 → `mission_state HOLD→PATROL`, `/fire/event` 에 `PATROL_RESUMED`, 순찰 재개 확인.

## 무엇을 보면 되나 (화면/토픽/로그별 기대 결과, 가능하면 수치)
- `/fire/status.fire_state` 가 NONE/SUSPECT/VERIFY/CONFIRMED/FALSE_ALARM 을 시나리오대로 순회.
- `/fire/status.mission_state` 가 fusion 의 fire_state 전이를 따라 PATROL/SEARCH/VERIFY/APPROACH/HOLD
  로 바뀜(단, `/mission/state` 를 fusion_node 가 구독해 채우므로 fusion.launch.py 가 켜져 있어야
  mission_state 가 정확함 — 안 켜져 있으면 기본값 PATROL 로 고정됨에 유의).
- `/fire/event` JSON 이 STEP6.md 스키마(robot_id/event/stamp/fire_state/mission_state/position/
  scores/reason) 그대로 나오고, 전이마다 정확히 1회씩만 찍힘(연속 중복 없음).
- `/fire/markers` : CONFIRMED 시 real_fire 위치에 빨간 구+텍스트, FALSE_ALARM 직후 잠깐 회색 구,
  SUSPECT 동안 로봇 위치 중심 노란 반투명 원(반경 `suspect_marker_radius_m`=2.0m).
- APPROACH 중 `ros2 topic echo /mission/state` 와 함께 로봇이 실제로 화재 앞에서 멈추는지,
  좌표가 화재 위치에서 약 1.5m 떨어졌는지(`ros2 topic echo /amcl_pose` 나 RViz로 확인).

## 체크리스트 (단계 문서의 완료 기준)
- [x] pytest 통과(확정/오탐 기각/의심→확정/의심 해제/센서 끊김) — `test_fusion_logic.py` 5건
- [ ] real_fire: PATROL → VERIFY/CONFIRMED → APPROACH → HOLD — **실행 검증 필요**
- [ ] fake_fire: VERIFY → FALSE_ALARM → PATROL, 60초 내 재트리거 없음 — **실행 검증 필요**
- [ ] hidden_fire: SUSPECT → SEARCH → (모퉁이 후) CONFIRMED → APPROACH → HOLD — **실행 검증 필요**
- [ ] 각 시나리오의 `/fire/event` 로그 첨부 — **실행 필요**

## 안 될 때 확인할 것 (흔한 원인 3~5개와 확인 명령)
1. **`mission_state` 가 항상 PATROL 로만 나옴**: `fusion.launch.py` 를 안 띄웠거나
   `/mission/state` 토픽에 아무도 발행을 안 한 것. `ros2 topic echo /mission/state` 와
   `ros2 node list | grep mission_manager` 로 확인.
2. **APPROACH 에서 로봇이 안 움직임**: `ros2 action list | grep navigate_to_pose` 로 Nav2 액션
   서버가 떠 있는지, `ros2 topic hz /global_costmap/costmap` 로 코스트맵이 나오는지 확인.
   `/patrol_node/set_parameters` 서비스가 없으면(`ros2 service list | grep patrol_node`)
   speed_scale 조정만 안 될 뿐 APPROACH 자체는 별개이므로 영향 없음.
3. **SEARCH_360 이 한 번 돌고 멈춤(재시작 안 됨)**: `camera_pan_node.py` 의 재시작 조건 수정이
   빌드에 반영됐는지 확인(`colcon build --symlink-install --packages-select fire_perception`).
   `/camera_pan/search_done` 이 실제로 발행되는지도 확인.
4. **fake_fire 근처에서도 계속 VERIFY 로 재진입**: `false_alarm_radius_m`/`false_alarm_ignore_s`
   가 너무 작거나, fusion_node 가 재시작되어 무시 목록이 초기화된 것(무시 목록은 fusion_node
   프로세스 메모리에만 있음 — 재시작하면 사라짐, 의도된 동작).
5. **CONFIRMED 인데 fire_position 이 이상한 곳을 가리킴**: vision_node/thermal_node 의 depth
   기반 range·TF 계산이 STEP4/5 에서 검증됐는지 먼저 확인(`/check 4`, `/check 5` 선행 권장).

## 종료 방법
```bash
bash ~/fire_ws/scripts/kill_sim.sh
```
