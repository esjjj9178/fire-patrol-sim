# STEP7 — 디버그 영상 · RViz · MQTT 설계/스텁 · 통합 시나리오

> **작업 방식 메모**: 구현(`/build-all`) 때는 빌드·정적 검증까지만 한다. 아래의 시뮬 실행 검증·데이터 수집·학습은 검증(`/check`) 때 수행하며, 그 절차를 `docs/verify/` 검증 시트에 옮겨 적는다. "완료 기준"은 검증 시트의 체크리스트가 된다.

## 목표
전체 데모를 한 번에 실행하고, 영상/맵으로 판단 과정을 눈으로 확인하며, IoT 연동 설계가 문서로 준비된다.

## 할 일
1. `fire_perception/viewer_node.py` → `/fire/debug_image` (약 640×300, 5Hz)
   - 왼쪽: RGB + bbox + confidence + (real/fake 구분 없이) 라벨
   - 가운데: 열화상 32FC1 → 컬러맵(INFERNO) 확대, 최고온도 위치 표시, Tmax 텍스트
   - 오른쪽: vision/thermal/gas/fused 막대(임계선 0.5, 0.7), fire_state / mission_state, 가스 ppm
   - 옵션 `show_window:=true` 이면 cv2.imshow 도 사용(Qt 에러 나면 자동으로 끄고 경고)
2. `fire_bringup/rviz/full_demo.rviz` — 맵, 로봇, 스캔, 전역/지역 경로, 코스트맵, 화재 마커, 웨이포인트, 디버그 이미지 패널
3. `fire_bringup/launch/full_demo.launch.py` — sim + nav + perception + fusion + RViz + rqt_image_view(`/fire/debug_image`)
   - 인자: `headless`, `detector`, `virtual_thermal`, `mqtt`
   - 노드 시작 순서/지연(TimerAction)으로 Nav2 준비 후 순찰 시작
4. `fire_iot_bridge` 패키지
   - `docs/MQTT_DESIGN.md`
     - 토픽: `factory/{robot_id}/fire/event`(QoS1), `.../status`(1Hz, QoS0), `.../telemetry`(pose, 배터리 자리, 센서 점수, 1Hz)
     - 명령 수신: `factory/{robot_id}/cmd` (resume / pause / return_home 예약)
     - JSON 스키마(STEP6 event 스키마 공유), LWT(`.../status` = offline, retain), 재접속 정책, 오프라인 버퍼링
     - **Advantech IoT Suite 연동 TODO**: 브로커 주소/인증/디바이스 등록 방식/토픽 규칙 확인 항목 체크리스트, 매핑 계층(`adapters/advantech.py`) 인터페이스만 정의
   - `mqtt_bridge_node.py` 스텁: `enabled: false` 기본. true면 로컬 mosquitto로 발행/명령 수신(paho-mqtt)
   - 테스트 안내: `mosquitto_sub -t 'factory/#' -v`
5. `scripts/run_demo.sh` — 환경 source + full_demo 실행 + 종료 시 정리(trap)
6. `scripts/kill_sim.sh` — 남은 gazebo/ros 프로세스 정리
7. 통합 시나리오 테스트 `fire_bringup/scripts/scenario_report.py`
   - `/fire/event` 와 `/ground_truth/pose` 를 기록 → 시나리오 3종 결과표 + 화재 위치 추정 오차 + 소요 시간을 `data/reports/report_<시간>.md` 로 저장
8. 최종 `README.md` (프로젝트 루트): 구조, 설치, 실행, 파라미터 튜닝 포인트, 실차 이식 시 바꿀 것(SIM ONLY 목록, 실제 MLX90640/MQ-2 드라이버 노드로 교체, Jetson에서 YOLO TensorRT 등)

## 완료 기준
- [ ] `bash scripts/run_demo.sh` 한 줄로 전체 실행
- [ ] 디버그 영상에서 세 패널이 실시간 갱신
- [ ] 세 시나리오가 한 번의 순찰 루프 안에서 기대대로 동작, 리포트 생성
- [ ] `mqtt:=true` 에서 mosquitto_sub 로 event/status 수신, cmd resume 동작
- [ ] README와 MQTT_DESIGN.md 작성
- [ ] PROGRESS.md 모든 단계 ✅, 최종 태그 `v0.1-sim` push, GitHub에서 README 표시 확인
