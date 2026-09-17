# PROGRESS

현재 페이즈: B (구현 대기)
GitHub 저장소: https://github.com/esjjj9178/fire-patrol-sim
작업 방식: 환경 준비(`/setup`) → 한 번에 구현(`/build-all`) → 단계별 검증(`/check N`, `/pass N`)

| 단계 | 내용 | 구현 | 검증 | 메모 |
|---|---|---|---|---|
| SETUP | 누락 패키지 설치, git/GitHub 연결, 자동 푸시 | ✅ | – | 의존성 모두 사전 설치됨, GitHub public 저장소 생성 |
| STEP1 | 설치 스크립트 점검, 워크스페이스, 창고 월드, 맵 자동 생성 | ✅ | ⬜ | 패키지 뼈대 3개(fire_interfaces/fire_world/fire_bringup), generate_world.py --check ALL PASS, SDF `gz sdf --check` Valid |
| STEP2 | fire_bot URDF(3층+팬 마운트), 센서, 스폰, 브리지 | ✅ | ⬜ | 무게중심 0.112m(base_footprint 기준, 총 1.858kg), check_urdf PASS, bridge.yaml 타입 전부 설치된 ros_gz_bridge convert 헤더 대조 확인 |
| STEP3 | laser filter, EKF, AMCL, Nav2, 웨이포인트 순찰 | ✅ | ⬜ | fire_navigation(ament_python) 신설, waypoints.yaml 은 warehouse_layout.yaml 에서 sync_waypoints 로 자동 생성(단일 관리), nav2_params.yaml 은 Humble 기본값 기반 robot_radius 0.13/inflation 0.35/max 0.18 로 수정, localization_launch.py+navigation_launch.py 재사용 |
| STEP4 | 비전(HSV → 자동 라벨 → YOLOv8n CPU 학습), 카메라 팬 | ⬜ | ⬜ | YOLO 학습은 검증 때 사용자가 실행 |
| STEP5 | 열화상 노드, 가스 가상센서 노드 | ⬜ | ⬜ | |
| STEP6 | 가중치 융합 + 임무 관리 상태머신 | ⬜ | ⬜ | |
| STEP7 | 디버그 영상, RViz 마커, MQTT 설계/스텁, 통합 시나리오 | ⬜ | ⬜ | |

상태 표기: ⬜ 대기 / 🔄 진행 중 / ✅ 완료 / 🔁 재검증 필요 / ⚠️ 보류(사유를 메모에)

## 사용자 확인 필요 사항
- **[STEP1] GPU 렌더러 불일치**: CLAUDE.md 는 "AMD 내장 그래픽"을 명시하지만 실제 이 PC는 `glxinfo -B` 기준
  Intel Mesa Graphics (RPL-P)이다. hardware-accelerated(direct rendering yes, llvmpipe 아님)라 STEP1 완료
  기준상 문제는 없으나, 실제 하드웨어 구성이 문서와 다르다는 점은 확인 바람.
- **[STEP1] pip `packaging` 버전 충돌로 환경 수정**: `pip install --user` 로 깔린 `setuptools 78.1.0` 이
  구버전 `packaging 21.3` 과 호환되지 않아(`canonicalize_version() got an unexpected keyword argument
  'strip_trailing_zero'`) 커스텀 msg 패키지(`fire_interfaces`)의 `ament_cmake_python` 빌드가 실패했다.
  `pip install --user --upgrade "packaging>=23"` 로 해결(현재 26.3). sudo 불필요, 다른 패키지(numpy<2, torch,
  ultralytics) 에 영향 없음을 확인. 이후 모든 커스텀 ROS2 메시지 패키지 빌드에 필요하므로 기록해 둠.
- **[STEP1] world_only.launch.py 의 `gz sdf --check`, `generate_world.py --check`, `colcon build` 만 정적으로
  확인했고, Gazebo GUI / RViz 맵 정합은 사용자가 `/check 1` 에서 직접 확인해야 함.**
- **[STEP2] 무게중심 0.112m vs 반폭(바퀴간격 0.160m의 절반) 0.08m** — 층이 높아 흔들림 우려가 실제로 있음.
  스폰 직후·급가감속 시 넘어지는지는 `/check 2`에서 실제로 확인 필요(정적 계산만으로는 판단 불가).
- **[STEP2] 열화상 원시값 스케일 미확정.** Gazebo Harmonic thermal 카메라의 출력 인코딩/온도 대응은
  STEP5에서 확정 예정. `/check 2`에서 real_fire를 비췄을 때 값이 안 오르면 정상적인 예상 범위이며,
  STEP5의 virtual_thermal 폴백으로 처리한다.
- **[STEP3] AMCL 초기 위치를 파라미터에 고정값으로 박아둠.** `set_initial_pose: true` +
  `initial_pose.{x,y,z,yaw}` = 로봇 스폰 좌표(-6.0, -3.8, 0.0)를 `nav2_params.yaml`에 직접 기록했다.
  스폰 위치(`warehouse_layout.yaml`의 `robot.spawn`, `sim.launch.py`의 x/y/yaw 기본값)를 바꾸면
  `nav2_params.yaml`의 `amcl.initial_pose`도 같이 바꿔야 한다(런치 인자로 자동 주입하지 않음 — 더 안전하지만
  수동 동기화 필요, `/check 3`에서 실측 오차 확인 시 함께 검토).
- **[STEP3] SUSPECT 감속(speed_scale) 구현 방식 결정.** `patrol_node`의 `speed_scale` 파라미터가 바뀌면
  `/velocity_smoother/set_parameters` 서비스를 호출해 `max_velocity`/`min_velocity`를 동적으로 낮추는
  방식을 택했다(다른 대안: DWB 파라미터 직접 변경, costmap speed limit 토픽 — 이번엔 velocity_smoother가
  가장 단순해서 선택). mission_manager(STEP6)가 실제로 이 파라미터를 설정하기 전까지는 미사용 상태이며,
  `/check 3`에서 `ros2 param set /patrol_node speed_scale 0.5` 로 수동 검증 가능.
- **[STEP3] 1바퀴 소요 시간/RTF, AMCL 수렴 오차, 장애물 회피, pause/resume 실동작은 정적 검증(빌드/pytest)
  범위 밖이라 `/check 3`에서 실제 시뮬레이션으로 확인 필요.**

## 변경 이력
(이전 단계 코드를 고쳤을 때: 날짜, 단계, 이유, 영향받은 단계)
