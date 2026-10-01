"""
자세 분석 시스템 추론 서비스 (Python / LSTM) 진입점.

현재 단계 목표:
    posture.summary 토픽을 실제로 구독해 api-server가 발행한 이벤트를
    받아 처리하는 파이프라인 전체를 연결한다. 세션별 슬라이딩 윈도우가
    쌓이면 합성 데이터로 학습한 테스트 LSTM 모델(app/model.py,
    train_test_model.py)로 추론하고, 윈도우가 안 찼거나 모델을 쓸 수
    없으면 규칙 기반 골격(consumer.infer_rule_based)으로 자동
    폴백한다.

architecture 문서 상 추론 서비스는 API 서버와 분리된 별도의
마이크로서비스이며, MySQL에는 직접 접근하지 않는다
(모델 버전/결과 기록은 API 서버를 경유).
"""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
import redis
from kafka import KafkaAdminClient
from kafka.errors import KafkaError

from app import model as lstm_model
from app.consumer import consumer, get_recent_results

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("inference-service")

# kafka-python 라이브러리 자체의 로거(`kafka.conn`, `kafka.coordinator` 등)는
# INFO 레벨에서 커넥션/브로커 버전 프로빙마다 여러 줄씩 로그를 남긴다.
# /health가 Docker healthcheck(기본 15초 간격)로 계속 호출되면서 매번
# 새 KafkaAdminClient를 만들다 보니 이 로그가 끊임없이 쌓여서, 정작
# 중요한 "posture.summary 이벤트 처리 완료" 같은 우리 애플리케이션
# 로그가 `docker compose logs --tail=N`의 짧은 창 밖으로 금방 밀려나는
# 문제가 있었다. kafka-python 쪽 로거만 WARNING 이상으로 올려서
# 연결 실패 같은 진짜 문제는 여전히 보이돼 정상 커넥션 로그는 숨긴다.
logging.getLogger("kafka").setLevel(os.getenv("KAFKA_LOG_LEVEL", "WARNING"))

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:19092")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 모델 로딩은 app/model.py 안에서 최초 predict() 호출 시 1회만
    # 로드되는 지연(lazy) 방식이다 — 그대로 두면 세션의 슬라이딩
    # 윈도우가 다 찰 때까지(기본 10개 이벤트) "모델 로드 완료" 로그가
    # 전혀 찍히지 않아, 기동 직후에는 로드 성공/실패를 확인할 방법이
    # 없다. 그래서 기동 시점에 한 번 미리 호출해서(eager load) 로그가
    # 바로 찍히게 한다 — 모델이 없거나 torch 미설치여도 여기서
    # 예외 없이 None을 반환하고 경고 로그만 남기므로 기동 자체는
    # 안전하다.
    lstm_model.load_model()
    # 시작 시 Kafka 컨슈머 백그라운드 스레드 기동
    consumer.start()
    yield
    # 종료 시 정리
    consumer.stop()


app = FastAPI(title="posture-inference-service", version="0.2.0", lifespan=lifespan)


def check_redis() -> dict:
    try:
        client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, socket_connect_timeout=3)
        client.ping()
        return {"status": "UP", "host": REDIS_HOST, "port": REDIS_PORT}
    except Exception as exc:  # noqa: BLE001 - 헬스체크는 원인 종류와 무관하게 DOWN 처리
        return {"status": "DOWN", "error": str(exc)}


def check_kafka() -> dict:
    try:
        admin = KafkaAdminClient(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            request_timeout_ms=3000,
            client_id="inference-service-healthcheck",
        )
        topics = admin.list_topics()
        admin.close()
        return {"status": "UP", "bootstrap_servers": KAFKA_BOOTSTRAP_SERVERS, "topics": topics}
    except KafkaError as exc:
        return {"status": "DOWN", "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"status": "DOWN", "error": str(exc)}


@app.get("/health")
def health():
    redis_result = check_redis()
    kafka_result = check_kafka()
    overall_up = redis_result["status"] == "UP" and kafka_result["status"] == "UP"

    # 모델은 redis/kafka와 달리 "없으면 규칙 기반으로 폴백"이 정상
    # 동작이므로 overall_up 판정에는 넣지 않는다 — 여기 loaded: false가
    # 나와도 /health 전체는 여전히 200일 수 있다. 로그를 뒤지지 않고도
    # 모델 로드 상태를 바로 확인하려고 넣었다.
    model_status = lstm_model.status()

    body = {
        "status": "UP" if overall_up else "DOWN",
        "components": {
            "redis": redis_result,
            "kafka": kafka_result,
            "lstmModel": model_status,
        },
    }
    return JSONResponse(
        content=body,
        status_code=status.HTTP_200_OK if overall_up else status.HTTP_503_SERVICE_UNAVAILABLE,
    )


@app.get("/")
def root():
    return {"service": "posture-inference-service", "docs": "/docs", "health": "/health"}


@app.get("/inference/recent")
def inference_recent(limit: int = 20):
    """
    최근 처리된 posture.summary 이벤트의 추론 결과 목록 (메모리 보관,
    재시작 시 초기화됨). 파이프라인이 실제로 연결되어 있는지 확인하는
    용도의 임시 엔드포인트 — 영속 조회 API는 다음 단계(DB 연동)에서
    api-server 쪽에 추가한다.
    """
    limit = max(1, min(limit, 50))
    return {"count": len(get_recent_results()), "results": get_recent_results(limit)}


@app.get("/inference/latest")
def inference_latest():
    results = get_recent_results(limit=1)
    if not results:
        raise HTTPException(status_code=404, detail="아직 처리된 posture.summary 이벤트가 없습니다")
    return results[0]
