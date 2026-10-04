"""
posture-cep 최소 버전 진입점.

계획서 "빅데이터 플랫폼 구성 > 처리·탐색 계층"의 Esper 기반
CEP(posture-cep) 역할 — posture.inference 스트림에서 지속조건(3초
후보)/회복조건/재알림 간격(60초 후보)을 판정해 붕괴 이벤트를
확정 — 을 실제 Esper 엔진 없이 상태 머신으로 최소 재현한 서비스다.
자세한 설계 근거는 app/state_machine.py 상단 주석 참고.

architecture 원칙에 따라 별도 마이크로서비스로 분리했다 —
inference-service와 마찬가지로 api-server/MySQL에는 직접 접근하지
않고, Kafka(posture.inference)로만 입력을 받고 지금은 조회 API로만
결과를 노출한다(DB 기록은 다음 단계).
"""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from kafka import KafkaAdminClient
from kafka.errors import KafkaError

from app.consumer import consumer, engine
from app.session_expiry import SessionExpiryWorker

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("posture-cep")

# inference-service에서 겪은 것과 같은 이유로 kafka-python 자체 로거는
# 조용히 시킨다 (README_빅데이터플랫폼_실행가이드.md 8절 "로그 가시성"
# 참고).
logging.getLogger("kafka").setLevel(os.getenv("KAFKA_LOG_LEVEL", "WARNING"))

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:19092")


session_expiry_worker = SessionExpiryWorker(engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    consumer.start()
    session_expiry_worker.start()
    yield
    session_expiry_worker.stop()
    consumer.stop()


app = FastAPI(title="posture-cep", version="0.1.0", lifespan=lifespan)


def check_kafka() -> dict:
    try:
        admin = KafkaAdminClient(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            request_timeout_ms=3000,
            client_id="posture-cep-healthcheck",
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
    kafka_result = check_kafka()
    overall_up = kafka_result["status"] == "UP"
    body = {
        "status": "UP" if overall_up else "DOWN",
        "components": {"kafka": kafka_result},
    }
    return JSONResponse(
        content=body,
        status_code=status.HTTP_200_OK if overall_up else status.HTTP_503_SERVICE_UNAVAILABLE,
    )


@app.get("/")
def root():
    return {"service": "posture-cep", "docs": "/docs", "health": "/health"}


@app.get("/cep/active")
def active_events():
    """현재 지속조건을 충족해 진행 중인(아직 회복되지 않은) 붕괴 이벤트 목록."""
    events = engine.active_events()
    return {"count": len(events), "events": events}


@app.get("/cep/events/recent")
def recent_events(limit: int = 20):
    """최근 종료(회복)된 붕괴 이벤트 목록."""
    limit = max(1, min(limit, 100))
    events = engine.recent_events(limit)
    return {"count": len(events), "events": events}


@app.post("/cep/sessions/expire")
def expire_sessions_now():
    """
    세션 만료 검사를 즉시 한 번 수행한다 (D-10). 원래는
    SessionExpiryWorker가 CEP_SESSION_EXPIRY_INTERVAL_SECONDS(기본
    60초)마다 자동으로 돌지만, VM에서 타임아웃(기본 5분)을 기다리지
    않고 바로 검증하고 싶을 때 이 엔드포인트로 즉시 트리거할 수 있다.
    """
    result = session_expiry_worker.run_once()
    return result
