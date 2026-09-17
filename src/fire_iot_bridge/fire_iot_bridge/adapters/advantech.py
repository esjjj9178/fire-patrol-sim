"""Advantech IoT Suite 연동 어댑터 인터페이스 (설계만, 미구현 — STEP7 TODO).

실제 Advantech WISE-PaaS/IoT Suite 브로커에 연결할 때, mqtt_bridge_node 가 만드는
factory/{robot_id}/... 페이로드(JSON, STEP6 event 스키마)를 Advantech 쪽 디바이스
모델/토픽 규칙으로 변환하는 계층을 여기 구현한다. 지금은 인터페이스 정의와
로컬 mosquitto용 기본 구현(identity 매핑)만 둔다.

TODO(Advantech 실제 연동 전 확인할 것) — docs/MQTT_DESIGN.md 의 체크리스트와 동일:
  - 브로커 주소/포트/TLS 여부
  - 인증 방식(사용자명/비번, 인증서, 디바이스 토큰 등)
  - 디바이스 등록 방식(사전 등록 필요 여부, device_id 발급 규칙)
  - 토픽 네이밍 규칙(Advantech 쪽 고정 스키마가 있는지)
  - 페이로드 스키마(고정 JSON 스키마 vs 커스텀 허용 여부)
  - QoS/retain 정책이 Advantech 쪽과 호환되는지
"""
from abc import ABC, abstractmethod


class IoTAdapter(ABC):
    """factory/{robot_id}/... 페이로드를 대상 플랫폼의 토픽/페이로드로 변환하는 인터페이스."""

    @abstractmethod
    def map_event_topic(self, robot_id: str) -> str:
        """이벤트 발행 토픽을 반환한다."""

    @abstractmethod
    def map_status_topic(self, robot_id: str) -> str:
        """상태(1Hz) 발행 토픽을 반환한다."""

    @abstractmethod
    def map_telemetry_topic(self, robot_id: str) -> str:
        """원격측정(1Hz) 발행 토픽을 반환한다."""

    @abstractmethod
    def map_command_topic(self, robot_id: str) -> str:
        """명령 구독 토픽을 반환한다."""

    @abstractmethod
    def transform_payload(self, kind: str, payload: dict) -> dict:
        """kind('event'|'status'|'telemetry')별로 payload(STEP6 JSON 스키마)를
        대상 플랫폼 스키마로 변환한다. 기본 구현은 항등(identity) 변환."""


class LocalMosquittoAdapter(IoTAdapter):
    """로컬 mosquitto 테스트용 기본 구현: factory/{robot_id}/... 그대로, 페이로드 변환 없음."""

    def map_event_topic(self, robot_id: str) -> str:
        return f'factory/{robot_id}/fire/event'

    def map_status_topic(self, robot_id: str) -> str:
        return f'factory/{robot_id}/fire/status'

    def map_telemetry_topic(self, robot_id: str) -> str:
        return f'factory/{robot_id}/fire/telemetry'

    def map_command_topic(self, robot_id: str) -> str:
        return f'factory/{robot_id}/cmd'

    def transform_payload(self, kind: str, payload: dict) -> dict:
        return payload
