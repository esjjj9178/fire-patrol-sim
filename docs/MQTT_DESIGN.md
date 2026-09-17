# MQTT_DESIGN — IoT 브리지 설계 (STEP7)

`fire_iot_bridge/mqtt_bridge_node.py` 의 설계 문서. 구현은 **`enabled: false` 기본 스텁**이며,
Advantech IoT Suite 실연동은 이 문서의 TODO 절과 `adapters/advantech.py` 인터페이스로 남겨둔다.

## 1. 토픽

| 토픽 | 방향 | QoS | retain | 주기 |
|---|---|---|---|---|
| `factory/{robot_id}/fire/event` | 로봇→서버 | 1 | false | 상태 전이 시 1회(STEP6 mission_manager `/fire/event` 그대로 중계) |
| `factory/{robot_id}/fire/status` | 로봇→서버 | 0 | **true** | 1Hz (LWT 도 이 토픽) |
| `factory/{robot_id}/fire/telemetry` | 로봇→서버 | 0 | false | 1Hz |
| `factory/{robot_id}/cmd` | 서버→로봇 | 1(구독) | - | 명령 수신 시 |

`{robot_id}` 는 `config/mqtt.yaml` 의 `robot_id` (기본 `fire_bot_01`).

## 2. 페이로드 스키마

### 2.1 event / status — STEP6 `/fire/event` JSON 그대로 공유
```json
{"robot_id":"fire_bot_01","event":"FIRE_CONFIRMED","stamp":"ISO8601",
 "fire_state":"CONFIRMED","mission_state":"APPROACH",
 "position":{"x":0.0,"y":0.0,"frame":"map"},
 "scores":{"fused":0.0,"vision":0.0,"thermal":0.0,"gas":0.0},
 "reason":"..."}
```
event 종류: `FIRE_SUSPECT`, `FIRE_VERIFY`, `FIRE_CONFIRMED`, `FALSE_ALARM`, `ARRIVED_HOLD`,
`PATROL_RESUMED`, `SENSOR_STALE`.

`fire/status` 페이로드(1Hz, 요약본):
```json
{"robot_id":"fire_bot_01","stamp":"ISO8601","status":"online",
 "fire_state":"NONE","mission_state":"PATROL"}
```
LWT(Last Will and Testament): 브로커 연결 시 `will_set(status_topic, {"status":"offline"}, qos=0, retain=true)`
을 등록해, 비정상 종료 시 서버가 `status:"offline"` 을 (retain 이므로) 즉시 받는다. 정상 연결 시
`{"status":"online"}` 을 같은 토픽에 retain 발행해 덮어쓴다.

### 2.2 telemetry
```json
{"robot_id":"fire_bot_01","stamp":"ISO8601",
 "pose":{"x":0.0,"y":0.0,"frame":"map"},
 "battery": null,
 "scores":{"fused":0.0,"vision":0.0,"thermal":0.0,"gas":0.0}}
```
`battery` 는 시뮬에 배터리 모델이 없어 자리만 예약(`null`, **SIM ONLY** — 실차에서 채움).

### 2.3 cmd (서버→로봇)
```json
{"cmd": "resume"}
```
`resume` 은 즉시 `/mission/cmd` 로 중계되어 mission_manager_node 의 HOLD 해제와 동일하게 동작한다(STEP6).
`pause` 는 `/patrol/cmd pause` 와 동일 문자열로 중계 가능(mission_manager_node 가 `/patrol/cmd`, `/mission/cmd`
둘 다 구독하므로 `cmd` 값을 그대로 전달하면 된다). `return_home` 은 **예약**(현재 mission_manager 에 대응 동작 없음,
STEP6 범위 밖 — 향후 "귀환 웨이포인트로 NavigateToPose" 로 구현 예정).

## 3. 재접속 / 오프라인 정책

- `paho.mqtt.client.Client.reconnect_delay_set(min, max)` 로 지수 백오프 재접속(기본 1s~30s, `config/mqtt.yaml`).
- 연결 끊긴 동안 `/fire/event` 는 `mqtt_bridge_node` 내부 `deque(maxlen=offline_buffer_max)` 에 버퍼링되고,
  재연결(`on_connect`) 시 순서대로 flush 한다. 버퍼가 가득 차면 가장 오래된 event 부터 버려진다
  (`offline_buffer_max`, 기본 200 — status/telemetry 는 최신값만 의미 있어 버퍼링하지 않는다).
- QoS1(event/cmd)은 paho 내부 큐가 재전송을 보장하지만, 프로세스 자체가 재시작되면 큐도 사라진다
  (디스크 영속 큐는 이번 범위에 없음 — TODO).

## 4. Advantech IoT Suite 연동 TODO 체크리스트

실제 Advantech WISE-PaaS/IoT Suite 로 전환하기 전에 확인해야 할 항목. `adapters/advantech.py` 의
`IoTAdapter` 인터페이스(토픽 매핑 4개 + `transform_payload`)를 구현하는 `AdvantechAdapter` 클래스를
새로 만들고, `mqtt_bridge_node.py` 의 `LocalMosquittoAdapter()` 생성 부분만 교체하면 된다.

- [ ] 브로커 주소/포트, TLS 사용 여부(mqtts, 인증서 경로)
- [ ] 인증 방식: 사용자명/비밀번호 vs 클라이언트 인증서 vs 디바이스 토큰
- [ ] 디바이스 등록 절차: 사전 등록 필요 여부, `device_id`/`robot_id` 발급 규칙, 등록 API 유무
- [ ] 토픽 네이밍 규칙: Advantech 쪽에 고정 스키마가 있는지(`factory/{robot_id}/...` 를 그대로 쓸 수 있는지)
- [ ] 페이로드 스키마: 위 JSON 을 그대로 받는지, 필드명/단위 변환이 필요한지
- [ ] QoS/retain 정책 호환성(브로커가 QoS1/retain 을 지원하는지)
- [ ] Rate limit / 과금 정책(1Hz status/telemetry 가 허용 범위인지)
- [ ] 명령 채널 보안(누가 `cmd` 를 보낼 수 있는지 ACL)

## 5. 로컬 테스트

```bash
# 터미널 1: 로컬 브로커(이미 설치됨, systemd 서비스로 떠 있을 수 있음)
mosquitto -v            # 이미 서비스로 떠 있으면 생략

# 터미널 2: 구독해서 확인
mosquitto_sub -t 'factory/#' -v

# 터미널 3: full_demo 를 mqtt:=true 로 실행 (STEP7_VERIFY.md 참고)
ros2 launch fire_bringup full_demo.launch.py mqtt:=true

# 터미널 4: cmd 발행 테스트(HOLD 상태에서 resume)
mosquitto_pub -t 'factory/fire_bot_01/cmd' -m '{"cmd":"resume"}'
```
