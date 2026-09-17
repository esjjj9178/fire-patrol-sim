# STEP4 검증

## 이 단계에서 확인하는 것 (2~3줄)
카메라 팬(`camera_pan_node`)이 SWEEP_FRONT/SEARCH_360/TRACK/HOLD 4모드로 동작하고,
`vision_node`(HSV 백엔드)가 불 3개를 검출해 `/fire/vision/detection`(bearing/range/map 위치 포함)을
발행하는지 확인한다. 이어서 사용자가 데이터 수집 → 자동 라벨링 → YOLOv8n(CPU) 학습을 진행하고
`detector:=yolo` 로도 같은 형식의 출력이 나오는지, 모델이 없을 때 HSV 로 자동 폴백하는지 확인한다.

## 사전 조건 (이전 단계, 필요한 파일/모델)
- STEP1~3 완료(`sim.launch.py`, `nav.launch.py` 정상 동작).
- `colcon build --symlink-install` 성공 (fire_perception 포함, 6 패키지).
- pytest(`test_hsv_detector.py`) 통과 — 합성 이미지 기준 HSV 검출/방위 계산 단위 테스트, ROS/시뮬 불필요.
- YOLO 학습 전에는 `src/fire_perception/models/fire_yolov8n.pt` 가 없음(정상) → `detector:=yolo` 로 띄우면
  경고 로그 후 자동으로 HSV 로 동작해야 한다.

## 실행 명령

### 터미널 1 — 시뮬(월드+로봇+브리지)
```bash
source ~/fire_ws/scripts/env.sh
cd ~/fire_ws && colcon build --symlink-install && source install/setup.bash
ros2 launch fire_bringup sim.launch.py headless:=true
```

### 터미널 2 — 내비게이션(순찰, 카메라가 여러 각도/거리를 보게 함)
```bash
source ~/fire_ws/scripts/env.sh && source ~/fire_ws/install/setup.bash
ros2 launch fire_bringup nav.launch.py autostart_patrol:=true
```

### 터미널 3 — 인식(HSV 백엔드)
```bash
source ~/fire_ws/scripts/env.sh && source ~/fire_ws/install/setup.bash
ros2 launch fire_bringup perception.launch.py detector:=hsv
```

### 터미널 4 — 팬 모드 수동 테스트
```bash
ros2 topic pub --once /camera_pan/mode std_msgs/String "{data: SWEEP_FRONT}"
ros2 topic echo /camera_pan/cmd    # -pi/2~+pi/2 사이를 삼각파로 왕복하는지 확인

ros2 topic pub --once /camera_pan/mode std_msgs/String "{data: SEARCH_360}"
ros2 topic echo /camera_pan/search_done   # 한 바퀴 후 data:true 1회 발행 확인

ros2 topic pub --once /camera_pan/track_bearing std_msgs/Float32 "{data: 1.0}"
ros2 topic pub --once /camera_pan/mode std_msgs/String "{data: TRACK}"
ros2 topic echo /camera_pan/cmd    # 1.0 rad 로 수렴하는지 확인

ros2 topic pub --once /camera_pan/mode std_msgs/String "{data: HOLD}"
ros2 topic echo /camera_pan/cmd    # 값 고정 확인
```

### 터미널 4 — 검출 결과 확인 (불 3개 앞에서)
```bash
ros2 topic echo /fire/vision/detection
# real_fire(-3.0,-4.3), fake_fire(2.0,4.3), hidden_fire(-4.3,0.6) 각각 앞 2m 지점에서
# detected:true, bbox 유효, bearing/range/position(map) 값을 기록해 정답 좌표와 비교(오차 계산)
```

### 터미널 5 — 데이터 수집 → 라벨링 → 학습 → 평가 (순찰 진행 중, 5~40분 소요)
```bash
source ~/fire_ws/scripts/env.sh && source ~/fire_ws/install/setup.bash
ros2 run fire_perception collect_images                 # ~data/raw/ 에 280장 모일 때까지 대기(약 2~3분, 0.5s 간격)
ros2 run fire_perception auto_label                      # data/fire_yolo/ + data/preview/ 생성
ls ~/fire_ws/data/preview                                 # bbox 미리보기 육안 확인
ros2 run fire_perception train_yolo                       # CPU, epochs 25, 약 10~30분
ros2 run fire_perception eval_yolo                        # mAP50, CPU FPS 출력
```

### 터미널 3(재시작) — YOLO 백엔드로 인식 재실행
```bash
# 터미널 3의 perception.launch.py 를 Ctrl+C 후
ros2 launch fire_bringup perception.launch.py detector:=yolo
ros2 topic echo /fire/vision/detection   # 같은 메시지 형식으로 발행되는지 확인
```

### 폴백 확인 (모델 파일을 임시로 옮겨서)
```bash
mv ~/fire_ws/src/fire_perception/models/fire_yolov8n.pt /tmp/fire_yolov8n.pt.bak
ros2 launch fire_bringup perception.launch.py detector:=yolo
# 로그에 "YOLO 모델 파일 없음 ... -> HSV 폴백" 경고가 뜨고 검출은 계속 동작하는지 확인
mv /tmp/fire_yolov8n.pt.bak ~/fire_ws/src/fire_perception/models/fire_yolov8n.pt
```

### 종료
```bash
bash ~/fire_ws/scripts/kill_sim.sh
```

