# STEP2 검증

## 이 단계에서 확인하는 것 (2~3줄)
3층 구조 + 팬 회전 마운트를 가진 fire_bot(URDF/xacro)이 창고 월드에 스폰되고,
LiDAR/IMU/RGB-D/열화상/조인트/오도메트리/정답위치 등 모든 센서·상태 토픽이 정상 주기로 발행되는지 확인한다.
팬 조인트가 명령대로 회전하고 카메라 방향이 함께 바뀌는지도 함께 확인한다.

## 사전 조건 (이전 단계, 필요한 파일/모델)
- STEP1 완료: `worlds/warehouse.sdf`, `maps/warehouse.{pgm,yaml}` 생성됨
- `colcon build --symlink-install` 완료 (fire_description 포함)
- 무게중심 높이(정적 계산, base_footprint 기준): **0.112m**, 전체 질량 1.858kg
  (wheel_separation 0.160m → 반폭 0.08m보다 높음 → 급가감속/급회전 시 흔들림 가능성 있음.
  검증 중 로봇이 스폰 직후나 주행 중 넘어지면 1순위 의심 지점)

## 실행 명령

### 터미널 1 — xacro/URDF 정적 확인(선택, 이미 구현 단계에서 통과 확인함)
```bash
source /opt/ros/humble/setup.bash
cd ~/fire_ws && colcon build --symlink-install && source install/setup.bash
xacro src/fire_description/urdf/fire_bot.urdf.xacro > /tmp/fire_bot.urdf
check_urdf /tmp/fire_bot.urdf
```

### 터미널 1 — 시뮬 실행(headless)
```bash
source ~/fire_ws/scripts/env.sh
cd ~/fire_ws && colcon build --symlink-install && source install/setup.bash
ros2 launch fire_bringup sim.launch.py headless:=true
```
GUI로 로봇 자세/기울어짐을 직접 보고 싶으면 `headless:=false gui:=true` 로 실행.
RViz(RobotModel/TF/LaserScan/Image)까지 같이 보려면 `rviz:=true` 추가.

### 터미널 2 — 토픽 발행/주기 확인
```bash
source ~/fire_ws/scripts/env.sh && source ~/fire_ws/install/setup.bash
bash src/fire_bringup/scripts/check_topics.sh
```

### 터미널 2 — 정지 상태 10초 odom 변화(넘어짐/미끄러짐 확인)
```bash
timeout 10 ros2 topic echo /odom --field pose.pose.position
```

### 터미널 2 — 팬 조인트 테스트
```bash
ros2 topic pub --once /camera_pan/cmd std_msgs/Float64 "{data: 1.57}"
timeout 5 ros2 topic echo /joint_states --field position
# rqt_image_view /camera/color/image_raw 로 화면 방향이 바뀌는지 육안 확인
```

### 터미널 3 — 수동 주행
```bash
source /opt/ros/humble/setup.bash
ros2 run teleop_twist_keyboard teleop_twist_keyboard
```

### 종료
```bash
bash ~/fire_ws/scripts/kill_sim.sh
```

## 무엇을 보면 되나 (화면/토픽/로그별 기대 결과, 가능하면 수치)
- `check_topics.sh` 출력에서 아래 주기가 대략 나와야 함(±20% 오차는 CPU 부하로 허용):
  `/scan` 5Hz, `/imu` 50Hz, `/odom` 30Hz(odom_publish_frequency), `/joint_states`(주기는 명시 안 됨, 발행만 확인),
  `/camera/color/image_raw` 10Hz, `/camera/depth/image_raw`(rgbd_camera와 같은 센서, image와 유사 주기),
  `/thermal/image_raw` 8Hz, `/camera/imu` 50Hz, `/ground_truth/pose` 10Hz(static_update_frequency).
- 스폰 직후 10초간 `/odom` position 변화가 1cm 미만(넘어지거나 미끄러지지 않음).
- 팬에 1.57rad 명령 시 `/joint_states`의 `camera_pan_joint` 값이 점점 1.57에 수렴(PID 게인 p=5.0/i=0.05/d=0.3),
  `/camera/color/image_raw` 화면이 좌(또는 우)로 90° 회전한 시야로 바뀜.
