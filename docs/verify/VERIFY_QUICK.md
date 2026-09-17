# 검증 빠른 요약 (묶음 1~4)

STEP1~7 별 상세 검증은 `docs/verify/STEP{N}_VERIFY.md` 를 따른다. 이 문서는 기능별 4개 묶음으로
통합한 빠른 실행 경로다. 자동 판정 스크립트: `scripts/verify.sh`, 자동 판정 노드:
`fire_bringup/scripts/verify_checker.py`, 런치: `fire_bringup/launch/verify_1~4.launch.py`.

| 묶음 | 내용 | 대응 STEP |
|---|---|---|
| 1 | 월드·로봇 | STEP1+2 |
| 2 | 자율주행 | STEP3 |
| 3 | 센서 인식 | STEP4+5 |
| 4 | 전체 시나리오 | STEP6+7 |

---

## 묶음 1 — 월드·로봇

**명령**: `bash scripts/verify.sh 1`  (자동: `bash scripts/verify.sh 1 --auto`)

**볼 것**:
- Gazebo GUI: 창고(벽/선반/장애물2/불3)가 배치대로 보임
- RViz(sim_check.rviz): LaserScan/RGB/Depth/Thermal 이미지가 갱신됨
- checker 표: 필수 토픽 주기 PASS, 팬이 1.0rad 로 수렴, 정지 중 odom 흔들림 < 2cm

**흔한 문제**:
- Gazebo 렌더링 실패 → `LIBGL_ALWAYS_SOFTWARE=1` 로 재시도
- 센서 토픽이 하나도 안 나옴 → `ros2 node list` 에 `ros_gz_bridge` 있는지 확인
- 팬이 안 수렴 → `/joint_states` 에 `camera_pan_joint` 존재/PID 게인 확인

## 묶음 2 — 자율주행

**명령**: `bash scripts/verify.sh 2`  (자동: `bash scripts/verify.sh 2 --auto`)

**볼 것**:
- RViz(nav.rviz): 로봇이 8개 웨이포인트를 순찰, 장애물 2개 회피, 코스트맵/경로 표시
- checker 표: EKF ≥20Hz, AMCL 오차 < 0.3m, 웨이포인트 인덱스 진행, pause/resume 자동 성공

**흔한 문제**:
- AMCL 이 안 수렴 → `nav2_params.yaml` 의 `amcl.initial_pose` 가 실제 스폰 좌표와 다른지 확인
- 로봇이 장애물에 부딪힘 → `local_costmap` 의 `robot_radius`/`inflation_radius` 확인
- pause 해도 계속 움직임 → `ros2 action list`, controller_server 취소 처리 로그 확인

## 묶음 3 — 센서 인식

**명령**: `bash scripts/verify.sh 3`  (자동: `bash scripts/verify.sh 3 --auto`)

**볼 것**:
- rqt_image_view(/fire/debug_image): RGB+bbox, 열화상 컬러맵 갱신
- checker 표: vision/thermal/gas 토픽 주기 + 불 3개(순간이동)·불 없는 곳 점수표가 기대값과 일치

**흔한 문제**:
- HSV 가 불을 못 찾음 → `perception.yaml` 의 hue/sat/val 범위를 실제 렌더링 색에 맞게 조정
- bearing 부호 반대 → `vision_common.pixel_to_camera_angle` 부호 확인
- 열화상 값이 안 오름 → `thermal_node.linear_resolution` 조정(STEP5 참고)

## 묶음 4 — 전체 시나리오

**명령**: `bash scripts/verify.sh 4`  (자동: `bash scripts/verify.sh 4 --auto`)

**볼 것**:
- RViz(full_demo.rviz)+디버그영상: 마커/3패널 영상 갱신
- `mosquitto_sub -t 'factory/#' -v` 로 event/status 수신
- checker 표: real_fire→FIRE_CONFIRMED, fake_fire→FIRE_VERIFY→FALSE_ALARM,
  hidden_fire→FIRE_SUSPECT/FIRE_CONFIRMED, resume→PATROL_RESUMED, MQTT 수신

**흔한 문제**:
- perception/fusion 이 늦게 붙어 초기 메시지 놓침 → `full_demo.launch.py` TimerAction 지연 값 늘리기
- MQTT 안 붙음 → `systemctl status mosquitto` 확인
- `virtual_thermal:=true` 인데 열화상 2중 발행 → `ros2 topic info /thermal/image_raw -v` 로 발행자 수 확인

---

## 전체 자동 실행

```bash
bash scripts/verify.sh all --auto     # 1 -> 2 -> 3 -> 4 순서로 자동 판정, 묶음별 결과 요약
bash scripts/verify.sh stop           # 남은 시뮬/ROS 프로세스 정리
```

리포트는 `data/reports/verify_group{N}_<시간>.md` 로 남는다.

## 사람이 직접 봐야 하는 것 (자동 판정 불가)

- Gazebo GUI 에서 월드/로봇 외형이 실제로 배치대로 보이는지 (좌표는 맞아도 렌더링이 이상할 수 있음)
- RViz 지도/코스트맵/마커가 실제로 "자연스럽게" 움직이는지(수치는 PASS여도 튐/떨림은 눈으로만 보임)
- YOLO 학습 데이터 미리보기(`data/preview/*.png`)의 bbox 품질
- 디버그 영상 3패널의 배치/가독성
