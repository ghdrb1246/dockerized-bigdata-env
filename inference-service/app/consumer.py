"""
posture.summary 토픽을 구독하는 Kafka 컨슈머.

지금 단계 목표:
    api-server가 발행한 PostureSummaryEvent를 실제로 수신해 처리하는
    파이프라인 전체를 연결하는 것 + "합성(synthetic) 예시 데이터로
    학습한 테스트 LSTM 모델"을 실제로 얹어서, 모델 로딩·세션별
    슬라이딩 윈도우 버퍼링·추론까지 포함한 전체 경로가 하드웨어/
    빅데이터 플랫폼에서 문제없이 도는지 검증한다(app/model.py,
    train_test_model.py 참고). 이 모델은 실제 자세 데이터로 학습된
    게 아니므로 판단 정확도에는 의미를 두지 않는다 — 파이프라인
    검증용이다.

    세션별로 최근 WINDOW_SIZE개 featureVector가 쌓이기 전까지는
    (또는 torch/모델 파일이 없으면) infer_rule_based()의 규칙 기반
    판단으로 자동 폴백한다. 실제 학습된 모델이 준비되면
    app/models/test_lstm.pt·test_lstm.meta.json만 교체하면 된다.
"""
import json
import logging
import os
import threading
from collections import defaultdict, deque
from typing import Deque, Dict, List, Optional

from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError

from app import model as lstm_model

logger = logging.getLogger("inference-service.consumer")

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:19092")
POSTURE_SUMMARY_TOPIC = os.getenv("KAFKA_TOPIC_POSTURE_SUMMARY", "posture.summary")
CONSUMER_GROUP_ID = os.getenv("KAFKA_CONSUMER_GROUP_ID", "inference-service")

# posture-cep(최소 버전)이 구독하는 출력 토픽. run_inference()의 결과를
# (규칙 기반이든 모델 추론이든) 그대로 발행해서, posture-cep이 지속조건/
# 재알림 판정을 위한 시계열 입력으로 쓴다. 발행 실패는 파이프라인 전체를
# 막지 않는다 — posture-cep은 계획서상 부가 판정 계층이라, 이게 죽어도
# inference-service 자체의 조회 API(/inference/latest 등)는 계속 동작해야
# 한다(그래서 아래 producer는 방어적으로 감싸고 실패해도 컨슈머 루프를
# 죽이지 않는다).
POSTURE_INFERENCE_TOPIC = os.getenv("KAFKA_TOPIC_POSTURE_INFERENCE", "posture.inference")
_PRODUCE_ENABLED = os.getenv("INFERENCE_PUBLISH_ENABLED", "true").lower() != "false"

# train_test_model.py가 학습한 테스트 모델의 window_size(10)와 맞춰야
# 한다 — 다르면 모델 메타데이터 기준으로 윈도우가 다 차도 예상보다
# 늦게/빨리 모델 추론으로 전환된다.
WINDOW_SIZE = int(os.getenv("INFERENCE_WINDOW_SIZE", "10"))

# 최근 처리 결과를 메모리에 보관한다 (확인용 골격 — 실제 저장은 다음 단계에서
# api-server/DB 경유로 처리하거나 별도 저장소를 붙인다).
_RECENT_RESULTS_MAXLEN = 50
recent_results: deque = deque(maxlen=_RECENT_RESULTS_MAXLEN)
_lock = threading.Lock()

# 세션ID별 최근 featureVector 슬라이딩 윈도우 버퍼. 컨슈머 스레드
# 하나에서만 읽고 쓰므로(카프카 메시지는 순차 처리) 별도 락이 필요
# 없다. 세션이 아주 많아지면 메모리에 무한히 쌓일 수 있는데, 지금은
# 테스트 단계라 별도 세션 만료 처리는 하지 않는다(다음 단계 항목).
_session_windows: Dict[str, Deque[List[float]]] = defaultdict(
    lambda: deque(maxlen=WINDOW_SIZE)
)


