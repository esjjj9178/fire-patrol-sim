# STEP3 검증

## 이 단계에서 확인하는 것 (2~3줄)
맵을 사전에 알고 있는 fire_bot 이 AMCL 로 초기 위치를 자동 수렴하고, EKF(휠 오도메트리+베이스 IMU)가
`odom→base_footprint` TF 를 발행하며, Nav2 가 8개 웨이포인트를 무한 순찰하고 맵에 없는 장애물 2개를
로컬 코스트맵으로 회피하는지 확인한다. `laser_filters` 로 후방 기둥이 `/scan_filtered`에서 사라지는지,
`/patrol/cmd` pause/resume 이 동작하는지도 함께 본다.

## 사전 조건 (이전 단계, 필요한 파일/모델)
- STEP1(`maps/warehouse.{pgm,yaml}`), STEP2(`fire_description`, `sim.launch.py`, `bridge.yaml`) 완료.
- `colcon build --symlink-install` 성공 (fire_navigation 포함, 5 패키지).
- `ros2 run fire_navigation sync_waypoints --check` PASS (webhouse_layout.yaml 과 waypoints.yaml 8개 일치).
- 로봇 스폰 위치(-6.0, -3.8, yaw 0.0)와 `nav2_params.yaml`의 `amcl.initial_pose` 가 반드시 같은 값이어야
  AMCL이 수동 초기 위치 지정 없이 바로 수렴한다. **스폰 위치를 바꾸면 이 값도 같이 바꿀 것.**

## 실행 명령

### 터미널 1 — 시뮬(월드+로봇+브리지)
```bash
source ~/fire_ws/scripts/env.sh
cd ~/fire_ws && colcon build --symlink-install && source install/setup.bash
ros2 launch fire_bringup sim.launch.py headless:=true
```

### 터미널 2 — 내비게이션(laser filter + EKF + AMCL + Nav2 + 순찰)
```bash
source ~/fire_ws/scripts/env.sh && source ~/fire_ws/install/setup.bash
ros2 launch fire_bringup nav.launch.py autostart_patrol:=true
```
RViz까지 같이 보려면 `rviz:=true` 추가(`fire_bringup/rviz/nav.rviz`: Map/코스트맵/전역·지역경로/스캔).

### 터미널 3 — 상태/오차 관찰
```bash
source ~/fire_ws/scripts/env.sh && source ~/fire_ws/install/setup.bash
ros2 topic echo /patrol/state
# 별도 터미널에서 AMCL 추정 위치와 /ground_truth/pose 비교(수동 또는 직접 echo 비교)
ros2 topic echo /amcl_pose --field pose.pose.position
ros2 topic echo /ground_truth/pose --field pose.position
```

### 터미널 3 — laser_filters 확인
```bash
ros2 topic hz /scan
ros2 topic hz /scan_filtered
# RViz 로 /scan(빨강) vs /scan_filtered 비교 — 후방(약 -x, mount_pillar_link 부근) 점 사라짐 확인
```

### 터미널 3 — pause/resume 수동 테스트
```bash
ros2 topic pub --once /patrol/cmd std_msgs/String "{data: pause}"
ros2 topic echo /patrol/state --once     # PAUSED:<index> 확인
ros2 topic pub --once /patrol/cmd std_msgs/String "{data: resume}"
```

### 터미널 3 — 자동 헤드리스 180초 검증(문서 STEP3.md 9번, 선택)
```bash
source ~/fire_ws/scripts/env.sh && source ~/fire_ws/install/setup.bash
timeout 180 ros2 launch fire_bringup nav.launch.py autostart_patrol:=true &
sleep 170
ros2 topic echo /patrol/state --once
wait
```

### 종료
```bash
bash ~/fire_ws/scripts/kill_sim.sh
```

## 무엇을 보면 되나 (화면/토픽/로그별 기대 결과, 가능하면 수치)
- `/scan_filtered` 에서 base_link 기준 x∈[-0.15,0.0], y∈[-0.06,0.06] 박스 안(후방 기둥) 점이 제거됨.
  `ros2 topic hz` 는 두 토픽 모두 약 5Hz.
- `ros2 topic list`에 `/tf`(map→odom→base_footprint 포함), `ros2 run tf2_tools view_frames` 또는
  `ros2 topic echo /tf --once`로 EKF가 odom→base_footprint 를, AMCL이 map→odom 를 발행하는지 확인.
  EKF 발행 주기 ≥25Hz(`ros2 topic hz /odometry/filtered`, frequency 30 설정).
