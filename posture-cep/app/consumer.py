"""
posture.inference 토픽을 구독하는 Kafka 컨슈머.

inference-service가 각 posture.summary 이벤트를 처리한 결과
(규칙 기반이든 테스트 LSTM 모델이든)를 posture.inference 토픽에
발행하면, 여기서 그 결과를 순서대로 읽어 app/state_machine.py의
PostureCepEngine에 넘긴다. 컨슈머 자체는 inference-service의
PostureSummaryConsumer와 같은 패턴(백그라운드 스레드 + poll 루프)이다.
"""
import json
import logging
import os
import threading
from typing import Optional

from kafka import KafkaConsumer
from kafka.errors import KafkaError

from app import db
from app.state_machine import PostureCepEngine

logger = logging.getLogger("posture-cep.consumer")

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:19092")
POSTURE_INFERENCE_TOPIC = os.getenv("KAFKA_TOPIC_POSTURE_INFERENCE", "posture.inference")
CONSUMER_GROUP_ID = os.getenv("KAFKA_CONSUMER_GROUP_ID", "posture-cep")

engine = PostureCepEngine()


class PostureInferenceConsumer:
    """posture.inference 토픽을 구독하는 백그라운드 컨슈머."""

    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._consumer: Optional[KafkaConsumer] = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="posture-inference-consumer", daemon=True
        )
        self._thread.start()
        logger.info(
            "Kafka consumer 스레드 시작 (topic=%s, group=%s, bootstrap=%s)",
            POSTURE_INFERENCE_TOPIC, CONSUMER_GROUP_ID, KAFKA_BOOTSTRAP_SERVERS,
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
            self._thread = None
        logger.info("Kafka consumer 스레드 종료")

    def _run(self) -> None:
        try:
            self._consumer = KafkaConsumer(
                POSTURE_INFERENCE_TOPIC,
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                group_id=CONSUMER_GROUP_ID,
                auto_offset_reset="earliest",
                enable_auto_commit=True,
                value_deserializer=lambda v: v.decode("utf-8"),
                consumer_timeout_ms=1000,
            )
        except KafkaError as exc:
            logger.error("Kafka consumer 생성 실패: %s", exc)
            return

        logger.info("Kafka consumer 준비 완료, posture.inference 메시지 대기 중...")
        try:
            while not self._stop_event.is_set():
                for message in self._consumer:
                    if self._stop_event.is_set():
                        break
                    self._handle_message(message.value)
        except Exception:  # noqa: BLE001 - 컨슈머 스레드가 죽지 않도록 방어
            logger.exception("Kafka consumer 루프 중 예외 발생, 스레드 종료")
        finally:
            if self._consumer is not None:
                self._consumer.close()

    def _handle_message(self, raw_value: str) -> None:
        try:
            event = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            logger.warning("JSON 파싱 실패, 메시지 건너뜀 (raw=%r): %s", raw_value, exc)
            return

        # sessions 갱신(last_seen_at/sample_count)은 상태 전환 여부와
        # 무관하게 매 샘플마다 수행한다. DB 기록 실패는 로그만 남기고
        # 판정 흐름에 영향을 주지 않는다(db.record_sample() 자체가
        # 방어적으로 구현되어 있음).
        db.record_sample(event)

        outcome = engine.handle(event)
        if outcome is not None:
            logger.info(
                "posture-cep 상태 전환: %s (sessionId=%s)",
                outcome["type"], outcome["event"]["sessionId"],
            )
            # DB 기록 실패는 로그만 남기고 판정 흐름에 영향을 주지 않는다
            # (db.record_event() 자체가 방어적으로 구현되어 있음).
            db.record_event(outcome)


consumer = PostureInferenceConsumer()
