# PROGRESS

현재 페이즈: B (구현 전체 완료 — STEP1~7 모두 구현 ✅, 검증 페이즈 C 대기, `/check 1`부터 시작)
GitHub 저장소: https://github.com/esjjj9178/fire-patrol-sim
작업 방식: 환경 준비(`/setup`) → 한 번에 구현(`/build-all`) → 단계별 검증(`/check N`, `/pass N`)

| 단계 | 내용 | 구현 | 검증 | 메모 |
|---|---|---|---|---|
| SETUP | 누락 패키지 설치, git/GitHub 연결, 자동 푸시 | ✅ | – | 의존성 모두 사전 설치됨, GitHub public 저장소 생성 |
| STEP1 | 설치 스크립트 점검, 워크스페이스, 창고 월드, 맵 자동 생성 | ✅ | ⬜ | 패키지 뼈대 3개(fire_interfaces/fire_world/fire_bringup), generate_world.py --check ALL PASS, SDF `gz sdf --check` Valid |
| STEP2 | fire_bot URDF(3층+팬 마운트), 센서, 스폰, 브리지 | ✅ | ⬜ | 무게중심 0.112m(base_footprint 기준, 총 1.858kg), check_urdf PASS, bridge.yaml 타입 전부 설치된 ros_gz_bridge convert 헤더 대조 확인 |
| STEP3 | laser filter, EKF, AMCL, Nav2, 웨이포인트 순찰 | ✅ | ⬜ | fire_navigation(ament_python) 신설, waypoints.yaml 은 warehouse_layout.yaml 에서 sync_waypoints 로 자동 생성(단일 관리), nav2_params.yaml 은 Humble 기본값 기반 robot_radius 0.13/inflation 0.35/max 0.18 로 수정, localization_launch.py+navigation_launch.py 재사용 |
| STEP4 | 비전(HSV → 자동 라벨 → YOLOv8n CPU 학습), 카메라 팬 | ✅ | ⬜ | fire_perception(ament_python) 신설. camera_pan_node 4모드, HSV/YOLO 공용 vision_node, 데이터 파이프라인 4종 CLI. YOLO 학습은 `/check 4`에서 사용자가 실행 |
| STEP5 | 열화상 노드, 가스 가상센서 노드 | ✅ | ⬜ | thermal_node/virtual_thermal_node(SIM ONLY)/gas_sim_node 신설. 열화상 스케일(K=raw×0.01)은 gz-sensors8 헤더 기본값 근거로만 확정(실측 미검증). LOS/가스식 pytest 10건 통과 |
| STEP6 | 가중치 융합 + 임무 관리 상태머신 | ✅ | ⬜ | fire_fusion(ament_python) 신설. fusion_logic.FusionStateMachine(순수 로직, pytest 5건: 확정/오탐기각/의심→확정/의심해제/센서끊김 통과) + fusion_node/mission_manager_node. `/mission/state`·`/mission/cmd` 토픽 신설(ARCHITECTURE.md 반영), STEP4 camera_pan_node.py에 SEARCH_360 재시작 조건 1줄 추가 |
| STEP7 | 디버그 영상, RViz 마커, MQTT 설계/스텁, 통합 시나리오 | ✅ | ⬜ | viewer_node(3패널 합성) 신설, fire_iot_bridge(mqtt_bridge_node 스텁+adapters/advantech.py) 신설, full_demo.launch.py(TimerAction 8/10/15초 지연), README.md+docs/MQTT_DESIGN.md 작성. **STEP5 thermal 충돌 위험 해결**: bridge.yaml에서 thermal 항목 분리→bridge_thermal.yaml, sim.launch.py에 virtual_thermal 인자 추가해 UnlessCondition으로 조건부 브리지 |

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
- **[STEP4] bearing 부호 규약(REP-103 CCW+)을 가정해 구현.** `vision_common.pixel_to_camera_angle`이
  이미지 우측 물체를 음의 각도로 변환하도록 부호를 정했는데, 이는 `camera_pan_joint`의 URDF `axis`가
  z축 CCW+ 라는 가정에 근거한다(STEP2에서 확정된 URDF를 실제로 대조하지는 않음). `/check 4`에서
  bearing 부호가 반대로 나오면 `pixel_to_camera_angle`의 부호 하나만 뒤집으면 된다(검증 시트에 기록).
- **[STEP4] perception.yaml 구조 결정.** ARCHITECTURE.md는 hsv_detector/yolo_detector를 별도 절로
  적어뒀지만, ROS2 파라미터 yaml은 노드 이름 단위로만 로드되므로 실제로는 `vision_node:` 절 아래에
  전부 합쳐 넣었다(주석으로 원래 절 구분 표시). 노드 코드는 그대로 hue_low1 등 개별 파라미터로 선언.
