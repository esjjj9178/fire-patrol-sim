# ARCHITECTURE — 인터페이스 계약서

모든 단계는 이 문서의 토픽/메시지/프레임 이름을 따른다. 바꿀 땐 이 문서를 먼저 고친다.

## 1. TF 트리
```
map ─(AMCL)─ odom ─(EKF)─ base_footprint ─ base_link
                                            ├─ wheel_left_link / wheel_right_link
                                            ├─ imu_link            (OpenCR IMU)
                                            ├─ plate2_link / plate3_link
                                            ├─ base_scan           (LDS-02)
                                            ├─ mount_pillar_link   (후방 기둥)
                                            └─ camera_pan_link  ←(camera_pan_joint, revolute ±π)
                                                 ├─ camera_link ─ camera_color_optical_frame
                                                 │              └ camera_depth_optical_frame / camera_imu_frame
                                                 └─ thermal_link ─ thermal_optical_frame
```

## 2. 커스텀 메시지 (fire_interfaces)

`FireDetection.msg`
```
std_msgs/Header header          # frame_id: 센서 프레임 또는 base_link
string source                   # "vision" | "thermal" | "gas"
bool detected
float32 confidence              # 0.0 ~ 1.0 (정규화 점수)
float32 raw_value               # vision: 모델 점수, thermal: 최고온도[K], gas: 농도[ppm]
float32 bearing                 # base_link 기준 방위[rad], 모르면 NaN
float32 range                   # [m], 모르면 NaN
geometry_msgs/Point position    # map 좌표 추정치
bool position_valid
int32[4] bbox                   # 이미지 좌표 x1,y1,x2,y2 (없으면 -1)
```

`FireStatus.msg`
```
std_msgs/Header header
string fire_state               # NONE | SUSPECT | VERIFY | CONFIRMED | FALSE_ALARM
string mission_state            # PATROL | SEARCH | VERIFY | APPROACH | HOLD
float32 fused_score
float32 vision_score
float32 thermal_score
float32 gas_score
geometry_msgs/Point fire_position   # map
bool position_valid
string reason                   # 사람이 읽는 판단 근거
```

## 3. 토픽 목록

| 토픽 | 타입 | 발행 | 비고 |
|---|---|---|---|
| `/clock` | rosgraph_msgs/Clock | bridge | |
| `/cmd_vel` | geometry_msgs/Twist | Nav2 | → Gazebo |
| `/odom` | nav_msgs/Odometry | bridge(DiffDrive) | TF는 브리지 안 함 |
| `/odometry/filtered` | nav_msgs/Odometry | EKF | |
| `/joint_states` | sensor_msgs/JointState | bridge | 바퀴 + 팬 |
| `/imu` | sensor_msgs/Imu | bridge | 베이스 IMU (EKF 입력) |
| `/camera/imu` | sensor_msgs/Imu | bridge | D435i IMU (EKF 미사용) |
| `/scan` | sensor_msgs/LaserScan | bridge | |
| `/scan_filtered` | sensor_msgs/LaserScan | laser_filters | Nav2/AMCL 입력 |
| `/camera/color/image_raw` | sensor_msgs/Image | bridge | 320×240 |
| `/camera/color/camera_info` | sensor_msgs/CameraInfo | bridge | |
| `/camera/depth/image_raw` | sensor_msgs/Image | bridge | 32FC1 [m] |
| `/thermal/image_raw` | sensor_msgs/Image | bridge 또는 virtual_thermal | 32×24, mono16 (값 해석은 STEP5에서 확정) |
| `/thermal/temperature_image` | sensor_msgs/Image | thermal_node | 32FC1 [K] (공통 형식) |
| `/gas/concentration` | std_msgs/Float32 | gas_sim_node | ppm |
| `/camera_pan/cmd` | std_msgs/Float64 | camera_pan_node | → Gazebo 위치 제어 [rad] |
| `/camera_pan/mode` | std_msgs/String | mission_manager | SWEEP_FRONT / SEARCH_360 / TRACK / HOLD |
| `/camera_pan/track_bearing` | std_msgs/Float32 | mission_manager | TRACK 모드 목표 방위 |
| `/fire/vision/detection` | fire_interfaces/FireDetection | vision_node | |
| `/fire/thermal/detection` | fire_interfaces/FireDetection | thermal_node | |
| `/fire/gas/detection` | fire_interfaces/FireDetection | gas_sim_node | bearing/range NaN |
| `/fire/status` | fire_interfaces/FireStatus | fusion_node | 10Hz |
| `/fire/event` | std_msgs/String (JSON) | mission_manager | 상태 전이 시 1회 |
| `/fire/markers` | visualization_msgs/MarkerArray | fusion_node | |
| `/fire/debug_image` | sensor_msgs/Image | viewer_node | 합성 영상 |
| `/patrol/cmd` | std_msgs/String | 사용자/mission_manager | start / pause / resume / stop |
| `/patrol/state` | std_msgs/String | patrol_node | |
| `/mission/state` | std_msgs/String | mission_manager | PATROL/SEARCH/VERIFY/APPROACH/HOLD. fusion_node 가 구독해 FireStatus.mission_state 를 채움(STEP6에서 추가) |
| `/mission/cmd` | std_msgs/String | 사용자 | resume(HOLD 해제, `/patrol/cmd resume`과 동일 취급, STEP6에서 추가) |
| `/ground_truth/pose` | geometry_msgs/PoseStamped | bridge | **SIM ONLY** (가스/가상열화상용) |

## 4. 파라미터 파일 위치
- `fire_world/config/warehouse_layout.yaml` — 월드/맵/불의 단일 정의
- `fire_navigation/config/nav2_params.yaml`, `ekf.yaml`, `laser_filter.yaml`, `waypoints.yaml`
- `fire_perception/config/perception.yaml` — HSV 범위, YOLO 경로, 열/가스 점수 변환, 팬 속도
- `fire_fusion/config/fusion.yaml` — 가중치, 임계값, 타임아웃, EMA
- `fire_iot_bridge/config/mqtt.yaml` — `enabled: false` 기본

## 5. 점수 변환 기본값
- vision: 검출 신뢰도 최대값 (HSV는 빨간 면적비·채도 기반 0~1)
- thermal: `clip((Tmax - 330) / (450 - 330), 0, 1)`
- gas: `clip((ppm - 400) / (1500 - 400), 0, 1)` (MQ-2 기저 약 200~300ppm 가정)
- fused: `0.4*v + 0.4*t + 0.2*g`, EMA α=0.3, 확정 0.7 / 해제 0.4 (히스테리시스)
- 개별 센서 "높음" 판정: 점수 ≥ 0.5

## 6. 런치 파일
| 런치 | 내용 | 주요 인자 |
|---|---|---|
| `fire_bringup/sim.launch.py` | 월드 + 로봇 스폰 + 브리지 + robot_state_publisher | `headless`(기본 true), `gui` |
| `fire_bringup/nav.launch.py` | laser filter + EKF + map_server + AMCL + Nav2 + patrol | `autostart_patrol` |
| `fire_bringup/perception.launch.py` | vision + thermal + gas + camera_pan + viewer | `detector`(hsv/yolo), `virtual_thermal` |
| `fire_bringup/fusion.launch.py` | fusion + mission_manager | |
| `fire_bringup/full_demo.launch.py` | 위 전부 + RViz | 위 인자 전달 |
