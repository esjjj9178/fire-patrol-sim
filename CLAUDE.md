# CLAUDE.md — 산업현장 자율주행 화재 탐지 로봇 (시뮬레이션)

이 파일은 프로젝트 전체 시나리오와 작업 규칙이다. **매 세션 시작 시 이 파일과 `PROGRESS.md` 를 먼저 읽고, 작업할 단계 문서를 읽는다.**
사용자와의 대화·설명·주석 요약은 **한국어**로 한다. 코드 식별자와 파일명은 영어.

---

## 0. 작업 방식 (가장 중요) — "한 번에 구현, 단계별 검증"

작업은 두 페이즈로 나뉜다. 현재 페이즈와 각 단계 상태는 `PROGRESS.md` 로 판단한다.

### 페이즈 A — 환경 준비 (`/setup`, 절차는 `docs/SETUP_PROMPT.md`)
1. 설치 스크립트는 **이미 제공**되어 있다: `scripts/deps_list.sh`(목록), `check_deps.sh`(점검, sudo 불필요), `install_deps.sh`(누락분만 설치, 사용자가 실행), `setup_github.sh`, `env.sh`, `kill_sim.sh`.
   목록에 패키지를 추가해야 하면 `deps_list.sh` 만 고친다.
2. `/build-all` 을 `/setup` 없이 바로 실행한 경우에도 먼저 `bash scripts/check_deps.sh` 로 점검한다.
   - 누락이 있으면 사용자에게 `bash scripts/install_deps.sh` 실행을 요청하고 **멈춘다.** (구현 중 유일한 정지 지점)
   - `git remote get-url origin` 이 없으면 `/setup` 을 먼저 권하되, 사용자가 원하면 원격 없이 진행한다(푸시만 생략).

### 페이즈 B — 전체 구현 (멈추지 않고 STEP1 → STEP7)
1. `docs/steps/STEP1.md` ~ `STEP7.md` 를 순서대로 **모두 구현한다.** 단계 사이에 사용자 확인을 기다리지 않는다.
2. 각 단계마다 반드시:
   1. 단계 문서의 "할 일"을 구현한다.
   2. `colcon build --symlink-install` 성공까지 고친다(경고는 허용, 에러는 불허).
   3. **가벼운 정적 검증만** 실행한다: 빌드, `pytest`, `python3 -m py_compile`, `xacro` 변환, `generate_world.py --check`, yaml 문법 검사 등.
      Gazebo를 띄우는 시뮬 검증, 데이터 수집, **YOLO 학습은 이 페이즈에서 하지 않는다**(페이즈 C에서 사용자가 수행).
   4. **검증 시트** `docs/verify/STEP{N}_VERIFY.md` 를 작성한다(형식은 아래).
   5. `PROGRESS.md` 의 해당 단계 "구현"을 ✅ 로 바꾸고, 구현 중 내린 결정·가정·확인 못 한 부분을 "메모"에 적는다.
   6. `git add -A && git commit -m "stepN: 구현" && git tag -a stepN-built -m "stepN 구현"` → **바로 push** (아래 Git 규칙)
3. 나중 단계에서 앞 단계 코드를 고치면 `PROGRESS.md` 변경 이력에 적고, 해당 검증 시트도 갱신한다.
4. 컨텍스트가 길어져 중단되더라도 `/build-all` 을 다시 실행하면 **구현 ✅ 가 아닌 첫 단계부터** 이어서 한다.
5. 전부 끝나면 단계별 구현 요약 표 + 사용자 확인이 필요한 위험 요소(버전 문법 불확실, 열화상 스케일 미확인 등)를 보고하고 `/check 1` 로 검증을 시작하라고 안내한 뒤 멈춘다.

### 페이즈 C — 단계별 검증 (사용자 주도)
- `/check N`: STEP N 검증 시트를 보여주고, 사용자가 실행할 명령을 **터미널별로** 안내한다. Claude가 GUI 없이 대신 확인할 수 있는 항목(timeout 건 headless 실행, 토픽 hz 등)은 직접 실행해 결과를 보고한다.
- 사용자가 결과·에러 로그를 주면 **원인을 좁혀서** 고친다(추측으로 여러 곳 동시 수정 금지). 고친 뒤 재빌드하고, 다시 확인할 명령을 알려준다.
- `/pass N`: 해당 단계 "검증"을 ✅ 로, 커밋 후 `stepN-verified` 태그 → push.
- 검증은 1 → 7 순서를 권장한다. 앞 단계가 검증 안 된 상태에서 뒷 단계 검증을 요청하면 의존 관계를 알려주고 사용자 선택을 따른다.
- 검증 중 고친 내용이 다른 단계에 영향을 주면 해당 단계들의 검증 상태를 🔁(재검증 필요)로 바꾼다.