- **[STEP4] 데이터 수집/라벨링/학습/평가 도구(collect_images, auto_label, train_yolo, eval_yolo)는
  작성만 하고 실행하지 않았다(시뮬 필요, YOLO 학습 10~30분 소요).** `/check 4`에서 사용자가 순서대로
  실행해 mAP50 ≥ 0.8, CPU FPS ≥ 5 를 확인해야 한다. HSV 자동 라벨링 품질에 학습 성능이 크게 좌우되므로
  `data/preview/`를 꼭 육안 확인할 것.

- **[STEP5] 열화상 스케일은 문서/헤더 조사로만 확정, 실측 안 됨(핵심 위험요소).**
  `/usr/include/gz/rendering8/.../BaseThermalCamera.hh`(`resolution = 0.01f`, 기본 10mK)와
  `ThermalCameraSensor.hh`(SetLinearResolution 문서: "temperature in kelvin / resolution") 근거로
  `K = raw(mono16) × 0.01` 로 가정했고, `gazebo.xacro`에 `<plugin ThermalSensor>` 오버라이드가 없어
  기본값이 적용된다고 판단했다. `/check 5`에서 real_fire(600K) 정면 raw_value 가 570~630K 범위인지
  **반드시 실측 확인** — 벗어나면 `perception.yaml`의 `thermal_node.linear_resolution`(및
  `virtual_thermal_node.linear_resolution`)만 조정하면 된다(값이 raw 값을 스케일하는 유일한 지점).
- **[STEP5] gas_sim_node의 "strength" 해석.** STEP5.md 식 `base_ppm + Σ strength·exp(...)`의
  strength를 warehouse_layout.yaml의 `gas_strength`(0~1 무차원)와 새 파라미터 `peak_ppm`(기본 1200)의
  곱으로 해석했다 — 즉 각 불의 기여량 = `gas_strength × peak_ppm × exp(-d²/2σ²)`. real_fire 바로 앞에서
  base(250)+peak(1200)=1450ppm 근처(ARCHITECTURE.md 임계 1500 바로 아래)가 되도록 peak_ppm을 골랐다.
  `/check 5`에서 반응이 너무 세거나 약하면 `peak_ppm` 하나만 조정.
- **[STEP5] virtual_thermal↔Gazebo thermal 토픽 충돌 — STEP7에서 해결됨.** `bridge.yaml`에서
  thermal 항목을 `bridge_thermal.yaml`로 분리하고, `sim.launch.py`에 `virtual_thermal` 인자를
  추가해 `true`면 `UnlessCondition`으로 이 브리지를 끄도록 고쳤다(`full_demo.launch.py`가
  sim/perception 양쪽에 같은 값을 전달). 정적 검증(launch --show-args)까지만 확인했고,
  실제로 발행자가 1개인지는 `/check 5`·`/check 7`에서 `ros2 topic info /thermal/image_raw -v`로
  확인 필요.
- **[STEP5] gas 방향 힌트(gradient)는 파라미터로 구현했지만 기본 off, 시뮬 검증 안 됨.**
  `enable_gradient_hint:=true`로 켜면 최근 20샘플의 (위치,농도) 최소자승 기울기로 bearing을 채운다 —
  실측 검증은 `/check 5` 이후 필요시 진행.
- **[STEP5] sensor_scenario_test.py는 Gazebo `/world/warehouse/set_pose` 서비스(ros_gz_interfaces/srv/
  SetEntityPose)를 자체적으로 `ros_gz_bridge parameter_bridge`로 띄워 사용한다.** bridge.yaml에는
  서비스 브리지 항목이 없다(토픽만 정의) — 이 스크립트가 실행 시마다 임시로 서비스 브리지 프로세스를
  띄우고 끝나면 종료한다. `/check 5`에서 `ros2 service list | grep set_pose`로 존재 확인.

- **[STEP6] `/mission/state`, `/mission/cmd` 토픽을 새로 만들었다(ARCHITECTURE.md 3절에 반영 완료).**
  FireStatus.mission_state를 fusion_node가 채우려면 mission_manager의 mission_state를 알아야 해서
  추가했다. 둘 다 STEP6.md에는 명시되지 않았던 내부 배선 토픽이므로, 나중에 인터페이스를 다시 볼 때
  참고할 것.
- **[STEP6] APPROACH의 "코스트맵상 비어있는 지점" 판정은 `/global_costmap/costmap`
  (OccupancyGrid, TRANSIENT_LOCAL QoS) 구독으로 구현했고, 코스트맵을 아직 못 받았으면 항상
  "비어있다"고 가정한다(최선 노력 — 실제 회피는 Nav2 로컬플래너가 최종적으로 처리하므로 안전하지만,
  8방향 후보 로직 자체는 `/check 6`에서 hidden_fire처럼 선반 근처인 경우로 실측 필요).
