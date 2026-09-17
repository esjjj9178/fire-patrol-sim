# STEP3 — Laser filter · EKF · AMCL · Nav2 · 웨이포인트 순찰

> **작업 방식 메모**: 구현(`/build-all`) 때는 빌드·정적 검증까지만 한다. 아래의 시뮬 실행 검증·데이터 수집·학습은 검증(`/check`) 때 수행하며, 그 절차를 `docs/verify/` 검증 시트에 옮겨 적는다. "완료 기준"은 검증 시트의 체크리스트가 된다.

## 목표
로봇이 맵을 알고 시작하여, 웨이포인트를 끝없이 순찰하고, 맵에 없는 장애물 2개를 라이다로 피한다.

## 할 일
1. `fire_navigation` 패키지 생성
2. `config/laser_filter.yaml` — `LaserScanBoxFilter` 로 후방 기둥 영역(base_link 기준 박스) 제거 → `/scan_filtered`
3. `config/ekf.yaml` — robot_localization
   - `two_d_mode: true`, frequency 30
   - odom0 = `/odom` (vx, vyaw 사용), imu0 = `/imu` (vyaw 위주, 필요 시 yaw)
   - `publish_tf: true` (odom → base_footprint), world_frame odom
4. `config/nav2_params.yaml` — TurtleBot3 Burger Humble 기본값을 바탕으로 수정
   - 모든 스캔 입력 `/scan_filtered`
   - AMCL: `set_initial_pose: true`, 초기 위치 = layout yaml 스폰 위치(런치에서 주입), base_frame `base_footprint`
   - robot_radius 0.13, inflation 0.35 내외 (통로 폭 고려해 조정)
   - local costmap: obstacle_layer + inflation (장애물 회피 핵심)
   - controller: DWB, 최대 속도 0.18
   - odom 토픽 `/odometry/filtered`
5. `config/waypoints.yaml` — layout yaml 의 웨이포인트를 읽거나 동기화(한 곳에서만 관리하도록 설계)
6. `fire_navigation/patrol_node.py`
   - `nav2_simple_commander.BasicNavigator` 사용, Nav2 active 대기
   - 웨이포인트 순서대로 `goToPose`(또는 followWaypoints), 끝나면 처음부터 반복
   - `/patrol/cmd`: start / pause(cancelTask, 현재 인덱스 기억) / resume(기억한 지점부터) / stop
   - 파라미터 `speed_scale`(SUSPECT 감속용, 컨트롤러 속도 제한 변경 또는 speed limit 토픽 활용 — 가능한 방식 조사 후 선택)
   - `/patrol/state` 발행(IDLE/RUNNING/PAUSED + 현재 인덱스)
   - 목표 실패 시 1회 재시도 후 다음 웨이포인트
7. `fire_bringup/launch/nav.launch.py` — laser filter, EKF, map_server, AMCL, Nav2 bringup, patrol(`autostart_patrol` 인자)
8. `fire_bringup/rviz/nav.rviz` — 맵, 코스트맵, 경로, 웨이포인트 마커
9. 자동 검증: headless + nav 를 timeout 180초로 실행, `/patrol/state` 인덱스가 증가하는지, `/ground_truth/pose` 와 AMCL 위치 오차 로그

## 완료 기준
- [ ] `/scan_filtered` 에서 기둥 점이 사라짐(RViz 비교)
- [ ] TF `map→odom→base_footprint` 정상, EKF 발행 주기 ≥ 25Hz
- [ ] 초기 위치 수동 지정 없이 AMCL 수렴(정답 대비 오차 < 0.2m)
- [ ] 순찰 1바퀴 완주, 장애물 2개 회피(충돌 없음)
- [ ] pause / resume 명령 동작
- [ ] 1바퀴 소요 시간과 RTF(실시간 비율) 보고 — 너무 느리면 조정안 제시
