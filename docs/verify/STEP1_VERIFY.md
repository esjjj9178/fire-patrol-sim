# STEP1 검증

## 이 단계에서 확인하는 것 (2~3줄)
Gazebo Harmonic에서 창고 월드(`warehouse.sdf`)가 뜨고, 같은 `warehouse_layout.yaml`에서 생성한
Nav2 맵(`warehouse.pgm/.yaml`)이 RViz에서 월드와 정확히 겹치는지 확인한다.
선반 3줄·장애물 2개·불 3개(real/fake/hidden)가 배치대로 보이는지도 함께 확인한다.

## 사전 조건 (이전 단계, 필요한 파일/모델)
- `colcon build --symlink-install` 완료 (fire_interfaces, fire_world, fire_bringup)
- `bash scripts/check_deps.sh` 누락 0개
- 생성된 산출물: `src/fire_world/worlds/warehouse.sdf`, `src/fire_world/maps/warehouse.{pgm,yaml}`
  (이미 `python3 scripts/generate_world.py` 로 생성해 커밋되어 있음. layout yaml을 고치면 재실행 필요)

## 실행 명령

### 터미널 1 — 정적 재검증(선택)
```bash
source /opt/ros/humble/setup.bash
cd ~/fire_ws/src/fire_world
python3 scripts/generate_world.py --check
```

### 터미널 1 — 빌드 + 월드/맵 GUI 확인
```bash
source ~/fire_ws/scripts/env.sh
cd ~/fire_ws && colcon build --symlink-install && source install/setup.bash
ros2 launch fire_bringup world_only.launch.py headless:=false show_map:=true
```
(GPU 렌더링이 안 되면: `LIBGL_ALWAYS_SOFTWARE=1 ros2 launch fire_bringup world_only.launch.py headless:=false show_map:=true`)

### 터미널 2 — SDF 유효성 / 맵 정합성만 headless로 빠르게 (GUI 없이)
```bash
source ~/fire_ws/scripts/env.sh
gz sdf --check ~/fire_ws/install/fire_world/share/fire_world/worlds/warehouse.sdf
timeout 15 ros2 launch fire_bringup world_only.launch.py headless:=true show_map:=false
```

## 무엇을 보면 되나 (화면/토픽/로그별 기대 결과, 가능하면 수치)
- Gazebo GUI: 15m×10m 바닥, 회색 외벽 4개, 갈색 선반 3줄(간격 통로 약 1.9~2.0m), 회색 장애물 2개,
  빨간 불 박스 3개(남쪽 통로 real_fire, 북쪽 통로 fake_fire, 2번 선반 서쪽 모서리 뒤 hidden_fire)가 보임.
- RViz: `/map` 토픽(Transient Local)이 수신되어 회색/흰색 점유격자가 표시됨.
  선반 모서리 좌표 비교 예: shelf_1 남서쪽 모서리 = 월드 (-4.0, -2.8) ↔ 맵 픽셀 (70, 156)
  [`col=(x-(-7.5))/0.05=70`, `row=200-1-((y-(-5))/0.05)=200-1-44=155~156`] — Gazebo에서 같은 지점을 클릭해 좌표가
  일치하는지 확인.
- `gz sdf --check` → `Valid.` (본 세션에서 이미 확인함)

## 체크리스트 (단계 문서의 완료 기준)
- [x] `bash scripts/check_deps.sh` 가 누락 0개 (SETUP 단계에서 확인 완료)
- [x] `glxinfo -B` 렌더러 확인 — 이 PC는 **Intel Mesa RPL-P**(hardware-accelerated, direct rendering yes).
      CLAUDE.md에 적힌 "AMD 내장 그래픽"과 실제 하드웨어가 다름(아래 위험요소 참고). llvmpipe(소프트웨어 렌더링)는
      아니므로 STEP1 기준상 정상.
- [x] colcon build 성공, `ros2 interface show fire_interfaces/msg/FireDetection` 출력 확인함
- [x] `generate_world.py --check` 모든 항목 PASS (요소 겹침/박스높이/웨이포인트거리/통로폭 1.88m/hidden_fire 시야 3항목)
- [ ] (사용자 확인 필요) 월드가 GUI로 뜨고, 선반/장애물/불 3개가 보임
- [ ] (사용자 확인 필요) RViz 맵과 월드 배치가 일치(선반 모서리 좌표 2곳 비교)

## 안 될 때 확인할 것 (흔한 원인 3~5개와 확인 명령)
1. **Gazebo가 안 뜨거나 검은 화면** → `LIBGL_ALWAYS_SOFTWARE=1` 로 재시도, `glxinfo -B` 로 렌더러 재확인.
2. **`Package 'fire_world' not found`** → `source ~/fire_ws/install/setup.bash` 안 했을 가능성. `source ~/fire_ws/scripts/env.sh` 사용 권장.
3. **RViz에 맵이 안 보임** → `ros2 topic echo /map --once` 로 발행 확인, `map_server`/`lifecycle_manager_map` 노드가 `active` 상태인지 `ros2 lifecycle get /map_server` 로 확인.
4. **맵과 월드가 어긋나 보임** → `src/fire_world/maps/warehouse.yaml` 의 `origin` 값과 `world.size`/`resolution` 이 layout yaml과 일치하는지, `generate_world.py` 를 layout 수정 후 재실행했는지 확인.
5. **불 박스가 열로만 보이고 빨간색이 안 보임(Harmonic 렌더링 이슈)** → `visual` material `ambient`/`diffuse` 값 확인, 문제면 STEP1 이슈로 기록.

## 종료 방법
```bash
# 터미널 1/2 에서 Ctrl+C 후
bash ~/fire_ws/scripts/kill_sim.sh
```