def infer_rule_based(event: dict) -> dict:
    """
    deviationScore 기준의 규칙 기반 판단. run_inference()가 아래 두
    경우에 이 함수로 폴백한다: (1) 세션의 슬라이딩 윈도우가 아직
    WINDOW_SIZE만큼 안 찼을 때, (2) torch/모델 파일이 없어 LSTM을 쓸
    수 없을 때. api-server가 이미 계산해 보낸 ruleStatus를 그대로
    신뢰하지 않고, inference-service 쪽에서도 자체적으로 판단을
    내려 본다는 점은 LSTM 도입 전과 동일하다.

    ------------------------------------------------------------------
    LSTM 적용 현황:

    1. 세션별 슬라이딩 윈도우 버퍼 — 구현됨. run_inference()가
       _session_windows에 세션ID별로 최근 WINDOW_SIZE개
       featureVector를 쌓고, 다 차면 모델 추론으로 넘어간다(아직은
       메모리 dict라 서비스 재시작 시 사라짐 — 세션이 많아지면 Redis
       등으로 옮기는 걸 고려. 지금은 테스트 단계라 보류).

    2. 모델 로딩 — 구현됨. app/model.py의 load_model()이 서비스
       기동 후 첫 predict() 호출 시 한 번만 로드해 전역에 캐싱한다
       (요청마다 다시 로드하지 않음).

    3. 전처리 일관성 — 아직 방어적 처리 수준. app/model.py의
       predict()가 featureVector 길이를 모델 input_size에 맞춰
       패딩/절단만 한다. 정규화/스케일링은 지금 합성 데이터 학습에
       쓴 것과 동일한 난수 분포를 가정하므로, 실제 자세 데이터로
       재학습할 때는 실제 전처리 파이프라인과 반드시 다시 맞춰야
       한다.

    4. 출력 형식 — 구현됨. inferredStatus 3단계 분류에 더해 클래스별
       확률(probabilities)도 함께 반환·로그된다(app/model.py의
       predict() 참고).

    5. 실패 시 폴백 — 구현됨. model.predict()가 None을 반환하는 모든
       경우(torch 미설치, 가중치 파일 없음, 로드/추론 중 예외)에
       run_inference()가 이 함수로 자동 폴백한다.
    ------------------------------------------------------------------
    """
    deviation_score = event.get("deviationScore")
    received_rule_status = event.get("ruleStatus", "UNKNOWN")

    if isinstance(deviation_score, (int, float)):
        if deviation_score >= 0.7:
            inferred_status = "BAD"
        elif deviation_score >= 0.4:
            inferred_status = "WARNING"
        else:
            inferred_status = "NORMAL"
    else:
        inferred_status = received_rule_status

    return {
        "sessionId": event.get("sessionId"),
        "userId": event.get("userId"),
        "receivedRuleStatus": received_rule_status,
        "inferredStatus": inferred_status,
        "deviationScore": deviation_score,
        "capturedAt": event.get("capturedAt"),
        "serverReceivedAt": event.get("serverReceivedAt"),
        "model": "rule-based-skeleton-v0",
    }


def _partition_key(result: dict) -> Optional[str]:
    """posture.inference 메시지 키 (D-15).

    v4 메시지 규격 1장에 따라 userId를 키로 쓴다. userId가 비어 있는
    예외적인 메시지는 sessionId로 대신한다 — 최소한 같은 세션의 순서는
    지켜야 상태머신 판정이 깨지지 않기 때문이다.
    """
    return result.get("userId") or result.get("sessionId")


def run_inference(event: dict) -> dict:
    """
    이벤트 하나를 처리하는 진입점. 세션별 슬라이딩 윈도우에
    featureVector를 쌓고, 윈도우가 다 찼고 테스트 LSTM 모델을 쓸 수
    있으면 모델 추론 결과를, 그렇지 않으면(윈도우 미완성 또는 모델
    사용 불가) infer_rule_based()의 규칙 기반 결과를 반환한다.
    """
    session_id = event.get("sessionId") or "unknown"
    feature_vector = event.get("featureVector") or []

    try:
        window_entry = [float(v) for v in feature_vector]
    except (TypeError, ValueError):
        logger.warning(
            "featureVector를 숫자 리스트로 변환할 수 없어 이번 이벤트는 "
            "윈도우에 넣지 않고 규칙 기반으로만 처리한다 (sessionId=%s)",
            session_id,
        )
        window_entry = None

    if window_entry is not None:
        window = _session_windows[session_id]
        window.append(window_entry)

        if len(window) == WINDOW_SIZE:
            model_result = lstm_model.predict(list(window))
            if model_result is not None:
                return {
                    "sessionId": session_id,
                    "userId": event.get("userId"),
                    "receivedRuleStatus": event.get("ruleStatus", "UNKNOWN"),
                    "inferredStatus": model_result["inferredStatus"],
                    "probabilities": model_result["probabilities"],
                    "deviationScore": event.get("deviationScore"),
                    "capturedAt": event.get("capturedAt"),
                    "serverReceivedAt": event.get("serverReceivedAt"),
                    "model": model_result["model"],
                    "windowSize": WINDOW_SIZE,
                }
            # model_result가 None이면(torch 미설치, 가중치 파일 없음 등)
            # 아래 규칙 기반으로 계속 폴백한다.

    result = infer_rule_based(event)
    result["windowBuffered"] = len(_session_windows.get(session_id, []))
    result["windowSize"] = WINDOW_SIZE
    return result


