# fire-patrol-sim — 산업현장 자율주행 화재 탐지 로봇 (시뮬레이션)

ROS 2 Humble + Gazebo Harmonic 기반. 맵을 아는 자율주행 로봇(`fire_bot`, TurtleBot3 Burger 개조)이
창고를 순찰하며 비전(RGB)·열화상·가스 센서를 가중치 융합해 화재를 판단하고, 확정 시 접근·대기한다.
이번 범위는 **PC 시뮬레이션만**(실차 Jetson 이식은 나중 — SIM ONLY 표시 항목 참고).

전체 시나리오·설계 규칙은 [`CLAUDE.md`](CLAUDE.md), 인터페이스 계약은
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), 진행 상태는 [`PROGRESS.md`](PROGRESS.md)를 참고.

## 1. 구조

```
src/
  fire_interfaces/   # msg: FireDetection, FireStatus
  fire_world/        # warehouse_layout.yaml(단일 정의) → worlds/*.sdf + maps/*.pgm,yaml 자동 생성
  fire_description/  # fire_bot URDF(xacro, 3층+팬 마운트) + Gazebo Harmonic 플러그인
  fire_bringup/       # launch(sim/nav/perception/fusion/full_demo/world_only), rviz, bridge 설정
  fire_navigation/    # laser_filter, ekf, nav2_params, patrol_node(웨이포인트 순찰)
  fire_perception/    # vision(hsv/yolo), thermal, virtual_thermal, gas_sim, camera_pan, viewer, 데이터/학습 도구
  fire_fusion/        # fusion_node(가중치 융합 판정) + mission_manager_node(임무 행동 상태머신)
  fire_iot_bridge/    # mqtt_bridge_node(스텁, 기본 비활성) + adapters/advantech.py(인터페이스만)
scripts/              # 설치/환경/정리/데모 스크립트 (sudo 필요한 것은 install_deps.sh 뿐)
docs/                 # SETUP_PROMPT, ARCHITECTURE, MQTT_DESIGN, steps/STEP1~7.md, verify/STEP{N}_VERIFY.md
```

## 2. 설치

```bash
cd ~/fire_ws
bash scripts/check_deps.sh          # 누락 확인 (sudo 불필요)
bash scripts/install_deps.sh        # 누락분만 설치 (사용자가 직접 실행, sudo 비밀번호 1회 요구)
echo 'source ~/fire_ws/scripts/env.sh' >> ~/.bashrc   # ROS_DOMAIN_ID, GZ_SIM_RESOURCE_PATH 등
source ~/fire_ws/scripts/env.sh
```

빌드:
```bash
cd ~/fire_ws && colcon build --symlink-install
source install/setup.bash
```

## 3. 실행

가장 간단하게 전체 데모:
```bash
bash scripts/run_demo.sh                                 # headless Gazebo + RViz + rqt_image_view
bash scripts/run_demo.sh headless:=false                  # Gazebo GUI 도 함께
bash scripts/run_demo.sh detector:=yolo virtual_thermal:=true mqtt:=true
```
종료(Ctrl+C)하면 `scripts/kill_sim.sh` 가 자동으로 남은 프로세스를 정리한다(trap).

단계별로 나눠서 실행하려면(각각 별도 터미널, `source scripts/env.sh` 먼저):
```bash
ros2 launch fire_bringup sim.launch.py headless:=true
ros2 launch fire_bringup nav.launch.py
ros2 launch fire_bringup perception.launch.py detector:=hsv
ros2 launch fire_bringup fusion.launch.py
```

`full_demo.launch.py` 주요 인자: `headless`(기본 true), `gui`, `detector`(hsv|yolo),
`virtual_thermal`(Gazebo 열화상 대신 SIM ONLY 가상 열화상 사용), `mqtt`(로컬 mosquitto 연동), `rviz`.

데이터 수집 → YOLO 학습(STEP4, CPU):
```bash
ros2 run fire_perception collect_images         # sim+nav 순찰 중 RGB 250~300장 수집
ros2 run fire_perception auto_label              # HSV 자동 라벨 → data/fire_yolo/
ros2 run fire_perception train_yolo              # yolov8n, CPU, imgsz=320, epochs=25 (~10~30분)
ros2 run fire_perception eval_yolo               # mAP50, CPU FPS
```

