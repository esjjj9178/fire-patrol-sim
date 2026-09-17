# STEP2 — fire_bot URDF · 센서 · 스폰 · 브리지

> **작업 방식 메모**: 구현(`/build-all`) 때는 빌드·정적 검증까지만 한다. 아래의 시뮬 실행 검증·데이터 수집·학습은 검증(`/check`) 때 수행하며, 그 절차를 `docs/verify/` 검증 시트에 옮겨 적는다. "완료 기준"은 검증 시트의 체크리스트가 된다.

## 목표
3층 구조 + 회전 마운트를 가진 fire_bot 이 창고에 스폰되고, 모든 센서 토픽이 ROS 2로 나온다.

## 할 일
1. `fire_description` 패키지
   - `urdf/fire_bot.urdf.xacro` 를 파일 분리: `base.xacro`, `layers.xacro`, `sensors.xacro`, `gazebo.xacro`
   - Burger 치수 기반 원통/박스 기본 도형만 사용(메시 불필요). 관성값은 xacro 매크로로 계산
   - 층: plate1(모터·OpenCR), plate2(Jetson·배터리 박스, 질량 반영), plate3(LDS-02), 후방 기둥(`mount_pillar_link`, 직경 0.02, 뒤쪽 x≈-0.06)
   - `camera_pan_joint`: revolute, limit ±3.14, effort/velocity 적당히, damping 설정
   - `camera_link`(D435i 박스 0.09×0.025×0.025), `thermal_link`(MLX90640, 카메라 바로 아래), optical frame 규약 준수(z 전방)
   - 캐스터: 앞뒤 마찰 낮은 구
   - 전체 무게중심 높이를 계산해서 보고(층이 높아 흔들림 우려)
2. Gazebo 플러그인(Harmonic 이름으로: `gz-sim-*-system`)
   - DiffDrive: `/cmd_vel` 구독, odom 발행, 최대 선속 0.22 / 각속 1.8. **TF는 브리지하지 않음**
   - JointStatePublisher(바퀴 + 팬)
   - JointPositionController: `camera_pan_joint`, PID 튜닝, 입력 gz 토픽 → 브리지로 `/camera_pan/cmd`
   - PosePublisher: 로봇 정답 위치 → `/ground_truth/pose` (**SIM ONLY**)
   - 센서: gpu_lidar(360, 0.12~3.5m, 5Hz), imu(베이스 50Hz), rgbd_camera(320×240, HFOV 1.204rad, 10Hz, depth 5Hz), camera imu, thermal(32×24, HFOV 0.96rad, 8Hz)
3. `fire_bringup/config/bridge.yaml` — ARCHITECTURE.md 토픽 표 기준 ros_gz_bridge 설정
   (메시지 타입 표기는 설치 버전에서 실제 동작하는 형식으로)
4. `fire_bringup/launch/sim.launch.py`
   - 인자: `headless`(기본 true), `gui`, `x y yaw`(기본값은 layout yaml의 스폰 위치)
   - 월드 실행 → robot_state_publisher(xacro) → `ros_gz_sim create` 스폰 → bridge → (옵션) RViz
5. `fire_bringup/rviz/sim_check.rviz` — RobotModel, TF, LaserScan, Image(RGB/Depth/Thermal)
6. 간단한 확인용 스크립트 `fire_bringup/scripts/check_topics.sh`
   - 주요 토픽 hz 를 각각 `timeout 8 ros2 topic hz` 로 찍어 표로 출력
7. 팬 조인트 테스트: `ros2 topic pub --once /camera_pan/cmd std_msgs/Float64 "{data: 1.57}"` 로 회전 확인
8. 자동 검증: headless 로 90초 timeout 실행 → check_topics.sh → 종료 정리

## 완료 기준
- [ ] `check_urdf`(또는 xacro 변환) 에러 없음, 무게중심 높이 보고
- [ ] 스폰 후 로봇이 넘어지거나 미끄러지지 않음(정지 상태 10초 odom 변화 < 1cm)
- [ ] `/scan /imu /odom /joint_states /camera/color/image_raw /camera/depth/image_raw /thermal/image_raw /ground_truth/pose` 발행 확인(주기 표)
- [ ] 팬 1.57rad 명령 시 joint_states 값이 따라감, 카메라 영상 방향이 바뀜
- [ ] RViz에서 스캔 후방에 기둥이 찍히는 것 확인(STEP3에서 필터링할 대상)
- [ ] `teleop_twist_keyboard` 로 수동 주행 가능
- [ ] 열화상 이미지에서 real_fire 쪽을 봤을 때 값이 주변보다 높음 (안 되면 원인 기록 → STEP5에서 가상 열화상 폴백)