## 무엇을 보면 되나 (화면/토픽/로그별 기대 결과, 가능하면 수치)
- SWEEP_FRONT: `/camera_pan/cmd` 가 -1.5708~1.5708 사이를 약 0.5rad/s 로 왕복.
- SEARCH_360: -π→+π 를 한 번 훑은 뒤 `/camera_pan/search_done`(Bool, true) 1회 발행, 이후 그 각도 유지.
- TRACK: `/camera_pan/cmd` 가 `track_bearing` 값(≤1rad/s 속도 제한)으로 수렴.
- HOLD: `/camera_pan/cmd` 가 더 이상 변하지 않음.
- HSV 모드: 불 3개 모두 `detected:true`, bbox 유효(x1<x2, y1<y2), **bearing 오차 < 10°**,
  **range 오차 < 0.3m**(정답: real_fire (-3.0,-4.3), fake_fire (2.0,4.3), hidden_fire (-4.3,0.6) — 단,
  hidden_fire 는 선반에 가려 안 보이는 지점에서는 애초에 미검출이 정상이며, STEP1 hidden_fire 시야
  규칙대로 모퉁이를 돈 뒤에만 검출되어야 함).
- `auto_label` 실행 후 `data/preview/*.png` 에 bbox 가 실제 불 위치에 그려져 있음(육안 확인).
- `train_yolo` 완료 후 `src/fire_perception/models/fire_yolov8n.pt` 생성, `eval_yolo` 결과
  **mAP50 ≥ 0.8**, **CPU FPS ≥ 5** 목표(미달 시 STEP4.md 파라미터 조정 — epochs/데이터 품질 등 검토).
- `detector:=yolo` 에서도 `/fire/vision/detection` 필드 구성이 HSV 모드와 동일.
- 모델 파일 없을 때: 로그에 폴백 경고가 뜨고 검출 자체는 계속 동작(HSV 로 대체).

## 체크리스트 (단계 문서의 완료 기준)
- [ ] SWEEP_FRONT / SEARCH_360 / TRACK 동작 확인 — **실행 검증 필요**
- [ ] HSV 모드에서 불 박스 3개 모두 검출(bearing 오차 < 10°, range 오차 < 0.3m, 정답 위치와 비교 보고) — **실행 검증 필요**
- [ ] 자동 라벨링 결과 preview 정상 — **실행 검증 필요**
- [ ] YOLO 학습 완료, mAP50 ≥ 0.8, CPU FPS 보고(≥ 5 목표) — **사용자가 학습 실행 후 확인**
- [ ] `detector:=yolo` 에서도 같은 토픽 형식으로 발행 — **실행 검증 필요**
- [ ] 모델 파일 없을 때 HSV 폴백 동작 — **실행 검증 필요**
- [x] `colcon build --symlink-install` 성공(6 패키지)
- [x] pytest(`test_hsv_detector.py`) 9건 통과 — HSV 검출/bearing/range/yaw 변환 단위 테스트
- [x] `ros2 launch fire_bringup perception.launch.py --show-args` 정상 로드
- [x] `ros2 run fire_perception {camera_pan_node,vision_node}` 짧은 timeout 실행 시 크래시 없음(토픽 없어도 대기만 함)

## 안 될 때 확인할 것 (흔한 원인 3~5개와 확인 명령)
1. **HSV 가 불을 못 찾음**: 선반/바닥 색이 빨강에 걸리는지 `ros2 run rqt_image_view rqt_image_view`
   로 `/camera/color/image_raw` 확인. `perception.yaml`의 `hue_low1~2/hue_high1~2/sat_min/val_min` 을
   Gazebo 렌더링 실제 색상에 맞게 조정(조명/렌더러 차이로 채도가 낮게 나올 수 있음).
2. **bearing 부호가 반대로 나옴**: `vision_common.pixel_to_camera_angle`/`camera_angle_to_bearing` 은
   REP-103(CCW+) 가정으로 구현했다 — 실제로 이미지 우측 물체가 양의 bearing 으로 나오면
   `camera_pan_joint` 축 방향(URDF `axis`)과 부호가 반대인 것이므로 `pixel_to_camera_angle` 의
   부호를 뒤집을 것.
3. **range/position 이 항상 NaN**: `/camera/depth/image_raw` 가 실제로 32FC1 로 오는지
   `ros2 topic echo /camera/depth/image_raw --field encoding --once` 로 확인. depth 가 0 또는
   NaN 뿐이면 bbox 중앙 마진(`depth_bbox_range`의 margin_ratio)을 줄여볼 것.
4. **YOLO 학습이 너무 느리거나 멈춤**: `train_yolo` 는 `~/fire_ws/runs/detect/fire_yolov8n/` 에
   체크포인트를 남기므로 중단 후 `ros2 run fire_perception train_yolo --resume` 로 이어서.
   `workers`(기본 2)/`batch`(기본 16)를 낮춰 메모리 압박 확인(RAM 16GB).
5. **`detector:=yolo` 인데 계속 HSV 로만 동작**: `src/fire_perception/models/fire_yolov8n.pt` 가
   실제로 있는지, `colcon build` 후 symlink install 이 `install/fire_perception/share/fire_perception/models/`
   에도 반영됐는지 확인(모델은 소스 트리 경로를 기본으로 찾으므로 재빌드 없이도 즉시 반영돼야 함 —
   안 되면 `vision_node` 파라미터 `model_path` 를 절대 경로로 직접 지정해서 테스트).

## 종료 방법
```bash
bash ~/fire_ws/scripts/kill_sim.sh
```