- 스폰 직후 수동 초기 위치 지정 없이 AMCL이 수렴(`set_initial_pose:true`, `initial_pose` = 스폰 좌표).
  수렴 후 `/amcl_pose` 위치가 `/ground_truth/pose` 와 오차 < 0.2m.
- `/patrol/state` 가 `RUNNING:0` → `RUNNING:1` → ... 로 인덱스가 증가하며 8개 웨이포인트를 순환(한 바퀴 후 0으로 복귀).
- 장애물 2개(`obstacle_1` (0,-3.8), `obstacle_2` (2.0,1.25), 둘 다 in_map:false) 근처를 지날 때
  로컬 코스트맵에 장애물이 나타나고 충돌 없이 우회.
- `pause` 명령 시 `/patrol/state` 가 `PAUSED:<n>`으로 바뀌고 로봇이 멈춤, `resume` 시 같은 인덱스에서 재개.
- 1바퀴 소요 시간과 RTF(`gz stats` 또는 real-time factor 로그) 보고 — 너무 느리면(RTF < 0.5 등)
  조정안(로컬 코스트맵 갱신 주기, 해상도) 제시.

## 체크리스트 (단계 문서의 완료 기준)
- [ ] `/scan_filtered` 에서 기둥 점이 사라짐(RViz 비교) — **실행 검증 필요**
- [ ] TF `map→odom→base_footprint` 정상, EKF 발행 주기 ≥ 25Hz — **실행 검증 필요**
- [ ] 초기 위치 수동 지정 없이 AMCL 수렴(정답 대비 오차 < 0.2m) — **실행 검증 필요**
- [ ] 순찰 1바퀴 완주, 장애물 2개 회피(충돌 없음) — **실행 검증 필요**
- [ ] pause / resume 명령 동작 — **실행 검증 필요**
- [ ] 1바퀴 소요 시간과 RTF 보고 — **실행 검증 필요**
- [x] `colcon build --symlink-install` 성공(5 패키지)
- [x] `ros2 run fire_navigation sync_waypoints --check` PASS
- [x] pytest(`test_waypoints_sync.py`) 통과 — waypoints.yaml ↔ warehouse_layout.yaml 일치, 웨이포인트가 월드 범위 안

## 안 될 때 확인할 것 (흔한 원인 3~5개와 확인 명령)
1. **AMCL이 수렴 안 하거나 엉뚱한 곳에서 시작**: `nav2_params.yaml`의 `amcl.initial_pose` 가
   실제 스폰 위치(`sim.launch.py`의 x/y/yaw 기본값, `warehouse_layout.yaml`의 `robot.spawn`)와
   다른지 확인. 스폰 위치를 바꿨다면 두 곳 다 갱신해야 함.
2. **`/scan_filtered`가 안 나옴**: `ros2 node list`에 `scan_to_scan_filter_chain`이 있는지,
   `laser_filter.yaml`의 파라미터 네임스페이스(`scan_to_scan_filter_chain.ros__parameters`)가
   노드 이름과 일치하는지 확인.
3. **로봇이 장애물에 부딪힘**: `local_costmap`의 `obstacle_layer` observation_sources 가
   `/scan_filtered`를 보고 있는지, `robot_radius`(0.13)·`inflation_radius`(0.35)가 통로 폭(≥1.8m)
   대비 너무 크지 않은지 확인.
4. **pause 해도 로봇이 계속 움직임**: `patrol_node`의 `cancelTask()` 호출이 실제로 Nav2 액션을
   취소하는지 `ros2 action list`/`ros2 node info /patrol_node`로 확인. Nav2 controller_server 가
   취소 요청을 받는지 로그 확인.
5. **speed_scale(SUSPECT 감속)이 반영 안 됨**: `/velocity_smoother/set_parameters` 서비스가 떠 있는지
   (`ros2 service list | grep velocity_smoother`), 서비스 콜 결과를 `ros2 param get /velocity_smoother
   max_velocity` 로 확인. 이 기능은 STEP6에서 mission_manager 가 실제로 사용하기 전까지는
   `ros2 param set /patrol_node speed_scale 0.5` 로 수동 테스트.

## 종료 방법
```bash
bash ~/fire_ws/scripts/kill_sim.sh
```