- **[STEP6] mission_manager가 Nav2 액션(`navigate_to_pose`)을 patrol_node의 BasicNavigator와는
  별도의 ActionClient로 직접 호출한다.** patrol_node는 APPROACH 진입 시 `/patrol/cmd pause`로
  자신의 목표를 취소하므로 두 클라이언트가 동시에 활성 목표를 갖지는 않지만, 이 가정이 실제로
  깨지지 않는지 `/check 6`에서 확인 필요.
- **[STEP5→STEP6] STEP4 `fire_perception/camera_pan_node.py`를 한 줄 조건 추가로 수정했다** —
  이미 SEARCH_360이고 이전 훑기가 끝난 상태에서 같은 모드를 재요청하면 재시작하도록(기존
  SWEEP_FRONT/SEARCH_360/TRACK/HOLD 전환 동작 자체는 변경 없음). mission_manager의 "못 찾으면
  재탐색" 로직이 이 경로에 의존한다. `docs/verify/STEP4_VERIFY.md`에도 반영함.

- **[STEP7] full_demo.launch.py의 TimerAction 지연(8/10/15초)은 이 개발 PC 기준 대략값이다.**
  느린 PC거나 처음 실행(디스크 캐시 없음)이면 Nav2/브리지가 늦게 뜨는 경우 perception/fusion이
  일부 초기 메시지를 놓칠 수 있다(치명적이진 않음 — 각 노드가 구독 재시도하므로 곧 정상화).
  `/check 7`에서 느리면 지연값을 늘리는 것을 검토.
- **[STEP7] mqtt_bridge_node의 재접속/오프라인 버퍼링은 로컬 mosquitto로만 단위 스모크
  테스트(연결 시도 로그만 확인)했고, 실제 끊김→재접속→버퍼 flush 시나리오는 `/check 7`에서
  mosquitto를 잠깐 껐다 켜보는 식으로 확인 필요.**
- **[STEP7] scenario_report.py의 화재 판정 매칭은 `/fire/event`의 `position`과 정답 위치 중
  최근접(`_closest_gt_fire`)으로 이름을 추정한다.** 위치 추정 오차가 아주 크면(예: bearing 부호
  문제가 남아있는 경우) 엉뚱한 이름에 매칭될 수 있음 — STEP4 bearing 위험요소와 연동해서 확인.
- **[STEP7] Advantech IoT Suite 실연동은 미구현(설계+TODO 체크리스트만).**
  `fire_iot_bridge/adapters/advantech.py`는 인터페이스와 로컬 mosquitto용 기본 구현만 있고,
  실제 Advantech 브로커 연동은 `docs/MQTT_DESIGN.md` 4절의 체크리스트를 확인한 뒤 별도 작업 필요.

## 변경 이력
- 2026-09-17, STEP6: `fire_perception/camera_pan_node.py`의 `_on_mode()`에 "SEARCH_360 재시작" 조건
  추가(같은 모드 재발행 시 이전 훑기가 끝난 상태면 리셋). 이유: mission_manager_node가
  "SEARCH_360 한 바퀴 돌고도 못 찾으면 재탐색"을 구현하려면 camera_pan_node가 모드 값 재발행만으로
  재시작을 지원해야 했음. 영향: STEP4(완료 기준 재검증 불필요 — 기존 전환 동작 그대로), STEP6.
- 2026-09-17, STEP6: `docs/ARCHITECTURE.md` 3절 토픽 표에 `/mission/state`, `/mission/cmd` 추가.
  이유: FireStatus.mission_state를 fusion_node가 채우기 위한 내부 배선, HOLD 해제 명령의 별칭.
  영향: STEP6(fusion_node/mission_manager_node), STEP7(full_demo/MQTT 설계 시 참고).
- 2026-09-17, STEP7: `fire_bringup/config/bridge.yaml`에서 `/thermal/image_raw` 항목을 제거하고
  `bridge_thermal.yaml`로 분리, `fire_bringup/launch/sim.launch.py`에 `virtual_thermal` 인자 +
  조건부 두 번째 parameter_bridge 노드 추가. 이유: STEP5에서 발견된 위험요소(virtual_thermal:=true
  여도 Gazebo thermal 브리지가 동시에 `/thermal/image_raw`를 발행해 virtual_thermal_node와
  충돌 가능)를 해결. 영향: STEP2(sim.launch.py 인자 추가, 기존 기본 동작은 변경 없음 — 재검증
  불필요), STEP5(STEP5_VERIFY.md 터미널7 절 갱신).