class PostureSummaryConsumer:
    """
    posture.summary 토픽을 구독하는 백그라운드 컨슈머.

    FastAPI lifespan에서 start()/stop()으로 제어한다. uvicorn의 메인
    이벤트 루프를 막지 않도록 별도 스레드에서 poll 루프를 돈다.
    """

    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._consumer: Optional[KafkaConsumer] = None
        self._producer: Optional[KafkaProducer] = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="posture-summary-consumer", daemon=True
        )
        self._thread.start()
        logger.info(
            "Kafka consumer 스레드 시작 (topic=%s, group=%s, bootstrap=%s)",
            POSTURE_SUMMARY_TOPIC, CONSUMER_GROUP_ID, KAFKA_BOOTSTRAP_SERVERS,
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
            self._thread = None
        if self._producer is not None:
            self._producer.close(timeout=5)
            self._producer = None
        logger.info("Kafka consumer 스레드 종료")

    def _init_producer(self) -> None:
        if not _PRODUCE_ENABLED:
            logger.info("INFERENCE_PUBLISH_ENABLED=false — posture.inference 발행 비활성화")
            return
        try:
            self._producer = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                # (D-15) 메시지 키 = userId (v4 메시지 규격 1장). posture.inference를
                # 여러 파티션으로 늘리면 키가 없는 메시지는 파티션에 흩어져
                # 같은 세션의 추론 결과가 서로 다른 컨슈머 스레드에서 순서
                # 없이 처리된다 — 상태머신(지속·회복 판정)이 깨진다. 키를
                # 주면 같은 사용자의 메시지는 항상 같은 파티션으로 가서
                # 순서가 보장된다.
                key_serializer=lambda k: k.encode("utf-8") if k is not None else None,
                # posture-cep은 부가 판정 계층이라 발행 실패로 컨슈머 루프
                # 전체를 막을 필요는 없다 — 재시도는 최소로, 타임아웃은
                # 짧게 잡아 컨슈머 처리 지연을 최소화한다.
                retries=1,
                request_timeout_ms=3000,
            )
            logger.info(
                "posture.inference producer 준비 완료 (topic=%s)", POSTURE_INFERENCE_TOPIC
            )
        except KafkaError as exc:
            logger.warning(
                "posture.inference producer 생성 실패, 발행 없이 계속 진행: %s", exc
            )
            self._producer = None

    def _run(self) -> None:
        try:
            self._consumer = KafkaConsumer(
                POSTURE_SUMMARY_TOPIC,
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                group_id=CONSUMER_GROUP_ID,
                auto_offset_reset="earliest",
                enable_auto_commit=True,
                value_deserializer=lambda v: v.decode("utf-8"),
                # consumer_timeout_ms: 메시지가 없을 때 for-loop을 주기적으로
                # 빠져나오게 해서 stop_event를 확인할 수 있게 한다 (KafkaConsumer
                # 자체에는 stop() 같은 게 없어서 poll 루프를 직접 제어해야 함).
                consumer_timeout_ms=1000,
            )
        except KafkaError as exc:
            logger.error("Kafka consumer 생성 실패: %s", exc)
            return

        self._init_producer()

        logger.info("Kafka consumer 준비 완료, posture.summary 메시지 대기 중...")
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

    def _publish_result(self, result: dict) -> None:
        if self._producer is None:
            return
        try:
            self._producer.send(
                POSTURE_INFERENCE_TOPIC,
                key=_partition_key(result),
                value=result,
            )
        except KafkaError as exc:  # noqa: BLE001 - 발행 실패는 로그만 남기고 계속
            logger.warning("posture.inference 발행 실패 (sessionId=%s): %s", result.get("sessionId"), exc)

    def _handle_message(self, raw_value: str) -> None:
        try:
            event = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            logger.warning("JSON 파싱 실패, 메시지 건너뜀 (raw=%r): %s", raw_value, exc)
            return

        result = run_inference(event)
        logger.info(
            "posture.summary 이벤트 처리 완료 (sessionId=%s, receivedRuleStatus=%s, "
            "inferredStatus=%s, model=%s, deviationScore=%s)",
            result["sessionId"], result["receivedRuleStatus"],
            result["inferredStatus"], result["model"], result["deviationScore"],
        )
        with _lock:
            recent_results.append(result)
        self._publish_result(result)


def get_recent_results(limit: Optional[int] = None) -> list:
    with _lock:
        items = list(recent_results)
    if limit is not None:
        items = items[-limit:]
    return items


consumer = PostureSummaryConsumer()
