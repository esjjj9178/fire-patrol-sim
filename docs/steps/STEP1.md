# STEP1 — 설치 스크립트 · 워크스페이스 · 창고 월드 · 맵 자동 생성

> **작업 방식 메모**: 구현(`/build-all`) 때는 빌드·정적 검증까지만 한다. 아래의 시뮬 실행 검증·데이터 수집·학습은 검증(`/check`) 때 수행하며, 그 절차를 `docs/verify/` 검증 시트에 옮겨 적는다. "완료 기준"은 검증 시트의 체크리스트가 된다.

## 목표
Gazebo Harmonic에서 창고 월드가 뜨고, **같은 정의로 만든 Nav2 맵**이 RViz에서 월드와 정확히 겹친다.

## 할 일
1. 설치/환경 스크립트는 **이미 제공됨**(`scripts/`). 구현 중 필요한 패키지가 생기면 `scripts/deps_list.sh` 에 추가하고 사용자에게 `install_deps.sh` 재실행을 요청한다.
2. `scripts/env.sh` 의 `GZ_SIM_RESOURCE_PATH` 가 실제 패키지 구조와 맞는지 확인·수정.
   사용자에게 `~/.bashrc` 에 `source ~/fire_ws/scripts/env.sh` 추가를 안내(직접 수정하지 않음).
3. `.gitignore` 확인(이미 제공). git 은 `/setup` 에서 초기화됨 — 안 되어 있으면 `git init -b main`.
4. 패키지 뼈대 생성: `fire_interfaces`(msg 2개 포함, ARCHITECTURE.md 그대로), `fire_world`, `fire_bringup`.
   나머지 패키지는 해당 단계에서 만든다.
5. `fire_world/config/warehouse_layout.yaml` — 단일 정의 파일
   - 월드 15m×10m, 원점은 창고 중심. 외벽 두께 0.2m, 높이 2.5m
   - 선반 3줄: 길이 8m(x -4~4), 두께 0.6m, 높이 2m, y = -2.5 / 0 / 2.5 부근 (통로 폭 ≥1.8m 확보)
   - 각 요소 속성: `name, type(wall|shelf|obstacle|fire), pose(x,y,yaw), size(l,w,h), color, in_map(bool)`
   - fire 전용 속성: `temperature_k`, `is_real(bool)`, `gas_strength`
   - 장애물 2개(0.5×0.5×0.5, 회색, in_map:false) — STEP3의 순찰 경로 위
   - 불 3개(0.4×0.4×0.5, 빨강, in_map:false): real_fire 600K, fake_fire 293K, hidden_fire 600K
   - 로봇 스폰 위치, 순찰 웨이포인트 초안(서펜타인 루프)도 여기에 둔다
6. `fire_world/scripts/generate_world.py`
   - yaml → `worlds/warehouse.sdf` (Harmonic 문법, 조명, 바닥, 물리 스텝 0.001/RTF 1.0)
     - 월드 플러그인: Physics, UserCommands, SceneBroadcaster, Sensors(render_engine ogre2), Imu, **Thermal 관련 시스템**
     - 불 박스에 Thermal system으로 `temperature` 지정. 일반 물체/주변 온도 293K
   - yaml → `maps/warehouse.pgm` + `maps/warehouse.yaml` (해상도 0.05, `in_map:true` 만, 벽/선반=점유, 나머지=자유)
   - **맵 origin 과 월드 좌표가 정확히 일치**해야 함 (가장 중요)
   - `--check` 옵션: 요소 겹침, 통로 폭, 웨이포인트가 점유칸/장애물 근처(0.4m)에 없는지, 박스 높이 ≥0.3m 검사
7. `hidden_fire` 배치 규칙 검증 (`--check`에 포함)
   - 순찰 웨이포인트 선분 위 어떤 점에서도, 해당 구간 진행방향 ±90° 안에서 **선반에 가려 직선 시야가 없는 구간**이 존재할 것
   - 순찰 경로의 어떤 점과는 거리 ≤2.0m (가스가 닿도록)
   - 모퉁이를 돈 뒤에는 시야가 열릴 것
   - 2D 선분 교차로 계산하고 결과를 표로 출력
8. `fire_bringup/launch/world_only.launch.py` — 월드만 띄우고(`headless` 인자), map_server + RViz로 맵 표시(`show_map:=true`)
9. `fire_bringup/rviz/world_check.rviz`

## 사용자 실행 명령 (안내 예시 — 실제로는 구현 결과에 맞춰 안내)
```
# 터미널 1 (최초 1회)
cd ~/fire_ws && bash scripts/check_deps.sh || bash scripts/install_deps.sh
# 터미널 1
source ~/fire_ws/scripts/env.sh && colcon build --symlink-install && source install/setup.bash
ros2 launch fire_bringup world_only.launch.py headless:=false show_map:=true
```

## 완료 기준
- [ ] `bash scripts/check_deps.sh` 가 누락 0개
- [ ] `glxinfo -B` 렌더러가 AMD/radeonsi(또는 llvmpipe면 사용자에게 알림)
- [ ] colcon build 성공, `ros2 interface show fire_interfaces/msg/FireDetection` 출력
- [ ] `generate_world.py --check` 모든 항목 PASS
- [ ] 월드가 GUI로 뜨고, 선반/장애물/불 3개가 보임
- [ ] RViz 맵과 월드 배치가 일치(선반 모서리 좌표 2곳 비교 보고)
