# STEP5 검증

## 이 단계에서 확인하는 것 (2~3줄)
`thermal_node`(Gazebo 열화상 → 켈빈 변환 → `/fire/thermal/detection`)와 `gas_sim_node`(가상
MQ-2, `/fire/gas/detection`)가 STEP5.md의 "기대 결과 표"대로 반응하는지 확인한다.
`virtual_thermal_node`(SIM ONLY 폴백)도 같은 표를 통과하는지, 가스 농도가 거리에 따라
기대대로 감쇠하는지 그래프로 확인한다.

## 사전 조건 (이전 단계, 필요한 파일/모델)
- STEP1~4 완료(`sim.launch.py`, `nav.launch.py`, `perception.launch.py` 정상 동작).
- `colcon build --symlink-install` 성공(fire_perception 포함, 6 패키지).
- pytest(`test_geometry_los.py`, `test_gas_model.py`) 통과 — LOS 판정/가스 농도식/1차 지연
  응답을 순수 함수로 검증(ROS/시뮬 불필요).
- **열화상 스케일은 문서 조사로만 확정**했고 아직 실측 안 됨(아래 "열화상 스케일 확정 근거" 참고) —
  이 단계에서 real_fire Tmax ≈ 600K(±30) 인지 실측 확인이 **핵심 체크리스트**.

## 열화상 스케일 확정 근거 (문서 조사, 실측 필요)
- `/usr/include/gz/rendering8/gz/rendering/base/BaseThermalCamera.hh:97-98`:
  `protected: float resolution = 0.01f; // Linear resolution. Defaults to 10mK.`
- `/usr/include/gz/sensors8/gz/sensors/ThermalCameraSensor.hh` `SetLinearResolution` 문서:
  "The thermal image data returned will be temperature in kelvin / resolution."
- `min_temp`/`max_temp` 기본값은 `-gz::math::INF_F` / `+gz::math::INF_F` (클리핑 없음).
- `fire_description/urdf/gazebo.xacro` 의 thermal 센서(`format: L16`, 32×24, HFOV 0.96)에
  `<plugin filename="gz-sim-thermal-sensor-system">` 오버라이드가 없으므로 기본 resolution(0.01)이
  적용된다고 판단 → **raw(uint16, ros mono16) = K / 0.01, 즉 K = raw × 0.01**.
  600K → raw 60000(uint16 범위 내), 293K → raw 29300.
- ros_gz_bridge 의 `gz.msgs.Image` L16 포맷은 `sensor_msgs::image_encodings::MONO16`("mono16")으로
  변환된다고 알려져 있음(ARCHITECTURE.md 에도 이미 mono16 로 명시) — **이 부분은 문서/헤더로만 확인했고
  실제 브리지 동작은 실측 안 됨**.
- `thermal_node.py` 의 `linear_resolution` 파라미터(기본 0.01)로 이 가정을 조정 가능.

## 실행 명령

### 터미널 1 — 시뮬(월드+로봇+브리지)
```bash
source ~/fire_ws/scripts/env.sh
cd ~/fire_ws && colcon build --symlink-install && source install/setup.bash
ros2 launch fire_bringup sim.launch.py headless:=true
```

### 터미널 2 — 내비게이션(순찰)
```bash
source ~/fire_ws/scripts/env.sh && source ~/fire_ws/install/setup.bash
ros2 launch fire_bringup nav.launch.py autostart_patrol:=true
```

### 터미널 3 — 인식 전체(비전 + 열화상 + 가스)
```bash
source ~/fire_ws/scripts/env.sh && source ~/fire_ws/install/setup.bash
ros2 launch fire_bringup perception.launch.py detector:=hsv
```

### 터미널 4 — 열화상 스케일 실측 (real_fire 정면에서)
```bash
ros2 topic echo /thermal/image_raw --field encoding --once     # mono16 확인
ros2 topic echo /thermal/temperature_image --field encoding --once  # 32FC1 확인
ros2 topic echo /fire/thermal/detection
# raw_value(=Tmax, K) 가 real_fire(600K) 정면에서 570~630K 범위인지 확인.
# 벗어나면 perception.yaml 의 thermal_node.linear_resolution 을 실측값에 맞게 조정 후 재빌드.
```

### 터미널 5 — 가스 시나리오 확인
```bash
ros2 topic echo /gas/concentration
ros2 topic echo /fire/gas/detection
# real_fire/hidden_fire(is_real:true) 근처에서 250 → 1450 부근까지 천천히(τ≈2s) 상승,
# fake_fire 근처에서는 250 부근(기저)에 머무는지 확인.
```