### 검증 시트 형식 (`docs/verify/STEP{N}_VERIFY.md`)
```
# STEP{N} 검증
## 이 단계에서 확인하는 것 (2~3줄)
## 사전 조건 (이전 단계, 필요한 파일/모델)
## 실행 명령
### 터미널 1 ... / 터미널 2 ...   (source 포함, 복사해서 바로 실행 가능하게)
## 무엇을 보면 되나 (화면/토픽/로그별 기대 결과, 가능하면 수치)
## 체크리스트 (단계 문서의 완료 기준)
## 안 될 때 확인할 것 (흔한 원인 3~5개와 확인 명령)
## 종료 방법
```

### Git 규칙 (자동 푸시)
- 원격 `origin` 이 연결되어 있으면 **커밋이나 태그를 만들 때마다 즉시** `git push origin main --follow-tags` 를 실행한다.
- 검증 중 버그 수정도 수정 단위로 커밋 → push. 커밋 메시지: `stepN: fix - <무엇을>` 형식, 한국어 가능.
- **강제 푸시(`--force`, `-f`) 금지.** 태그를 다시 찍어야 하면 `git tag -d X && git push origin :refs/tags/X` 로 지운 뒤 새로 만들고 push.
- push 가 실패하면(네트워크/인증) 작업은 계속하고, 실패 사실을 PROGRESS.md "사용자 확인 필요 사항"에 적고 보고한다. 다음 커밋 때 다시 push 한다.
- `data/`, `build/`, `install/`, `log/`, `runs/` 는 올리지 않는다(.gitignore). 50MB 넘는 파일은 커밋하지 않는다.

### 실행 관련 규칙
- **`sudo` 명령은 직접 실행하지 않는다.** `scripts/*.sh` 로 만들고 사용자에게 실행을 요청한다.
- Gazebo/RViz/영상 창처럼 **계속 떠 있는 GUI 프로세스는 직접 띄우지 않는다.**
- 직접 시뮬을 돌려 확인할 때(페이즈 C)는 `headless:=true` + **반드시 `timeout`**, 끝나면 `bash scripts/kill_sim.sh` 로 정리한다.
- 모든 명령 전에 `source /opt/ros/humble/setup.bash` (install 이 있으면 `source ~/fire_ws/install/setup.bash` 도).
- 사용자와의 설명은 짧고 명확하게. 긴 로그는 요약해서 보여준다.

---

## 1. 프로젝트 개요

산업현장(창고)에서 **맵을 이미 알고 있는** 자율주행 차량이 웨이포인트를 순찰하며 화재를 탐지한다.
- **1차 탐지: 비전**(RGB, YOLO/HSV)
- **2차 검증: 열화상 + 가스** 센서
- 불이 카메라에 안 보여도 **가스(비가시거리)** 가 먼저 반응할 수 있으며, 이 경우 카메라를 돌려 불을 찾는다.
- 판단은 **가중치 기반 신뢰도 융합**.
- 이번 범위는 **PC 시뮬레이션만**. 실차(Jetson)는 나중. 실차 이식이 쉽도록 시뮬 전용 코드는 명확히 분리·표시한다(`# SIM ONLY`).
- 최종적으로 **Advantech IoT Suite** 를 반드시 연동해야 하지만, 이번에는 **MQTT 브리지 설계 + 비활성 스텁**만 만든다.

## 2. 개발 환경 (고정)

| 항목 | 값 |
|---|---|
| PC | Lenovo IdeaPad Slim 3 15ARP10, Ryzen 5, RAM 16GB, **외장 GPU 없음**(AMD 내장 그래픽) |
| OS | Ubuntu 22.04 |
| ROS | ROS 2 **Humble** |
| 시뮬레이터 | **Gazebo Harmonic** (`ros-humble-ros-gzharmonic`, OSRF 저장소 — PC에 이미 설치된 구성) |
| 언어 | Python 우선(rclpy). 커스텀 메시지만 ament_cmake |
| 딥러닝 | YOLOv8n, **CPU 전용** (ultralytics, torch CPU 휠) |
| 워크스페이스 | `~/fire_ws` (이 파일이 있는 폴더) |

### ⚠️ 버전 함정 (반드시 지킬 것)
- Harmonic(gz-sim 8)은 **`gz` 계열**이다. CLI는 `gz sim`, 환경변수는 `GZ_SIM_RESOURCE_PATH`,
  플러그인 파일명은 `gz-sim-XXX-system`, 클래스명은 `gz::sim::systems::XXX`.
  Fortress/Classic 문서의 `ign gazebo`, `ignition-gazebo-*`, `ignition::gazebo::*`, `IGN_*` 를 **쓰지 않는다.**