시나리오 리포트(순찰 중 real/fake/hidden fire 판정 로그 + 위치오차):
```bash
python3 install/fire_bringup/share/fire_bringup/scripts/scenario_report.py --duration 600
```

## 4. 파라미터 튜닝 포인트

| 무엇을 바꾸고 싶을 때 | 파일 |
|---|---|
| 월드/맵/불/웨이포인트 배치 | `fire_world/config/warehouse_layout.yaml` (수정 후 `generate_world.py` 재실행 필요) |
| 로봇 치수/센서 스펙/팬 조인트 | `fire_description/urdf/*.xacro` |
| ROS↔Gazebo 토픽 매핑 | `fire_bringup/config/bridge.yaml`, `bridge_thermal.yaml` |
| Nav2/AMCL/EKF/장애물 회피 | `fire_navigation/config/{nav2_params,ekf,laser_filter}.yaml` |
| HSV 색 범위 / YOLO 경로·conf / 팬 속도 | `fire_perception/config/perception.yaml` |
| 열화상 스케일(`linear_resolution`) / 점수 변환 임계 | `fire_perception/config/perception.yaml` (thermal_node/virtual_thermal_node 절) |
| 가스 확산 모델(base/peak/sigma/tau) | `fire_perception/config/perception.yaml` (gas_sim_node 절) |
| 융합 가중치/임계값/타임아웃(확정 0.7, 해제 0.4 등) | `fire_fusion/config/fusion.yaml` |
| MQTT 브로커/토픽/재접속 정책 | `fire_iot_bridge/config/mqtt.yaml`, 설계는 `docs/MQTT_DESIGN.md` |

## 5. 실차(Jetson) 이식 시 바꿀 것

`# SIM ONLY` 로 표시된 부분은 실차에서 반드시 교체해야 한다:

- **가스 센서**: `fire_perception/gas_sim_node.py`(가상 확산 모델) → 실제 MQ-2 아날로그 입력을 읽는
  드라이버 노드로 교체. 출력 메시지 형식(`/gas/concentration`, `/fire/gas/detection`)은 그대로 유지.
- **열화상**: 기본은 Gazebo thermal 카메라 브리지를 쓰지만, `virtual_thermal_node.py`(SIM ONLY 폴백,
  레이아웃 정답 위치 기반)는 실차에 없다 → 실제 MLX90640 I2C 드라이버 노드로 교체(`/thermal/image_raw`
  발행 형식 동일하게 유지하면 `thermal_node.py`는 그대로 재사용 가능).
- **로봇 정답 위치**: `/ground_truth/pose`(PosePublisher, gazebo.xacro) — 실차에는 없음. 이를 구독하는
  `gas_sim_node`/`virtual_thermal_node` 는 애초에 실차에서 안 쓰는 노드이므로 함께 제거.
- **YOLO 추론**: 현재 CPU(`device: cpu`, ultralytics). Jetson Orin Nano 에서는 TensorRT 엔진으로
  변환(`yolo export format=engine`)해 `yolo_detector.py` 의 로드 방식을 교체하는 것을 권장(현재 구조는
  `model_path` 파라미터만 바뀌면 되도록 설계했으나, `.engine` 로딩은 ultralytics 쪽 API 확인 필요).
- **Nav2 로컬라이제이션**: 시뮬은 AMCL(맵 사전 제공)만 쓴다. 실차에서 맵이 부정확하면 SLAM 재구축 필요
  — 이번 범위 밖.
- **배터리/텔레메트리**: `mqtt_bridge_node.py` 의 `telemetry.battery` 는 항상 `null`(SIM ONLY 자리
  예약) — 실차 전원 관리 IC 값을 채워야 함.

## 6. 작업 방식 요약

이 저장소는 `/setup` → `/build-all`(전체 구현, 단계 사이 정지 없음) → `/check N`/`/pass N`(단계별
검증, 사용자 주도) 순서로 만들어졌다. 각 STEP의 구현 결정/가정/위험요소는 `docs/verify/STEP{N}_VERIFY.md`
와 `PROGRESS.md` 를 참고.