- RViz LaserScan에서 로봇 후방(약 -x 방향, mount_pillar_link 근처)에 기둥으로 인한 결측/반사 점이 보임
  → STEP3에서 `laser_filters`로 `/scan_filtered`에서 제거 예정.
- `teleop_twist_keyboard`로 전후좌우 회전 시 `/odom`이 반응.
- 열화상: `real_fire`(600K) 쪽을 팬으로 향하게 하면 `/thermal/image_raw` 최대값이 주변보다 뚜렷이 높음.
  Gazebo Harmonic의 thermal 카메라 출력 스케일/인코딩은 이 단계에서 확정하지 않았고(STEP5에서 확정),
  안 되면(값이 안 오르거나 평평하면) 원인을 기록하고 STEP5의 `virtual_thermal_node` 폴백으로 넘어간다.

## 체크리스트 (단계 문서의 완료 기준)
- [ ] `check_urdf`(xacro 변환) 에러 없음 — **정적 검증 완료, PASS**
- [ ] 무게중심 높이 보고 — **완료: 0.112m** (검증 시 실측 기울어짐 여부 확인 필요)
- [ ] 스폰 후 정지 상태 10초 odom 변화 < 1cm
- [ ] `/scan /imu /odom /joint_states /camera/color/image_raw /camera/depth/image_raw /thermal/image_raw /ground_truth/pose` 발행 확인(주기 표)
- [ ] 팬 1.57rad 명령 시 joint_states 값이 따라감, 카메라 영상 방향이 바뀜
- [ ] RViz에서 스캔 후방에 기둥이 찍히는 것 확인
- [ ] `teleop_twist_keyboard`로 수동 주행 가능
- [ ] 열화상에서 real_fire 쪽을 봤을 때 값이 주변보다 높음(안 되면 원인 기록 → STEP5 가상 열화상 폴백)

## 안 될 때 확인할 것 (흔한 원인 3~5개와 확인 명령)
1. **Gazebo가 안 뜨거나 렌더링 실패**: `glxinfo -B`로 렌더러 확인, 안 되면
   `LIBGL_ALWAYS_SOFTWARE=1 ros2 launch fire_bringup sim.launch.py headless:=true` 로 재시도.
2. **스폰은 되는데 센서 토픽이 하나도 안 나옴**: `ros2 topic list`로 브리지 노드가 살아있는지,
   `ros2 node list`에 `ros_gz_bridge`가 있는지 확인. `gz topic -l`로 Gazebo 쪽 토픽 이름이
   `src/fire_bringup/config/bridge.yaml`의 `gz_topic_name`과 정확히 일치하는지 대조(특히 `camera/image`,
   `camera/depth_image`, `thermal/image_raw`, `model/fire_bot/pose`).
3. **로봇이 스폰 직후 넘어짐**: 무게중심 0.112m가 원인일 수 있음 →
   `sim.launch.py gui:=true headless:=false`로 직접 보고, 필요하면 plate2/plate3 질량 배치나
   base_radius를 조정(이 경우 STEP2 재구현 필요, PROGRESS.md 변경 이력에 기록).
4. **팬이 안 돌거나 진동함**: JointPositionController PID(p=5.0/i=0.05/d=0.3)가 안 맞을 수 있음 →
   `ros2 topic echo /joint_states`로 camera_pan_joint velocity/position 관찰, 게인 조정.
5. **열화상 값이 온도를 반영하지 않음(전부 같은 값)**: Harmonic Thermal 시스템이 world 플러그인
   (STEP1의 `warehouse.sdf`)에 등록돼 있는지, 불 박스에 `<plugin>...Thermal...</plugin>` 또는
   `<temperature>` 태그가 있는지 확인. 안 되면 정상 — STEP5에서 확정/폴백 처리.

## 종료 방법
```bash
bash ~/fire_ws/scripts/kill_sim.sh
```
