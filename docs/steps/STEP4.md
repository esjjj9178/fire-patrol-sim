# STEP4 — 비전 인식 (HSV → 자동 라벨링 → YOLOv8n CPU 학습) · 카메라 팬

> **작업 방식 메모**: 구현(`/build-all`) 때는 빌드·정적 검증까지만 한다. 아래의 시뮬 실행 검증·데이터 수집·학습은 검증(`/check`) 때 수행하며, 그 절차를 `docs/verify/` 검증 시트에 옮겨 적는다. "완료 기준"은 검증 시트의 체크리스트가 된다.

## 목표
카메라가 스윕하며 빨간 박스(불)를 검출하고 `/fire/vision/detection` 을 발행한다. HSV와 YOLO 둘 다 같은 출력.

## 할 일
1. `fire_perception` 패키지 생성 (ament_python)
2. `camera_pan_node.py`
   - `/camera_pan/mode` 에 따라 `/camera_pan/cmd` 생성
     - SWEEP_FRONT: -π/2 ↔ +π/2 삼각파 (속도 파라미터, 기본 0.5 rad/s)
     - SEARCH_360: -π → +π 한 번 훑고 `/camera_pan/search_done`(std_msgs/Bool) 발행
     - TRACK: `/camera_pan/track_bearing` 방향 유지
     - HOLD: 현재 각도 유지
   - 이 단계에서는 기본 모드 SWEEP_FRONT 로 시작(STEP6 전까지 수동 토픽으로 테스트)
3. `vision_common.py` — 공통 유틸
   - bbox 중심 x → 카메라 기준 각도(HFOV, camera_info 사용) → 팬 각도(joint_states) 더해 base_link 기준 bearing
   - depth 이미지에서 bbox 영역 중앙값 → range
   - TF로 map 좌표 계산 → FireDetection 채우기
4. `hsv_detector` (vision_node 의 한 백엔드)
   - HSV 빨강 두 구간, morphology, 최소 면적, confidence = f(면적비, 채도)
5. `yolo_detector` (다른 백엔드)
   - ultralytics YOLOv8n, CPU, imgsz 320, 클래스 `fire` 1개, conf 0.4
   - 모델 파일 없으면 **경고 후 HSV로 자동 폴백**
   - 추론은 최신 프레임만 처리(큐 1개, 밀리면 드롭)
6. `vision_node.py` — 파라미터 `detector: hsv|yolo`, 발행 `/fire/vision/detection`(검출 없을 때도 detected=false로 5Hz 발행)
7. 데이터셋 파이프라인 (`fire_perception/tools/`)
   - `collect_images.py`: 순찰(또는 teleop) 중 0.5초마다 RGB 저장 → `~/fire_ws/data/raw/`, 목표 250~300장
     - 불 3개가 다양한 거리/각도로 찍히도록 안내, 불이 없는 배경 사진도 20% 포함
   - `auto_label.py`: HSV로 bbox 자동 생성 → YOLO txt 라벨, train/val 8:2 분할 → `data/fire_yolo/` + `data.yaml`
     - 라벨 미리보기 몇 장을 `data/preview/` 에 그려서 저장
   - `train_yolo.py`: yolov8n.pt 기반, `device=cpu, imgsz=320, epochs=25, batch=16, workers=2`, 결과를 `fire_perception/models/fire_yolov8n.pt` 로 복사
     - 시작 전 예상 소요시간 출력, 중간에 끊겨도 `resume` 가능하게
   - `eval_yolo.py`: val mAP50 출력, CPU 추론 FPS 측정
8. `fire_bringup/launch/perception.launch.py` 에 camera_pan + vision 추가(`detector` 인자)
9. 참고: 빨간 박스만 학습하므로 YOLO는 real/fake를 구분하지 못하는 것이 **의도된 동작**(검증은 열/가스 담당)

## 사용자 실행 흐름(안내용)
1. sim + nav(순찰) 실행 → collect_images 실행(약 3~5분)
2. auto_label → preview 확인 → train_yolo(약 10~30분)
3. `detector:=yolo` 로 perception 실행

## 완료 기준
- [ ] SWEEP_FRONT / SEARCH_360 / TRACK 동작 확인
- [ ] HSV 모드에서 불 박스 3개 모두 검출(bearing 오차 < 10°, range 오차 < 0.3m, 정답 위치와 비교 보고)
- [ ] 자동 라벨링 결과 preview 정상
- [ ] YOLO 학습 완료, mAP50 ≥ 0.8, CPU FPS 보고(≥ 5 목표)
- [ ] `detector:=yolo` 에서도 같은 토픽 형식으로 발행
- [ ] 모델 파일 없을 때 HSV 폴백 동작