- ROS 쪽 패키지 이름은 그대로 `ros_gz_sim`, `ros_gz_bridge` 이다(apt 패키지명만 `ros-humble-ros-gzharmonic-*`).
  **`ros-humble-ros-gz`(Fortress용)는 설치하지 않는다** — gzharmonic 패키지와 충돌한다.
- Humble용 TurtleBot3 Gazebo 예제(Classic 기반)는 참고만 하고 플러그인 문법을 복사하지 않는다.
- SDF/플러그인 문법이 헷갈리면 설치된 예제를 먼저 확인한다:
  `find /usr/share/gz -name "*.sdf" 2>/dev/null | grep -Ei "thermal|diff_drive|joint_position|imu|lidar|rgbd|pose_publisher"`
- `ros_gz_bridge` 메시지 타입은 `gz.msgs.*` 로 통일한다.
- **numpy는 2.x 금지**(`numpy<2`). cv_bridge가 시스템 numpy 1.x로 빌드되어 있다. pip `opencv-python` 도 `<4.12` 로 고정.
- MQTT는 apt `python3-paho-mqtt`(1.x API)를 쓴다. 2.x 전용 `CallbackAPIVersion` 을 쓰지 않는다.
- 모든 노드/런치에 `use_sim_time: true`.
- Humble의 Nav2 기본 컨트롤러는 DWB. Jazzy 전용 파라미터를 쓰지 않는다.

### 성능 예산 (CPU 노트북 기준)
- Gazebo는 기본 **headless**(`-s --headless-rendering`)로 실행, 확인은 RViz + 영상 뷰어로.
  `gui:=true` 인자로 Gazebo GUI도 켤 수 있게 한다.
- RGB 320×240 @10Hz, Depth 320×240 @5Hz, 열화상 32×24 @8Hz, LiDAR 360샘플 @5Hz, IMU 50Hz.
- 렌더링이 안 되면 `LIBGL_ALWAYS_SOFTWARE=1` 폴백과 **가상 열화상 노드**(STEP5) 폴백을 쓴다.

---

## 3. 로봇: fire_bot (TurtleBot3 Burger 개조)

- 베이스: Burger 기본 치수(바퀴 반경 0.033m, 바퀴 간격 0.160m, 몸체 약 0.138×0.178m), OpenCR/모터 그대로.
- **층 구조**
  - 1층(z≈0.01~0.07): 모터·OpenCR 모터 드라이버 (+ OpenCR 내장 IMU → `imu_link`)
  - 2층(z≈0.08): Jetson Orin Nano, 배터리 (시뮬에선 질량/박스로만 표현)
  - 3층(z≈0.14): LDS-02 2D LiDAR(`base_scan`, z≈0.17) + **후방 기둥 1개**(마운트)
  - 최상단(z≈0.28): **팬(pan) 회전 조인트** `camera_pan_joint` (revolute, ±π)
    - 그 위에 D435i(`camera_link`, z≈0.30)와 MLX90640(`thermal_link`, 카메라 바로 아래)을 **같이 장착 → 함께 회전**
- 후방 기둥이 LiDAR 후방 일부를 가림 → `laser_filters` 로 `/scan` → `/scan_filtered`.
- **LiDAR 높이(0.17m) 때문에 장애물·불 박스는 높이 0.3m 이상**이어야 라이다에 보인다.
- **EKF용 IMU는 베이스(OpenCR) IMU를 쓴다.** D435i IMU는 회전 마운트 위에 있어 팬 회전이 섞이므로 EKF에 넣지 않는다(토픽만 발행).

### 센서 사양 (시뮬)
| 센서 | 모델 | 시뮬 구현 |
|---|---|---|
| RGB-D | Intel RealSense D435i | Gazebo `rgbd_camera` (HFOV 69°) |
| 열화상 | MLX90640 (BAB, 32×24, 55°×35°) | Gazebo `thermal` 카메라 + 박스별 온도(Thermal system). 폴백: 가상 열화상 노드 |
| 가스 | MQ-2 | **가상 센서 노드** (불까지 거리 기반 농도 + 1차 지연 + 노이즈) |
| LiDAR | LDS-02 | Gazebo `gpu_lidar` |
| IMU | OpenCR 내장 | Gazebo `imu` |

## 4. 월드: 단순 창고

- **단일 정의 파일** `fire_world/config/warehouse_layout.yaml` 에서 벽·선반·장애물·불을 정의하고,
  스크립트가 **SDF 월드 + Nav2 맵(pgm/yaml)** 을 동시에 생성한다 → 맵과 월드가 정확히 일치(SLAM 없음).
- 크기 15m×10m, 선반 줄 여러 개(높이 2m), 통로 폭 ≥1.8m.
- 맵에 넣는 것: 벽, 선반. **맵에 넣지 않는 것: 장애물 2개, 불 박스 3개**(라이다로만 인지 → 회피 시연).
- 화재 시나리오 3종

