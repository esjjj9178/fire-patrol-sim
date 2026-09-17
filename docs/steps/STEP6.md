# STEP6 — 가중치 신뢰도 융합 · 임무 관리 상태머신

> **작업 방식 메모**: 구현(`/build-all`) 때는 빌드·정적 검증까지만 한다. 아래의 시뮬 실행 검증·데이터 수집·학습은 검증(`/check`) 때 수행하며, 그 절차를 `docs/verify/` 검증 시트에 옮겨 적는다. "완료 기준"은 검증 시트의 체크리스트가 된다.

## 목표
세 센서를 융합해 화재를 판단하고, 판단에 따라 로봇이 순찰/탐색/검증/접근/대기를 스스로 전환한다.

## 할 일
1. `fire_fusion` 패키지, `config/fusion.yaml`
   ```yaml
   weights: {vision: 0.4, thermal: 0.4, gas: 0.2}
   ema_alpha: 0.3
   sensor_high: 0.5
   confirm_threshold: 0.7
   release_threshold: 0.4
   stale_timeout_s: 1.0          # 센서 메시지 끊기면 점수 0 취급 + 경고
   verify_timeout_s: 6.0
   confirm_hold_s: 1.0           # 조건이 연속 유지되어야 확정
   false_alarm_radius_m: 1.5
   false_alarm_ignore_s: 60.0
   suspect_release_s: 15.0
   approach_distance_m: 1.5
   position_window: 10           # 위치 추정 이동평균 개수
   ```
2. `fusion_node.py` (판단만, 로봇을 움직이지 않음)
   - 센서별 EMA, 오래된 메시지 처리, fused 계산
   - fire_state 판정 (ARCHITECTURE.md 규칙)
     - NONE → VERIFY: vision 높음, 열/가스 낮음
     - NONE/VERIFY/SUSPECT → CONFIRMED: fused ≥ 0.7 && vision 높음 && (thermal 또는 gas 높음), confirm_hold_s 유지
     - NONE → SUSPECT: vision 낮음 && (thermal 또는 gas 높음)
     - VERIFY → FALSE_ALARM: verify_timeout 동안 확정 안 됨 → 그 위치 기록(무시 목록)
     - 해제는 release_threshold 히스테리시스
   - 화재 위치: vision(depth) 추정 우선, 없으면 thermal bearing + depth 조합, 이동평균
   - 무시 목록 반경 안의 비전 검출은 VERIFY로 가지 않음
   - `/fire/status` 10Hz, `/fire/markers` (확정=빨간 구+텍스트, 기각=회색, 의심=노란 반투명 원(로봇 위치 중심))
   - `reason` 필드에 판단 근거 문자열 (예: "vision 0.91 + thermal 0.88 → fused 0.83 ≥ 0.70")
3. `mission_manager_node.py` (행동 담당)
   - mission_state: PATROL / SEARCH / VERIFY / APPROACH / HOLD
   - PATROL: patrol start, 팬 SWEEP_FRONT
   - fire_state=VERIFY → patrol pause, 팬 TRACK(비전 bearing), 결과 대기 → FALSE_ALARM이면 PATROL 복귀
   - fire_state=SUSPECT → patrol pause, 팬 SEARCH_360
     - 360 탐색 중 비전 검출 → TRACK → 판정 대기
     - 못 찾으면 patrol resume(speed_scale 0.5) + 팬 SEARCH_360 반복 → suspect_release_s 동안 가스 낮으면 PATROL 정상 속도
   - fire_state=CONFIRMED → patrol pause → APPROACH: 화재 위치에서 로봇 방향으로 approach_distance 떨어진, 코스트맵상 비어있는 지점 계산 → NavigateToPose
     - 목표 지점이 막혀 있으면 원 둘레 후보 8개 중 가장 가까운 자유 지점
   - 도착 → HOLD: 팬 TRACK 유지, `/fire/event` JSON 발행
   - HOLD 에서 `/patrol/cmd resume` 또는 `/mission/cmd resume` 수신 → 해당 화재를 '처리됨'으로 기록 후 PATROL
   - 모든 전이는 로그 + `/fire/event` 발행
   - `/fire/event` JSON 스키마 (STEP7 MQTT와 공유)
     ```json
     {"robot_id":"fire_bot_01","event":"FIRE_CONFIRMED","stamp":"ISO8601",
      "fire_state":"CONFIRMED","mission_state":"APPROACH",
      "position":{"x":0.0,"y":0.0,"frame":"map"},
      "scores":{"fused":0.0,"vision":0.0,"thermal":0.0,"gas":0.0},
      "reason":"..."}
     ```
     event 종류: FIRE_SUSPECT, FIRE_VERIFY, FIRE_CONFIRMED, FALSE_ALARM, ARRIVED_HOLD, PATROL_RESUMED, SENSOR_STALE
4. `fire_bringup/launch/fusion.launch.py`
5. 단위 테스트(`fire_fusion/test/`): 가짜 FireDetection 시퀀스를 넣어 상태 전이 검증(pytest, ROS 없이 로직 클래스만 테스트되도록 설계)

## 완료 기준
- [ ] pytest 통과(최소: 확정, 오탐 기각, 의심→확정, 의심 해제, 센서 끊김)
- [ ] real_fire: PATROL → VERIFY/CONFIRMED → APPROACH → HOLD
- [ ] fake_fire: VERIFY → FALSE_ALARM → PATROL, 60초 내 재트리거 없음
- [ ] hidden_fire: SUSPECT → SEARCH → (모퉁이 후) CONFIRMED → APPROACH → HOLD
- [ ] 각 시나리오의 `/fire/event` 로그 첨부