### 터미널 6 — 세 센서 종합 시나리오 표 (SIM ONLY, set_pose 서비스로 순간이동)
```bash
source ~/fire_ws/scripts/env.sh && source ~/fire_ws/install/setup.bash
ros2 run fire_perception sensor_scenario_test
# 내부에서 `ros2 run ros_gz_bridge parameter_bridge
# /world/warehouse/set_pose@ros_gz_interfaces/srv/SetEntityPose` 를 임시로 띄운다.
# 출력 표를 STEP5.md "기대 결과 표"와 비교해 기록.
```

### 터미널 7 — virtual_thermal 폴백 확인 (Gazebo 열화상 대신 가상 노드)
```bash
# 터미널3의 perception.launch.py 를 Ctrl+C 후 재실행
ros2 launch fire_bringup perception.launch.py detector:=hsv virtual_thermal:=true
# 주의: bridge.yaml 이 여전히 Gazebo thermal 을 /thermal/image_raw 로 브리지하므로
# 두 발행자가 겹칠 수 있음 — 겹치면 sim.launch.py 실행 시 bridge.yaml 에서 thermal 항목을
# 빼거나(또는 remap) 확인할 것. thermal_node 는 소스에 무관하게 같은 형식을 받으므로
# 동작 자체는 동일해야 한다.
ros2 run fire_perception sensor_scenario_test   # 같은 표가 나오는지 재확인
```

### 가스 농도-거리 그래프 저장 (선택, matplotlib)
```bash
python3 - <<'EOF'
import math
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
base, peak, sigma = 250.0, 1200.0, 1.5
d = np.linspace(0, 8, 200)
ppm = base + peak * np.exp(-d**2 / (2 * sigma**2))
plt.plot(d, ppm)
plt.axhline(1500, color='r', ls='--', label='score_high')
plt.axhline(400, color='orange', ls='--', label='score_low')
plt.xlabel('distance [m]'); plt.ylabel('ppm'); plt.legend()
plt.title('gas concentration vs distance (target, before 1st-order lag)')
import os
os.makedirs(os.path.expanduser('~/fire_ws/data/plots'), exist_ok=True)
plt.savefig(os.path.expanduser('~/fire_ws/data/plots/gas_vs_distance.png'))
EOF
```

### 종료
```bash
bash ~/fire_ws/scripts/kill_sim.sh
```

## 무엇을 보면 되나 (화면/토픽/로그별 기대 결과, 가능하면 수치)
- `/thermal/image_raw` encoding = `mono16`, `/thermal/temperature_image` encoding = `32FC1`.
- real_fire 정면 raw_value(Tmax) ≈ 600K(±30) → 벗어나면 `linear_resolution` 재확정.
- **기대 결과 표** (STEP5.md 동일):

  | 위치 | vision | thermal | gas |
  |---|---|---|---|
  | real_fire 앞 2m | 높음 | 높음 | 높음 |
  | fake_fire 앞 2m | 높음 | 낮음 | 낮음 |
  | hidden_fire 모퉁이 전(안 보임) | 낮음 | 낮음 | 중간~높음 |
  | 불 없는 곳 | 낮음 | 낮음 | 낮음 |

  `sensor_scenario_test` 출력 표를 여기에 옮겨 적고 비교.
- 가스: `/gas/concentration` 이 계단 변화 없이 τ≈2s 로 부드럽게 올라감(1차 지연), 정상 상태에서
  base+peak≈1450 부근(±노이즈 15ppm)까지 근접.
- `virtual_thermal:=true` 에서도 위 표와 같은 경향(정확한 수치는 달라도 high/low 판정은 동일).

## 체크리스트 (단계 문서의 완료 기준)
- [ ] 열화상 스케일 확정, real_fire Tmax ≈ 600K(±30) — **실측 필요**(현재는 문서 조사만)
- [ ] 위 기대 결과 표와 실제 측정 표 비교 보고 — **실행 검증 필요**
- [ ] virtual_thermal 모드도 같은 표 통과 — **실행 검증 필요**
- [ ] 가스 농도 그래프(거리별) 출력 이미지 저장 `data/plots/gas_vs_distance.png` — **실행 필요**
- [x] `colcon build --symlink-install` 성공(6 패키지)
- [x] pytest(`test_geometry_los.py` 4건, `test_gas_model.py` 6건) 통과
- [x] `ros2 launch fire_bringup perception.launch.py --show-args` 정상 로드(`virtual_thermal` 인자 포함)
- [x] `ros2 run fire_perception {thermal_node,gas_sim_node,virtual_thermal_node}` 짧은 timeout 실행 시
      크래시 없음(레이아웃 로드 로그: gas_sim_node "is_real 불 2개", virtual_thermal_node "불 3개,
      가림막 7개" 확인됨)

## 안 될 때 확인할 것 (흔한 원인 3~5개와 확인 명령)
1. **Tmax 가 600K 근처로 안 나옴**: `linear_resolution` 가정이 설치 버전과 다를 수 있음.
   `ros2 topic echo /thermal/image_raw --field data --once | head` 로 raw 값을 직접 보고
   `실측K / raw` 로 실제 resolution 을 역산해 `perception.yaml` 에 반영.
2. **gas_sim_node 가 fake_fire 근처에서도 반응**: layout yaml 의 `is_real` 필드가 fake_fire 는
   `false` 인지 확인(`grep is_real src/fire_world/config/warehouse_layout.yaml`). 코드는
   `is_real` 로 필터링하므로 yaml 값이 원인일 가능성이 큼.
3. **virtual_thermal 에서 불이 하나도 안 보임**: `/ground_truth/pose` 가 실제로 오는지
   (`ros2 topic hz /ground_truth/pose`), `/joint_states` 에 `camera_pan_joint` 가 있는지 확인.
   가시선 판정이 너무 엄격하면 `test_geometry_los.py` 케이스를 실제 로봇 위치로 바꿔 재현.
4. **sensor_scenario_test 가 set_pose 서비스를 못 찾음**: `ros2 service list | grep set_pose` 로
   브리지가 떴는지 확인. world 이름이 `warehouse` 가 아니면(`warehouse_layout.yaml` 의
   `world.name`) 스크립트가 자동으로 맞는 이름을 쓰므로 layout 파일이 최신인지 확인.
5. **가스 농도가 너무 급격히/느리게 변함**: `tau_s`(기본 2.0s), `rate_hz`(기본 10)를
   `perception.yaml` 의 `gas_sim_node` 절에서 조정.

## 종료 방법
```bash
bash ~/fire_ws/scripts/kill_sim.sh
```