| 이름 | 외형 | 온도 | 목적 |
|---|---|---|---|
| `real_fire` | 빨간 박스 | 600K | 비전+열+가스 모두 반응 → 확정 |
| `fake_fire` | 빨간 박스(소화기함 역할) | 293K | 비전만 반응 → **검증에서 기각** |
| `hidden_fire` | 빨간 박스 | 600K | 선반 모퉁이 뒤. **가스가 먼저** 반응 → 의심 → 카메라 탐색 → 모퉁이 돌면 확정 |

- 불 박스는 0.4×0.4×0.5m, 주변 온도 293K.

## 5. 주행

- 맵 사전 제공(map_server) + **AMCL**(초기 위치 자동 설정) + **EKF**(robot_localization: 휠 오도메트리 + 베이스 IMU → `odom→base_footprint`).
  Gazebo DiffDrive의 TF는 브리지하지 않는다(EKF와 충돌 방지).
- **Nav2 웨이포인트 순찰**(`nav2_simple_commander`), 무한 루프, `/patrol/cmd` 로 pause/resume.
- 장애물은 로컬 코스트맵(`/scan_filtered`)으로 회피.

## 6. 화재 판단

- 각 센서 노드는 **동일한 메시지** `fire_interfaces/FireDetection` 을 발행한다(형식은 `docs/ARCHITECTURE.md`).
- 비전은 `detector:=hsv|yolo` 파라미터로 교체 가능(출력 동일).
- **융합**: `fused = 0.4*vision + 0.4*thermal + 0.2*gas` (EMA 평활, 파라미터 파일로 조정)
  - `fused ≥ 0.7` 이고 비전+(열 또는 가스) 동시 → **CONFIRMED**
  - 비전만 높음 → **VERIFY**(카메라 고정·정지 후 재확인, 시간 초과 시 **FALSE_ALARM** 기록 후 그 위치 반경 1.5m 60초 무시)
  - 열/가스만 높음 → **SUSPECT**
- **임무 관리(행동)**
  - PATROL: 순찰 + 카메라 전방 ±90° 스윕
  - SUSPECT: 정지 → 카메라 360° 탐색 → 못 찾으면 감속 순찰 + 전방위 스윕 유지(가스가 내려가면 해제)
  - CONFIRMED → APPROACH: 화재 위치 1.5m 앞까지 Nav2 이동
  - HOLD: 정지, RViz 마커·알림(`/fire/event`) 발행, 사용자 `resume` 명령 시 순찰 재개

## 7. 시각화 / IoT

- **디버그 영상 1장 합성**: [RGB + 박스] | [열화상 컬러맵 + 최고온도] | [센서 점수 막대 + 상태] → `/fire/debug_image` → `rqt_image_view` 로 확인.
- RViz: 맵, 로봇, 스캔, 경로, 화재 마커(확정=빨강, 기각=회색, 의심=노랑 원).
- **MQTT 브리지(설계 + 비활성 스텁)**: `factory/{robot_id}/fire/event|status|telemetry`, JSON, 로컬 mosquitto로 테스트. Advantech IoT Suite 매핑은 문서의 TODO로 남긴다.

## 8. 패키지 구조

```
~/fire_ws/src/
  fire_interfaces/   # msg: FireDetection, FireStatus (ament_cmake)
  fire_world/        # layout yaml, 월드/맵 생성 스크립트, worlds/, maps/
  fire_description/  # fire_bot URDF(xacro) + Gazebo 플러그인
  fire_bringup/      # launch (sim, nav, perception, fusion, full_demo), rviz, 공통 config
  fire_navigation/   # nav2 params, ekf, laser filter, patrol_node
  fire_perception/   # vision(hsv/yolo), thermal, gas_sim, camera_pan, viewer, 데이터/학습 스크립트
  fire_fusion/       # fusion_node, mission_manager_node, marker
  fire_iot_bridge/   # mqtt_bridge_node(스텁), 설계 문서
```
상세 인터페이스·토픽·TF는 **`docs/ARCHITECTURE.md`** 를 따른다. 인터페이스를 바꾸면 이 문서도 같이 고친다.

## 9. 코드 품질 규칙
- 매직넘버 금지 → 파라미터(yaml)로.
- 노드마다 파일 상단 docstring: 역할 / 구독 / 발행 / 파라미터.
- 시뮬 전용 로직(정답 위치 사용, 가상 센서)은 `# SIM ONLY` 주석 + 파라미터로 끌 수 있게.
- 대용량 산출물(`data/`, `runs/`, `build/`, `install/`, `log/`)은 git에 넣지 않는다. 학습된 `*.pt` 1개는 예외로 허용.
