"""
posture-cep이 확정한 붕괴 이벤트를 MySQL(서비스DB `posture_app`)의
`collapse_events` 테이블에 기록한다.

model.py(inference-service)의 torch 지연 임포트와 같은 방어적 패턴을
그대로 따른다 — mysql-connector-python이 설치되지 않았거나, DB 접속
정보가 없거나, 접속 자체가 실패해도 posture-cep의 핵심 기능(상태
머신 판정, /cep/active·/cep/events/recent 조회)은 절대 멈추면 안
된다. DB 기록은 어디까지나 부가 기능이다 — 계획서 정의상 이 DB에는
"세션·원본 시계열"이 아니라 "확정된 이벤트"만 들어가므로, 쓰기
실패가 이벤트 판정 자체를 막을 이유도 없다.

환경변수:
  CEP_DB_ENABLED   "false"로 두면 DB 기록 자체를 끈다(기본 true).
  DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD
                   api-server와 동일한 이름 사용 (.env 공유).
"""
import logging
import os
import threading
from typing import Optional

from app.state_machine import parse_instant

logger = logging.getLogger("posture-cep.db")

DB_ENABLED = os.getenv("CEP_DB_ENABLED", "true").lower() not in ("false", "0", "no")
DB_HOST = os.getenv("DB_HOST", "")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_NAME = os.getenv("DB_NAME", "posture_app")
DB_USER = os.getenv("DB_USER", "posture_app")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

_UPSERT_SQL = """
    INSERT INTO collapse_events
        (session_id, user_id, started_at, ended_at, duration_seconds,
         alert_count, last_alert_at, recovered, ongoing)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
        ended_at = VALUES(ended_at),
        duration_seconds = VALUES(duration_seconds),
        alert_count = VALUES(alert_count),
        last_alert_at = VALUES(last_alert_at),
        recovered = VALUES(recovered),
        ongoing = VALUES(ongoing)
"""

_SESSION_UPSERT_SQL = """
    INSERT INTO sessions
        (session_id, user_id, started_at, last_seen_at, sample_count, status)
    VALUES (%s, %s, %s, %s, 1, 'ACTIVE')
    ON DUPLICATE KEY UPDATE
        last_seen_at = VALUES(last_seen_at),
        sample_count = sample_count + 1
"""

_EXPIRE_SESSIONS_SQL = """
    UPDATE sessions
    SET status = 'ENDED'
    WHERE status = 'ACTIVE'
      AND last_seen_at < (UTC_TIMESTAMP(3) - INTERVAL %s SECOND)
"""

_lock = threading.Lock()
_pool = None
_pool_init_attempted = False


def _try_import_connector():
    try:
        import mysql.connector
        return mysql.connector
    except ImportError as exc:
        logger.warning(
            "mysql-connector-python이 설치되어 있지 않아 붕괴 이벤트를 DB에 "
            "기록할 수 없다 (판정 로직 자체는 계속 동작함): %s", exc,
        )
        return None


def _get_pool():
    """
    커넥션 풀을 지연 생성하고 캐싱한다. 생성 실패(호스트 미설정,
    네트워크 문제, 인증 실패 등)는 한 번만 로그를 남기고 이후 호출은
    조용히 스킵한다 — 매 이벤트마다 같은 에러를 반복해서 로그에 쏟아내지
    않기 위함(15초 헬스체크마다 새 클라이언트를 만들어 로그가 넘쳤던
    inference-service의 사례를 참고).
    """
    global _pool, _pool_init_attempted
    if _pool is not None:
        return _pool
    if _pool_init_attempted:
        return None

    with _lock:
        if _pool is not None or _pool_init_attempted:
            return _pool
        _pool_init_attempted = True

        if not DB_ENABLED:
            logger.info("CEP_DB_ENABLED=false — 붕괴 이벤트 DB 기록을 사용하지 않음")
            return None
        if not DB_HOST:
            logger.warning("DB_HOST가 설정되지 않아 붕괴 이벤트 DB 기록을 건너뜀")
            return None

        connector = _try_import_connector()
        if connector is None:
            return None

        try:
            _pool = connector.pooling.MySQLConnectionPool(
                pool_name="posture-cep-pool",
                pool_size=3,
                host=DB_HOST,
                port=DB_PORT,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
                connection_timeout=5,
            )
            logger.info(
                "MySQL 커넥션 풀 생성 완료 (host=%s:%s, db=%s)", DB_HOST, DB_PORT, DB_NAME,
            )
        except Exception as exc:  # noqa: BLE001 - 드라이버가 던지는 예외 종류가 다양함
            logger.warning(
                "MySQL 커넥션 풀 생성 실패 (host=%s:%s, db=%s) — 이후 이벤트는 DB "
                "기록 없이 계속 처리됨: %s", DB_HOST, DB_PORT, DB_NAME, exc,
            )
            _pool = None
        return _pool


def record_event(outcome: dict) -> bool:
    """
    engine.handle()이 반환한 outcome({"type": ..., "event": {...}})을
    받아 collapse_events 테이블에 upsert한다. 성공하면 True, DB가
    비활성/미접속/오류 상태라 기록하지 못했으면 False를 반환한다
    (호출부는 반환값으로 판단할 필요 없이 로그만 참고하면 됨 — 판정
    흐름 자체는 이 함수 결과와 무관하게 계속된다).
    """
    pool = _get_pool()
    if pool is None:
        return False

    event = outcome.get("event", {})
    params = (
        event.get("sessionId"),
        event.get("userId"),
        _to_mysql_datetime(event.get("startedAt")),
        _to_mysql_datetime(event.get("endedAt")),
        event.get("durationSeconds"),
        event.get("alertCount", 1),
        _to_mysql_datetime(event.get("lastAlertAt")),
        1 if event.get("recovered") else 0,
        1 if event.get("ongoing") else 0,
    )

    conn = None
    try:
        conn = pool.get_connection()
        cursor = conn.cursor()
        cursor.execute(_UPSERT_SQL, params)
        conn.commit()
        cursor.close()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "붕괴 이벤트 DB 기록 실패 (sessionId=%s, type=%s): %s",
            event.get("sessionId"), outcome.get("type"), exc,
        )
        return False
    finally:
        if conn is not None:
            conn.close()


def record_sample(event: dict) -> bool:
    """
    posture.inference에서 들어온 원본 이벤트(상태 전환 여부와 무관한
    "매 샘플")를 받아 sessions 테이블을 upsert한다.

    - 세션을 처음 보면 새 행을 만든다 (sample_count=1, status='ACTIVE').
    - 이미 있는 세션이면 last_seen_at을 갱신하고 sample_count를 1
      증가시킨다. started_at은 ON DUPLICATE KEY UPDATE 절에서 건드리지
      않으므로 최초 삽입 시각으로 고정된다 ("세션이 시작된 시각"의
      정의를 그대로 지킴).
    - record_event()와 마찬가지로 DB가 비활성/미접속/오류 상태여도
      예외를 던지지 않는다 — 상태 머신 판정 흐름은 이 함수의 성공
      여부와 무관하게 계속된다. sessions는 계획서 정의상 "세션 메타
      정보"이지 판정에 필요한 데이터가 아니므로, 여기서 매번(매 샘플)
      DB 왕복이 발생해도 판정 자체를 막을 이유가 없다.
    """
    pool = _get_pool()
    if pool is None:
        return False

    session_id = event.get("sessionId")
    if not session_id:
        return False

    try:
        captured_at = parse_instant(event.get("capturedAt"))
    except (ValueError, TypeError) as exc:
        logger.warning(
            "capturedAt을 파싱할 수 없어 세션 upsert를 건너뜀 (sessionId=%s): %s",
            session_id, exc,
        )
        return False

    captured_at_str = captured_at.strftime("%Y-%m-%d %H:%M:%S.%f")
    params = (session_id, event.get("userId"), captured_at_str, captured_at_str)

    conn = None
    try:
        conn = pool.get_connection()
        cursor = conn.cursor()
        cursor.execute(_SESSION_UPSERT_SQL, params)
        conn.commit()
        cursor.close()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("세션 upsert 실패 (sessionId=%s): %s", session_id, exc)
        return False
    finally:
        if conn is not None:
            conn.close()


def expire_stale_sessions(timeout_seconds: int) -> int:
    """
    `last_seen_at`이 `timeout_seconds`초 이상 갱신되지 않은 ACTIVE
    세션을 한 번에 ENDED로 마킹한다 (D-10: 세션 만료·정리).

    engine.expire_stale_sessions()(메모리 상태 정리)와는 독립적으로
    동작한다 — posture-cep이 재시작되면 메모리 상태는 사라지지만
    DB의 sessions 행은 남아있으므로, 이 함수는 순수하게 DB의
    last_seen_at 값만 기준으로 판단한다. 그래서 재시작 이후에도
    계속 정상적으로 오래된 세션을 정리할 수 있다.

    반환값은 이번 호출로 ENDED로 바뀐 행 수(정보/로그용). DB가
    비활성/미접속/오류 상태면 0을 반환하고 예외를 던지지 않는다
    (다른 record_*/함수들과 동일한 방어적 패턴).
    """
    pool = _get_pool()
    if pool is None:
        return 0

    conn = None
    try:
        conn = pool.get_connection()
        cursor = conn.cursor()
        cursor.execute(_EXPIRE_SESSIONS_SQL, (timeout_seconds,))
        conn.commit()
        affected = cursor.rowcount
        cursor.close()
        return affected
    except Exception as exc:  # noqa: BLE001
        logger.warning("세션 만료 처리(sessions UPDATE) 실패: %s", exc)
        return 0
    finally:
        if conn is not None:
            conn.close()


def _to_mysql_datetime(iso_value: Optional[str]) -> Optional[str]:
    """
    state_machine._serialize()가 만드는 `datetime.isoformat()` 문자열
    (예: "2026-09-25T16:21:43.032994+00:00")을 MySQL DATETIME 리터럴이
    받아들이는 "YYYY-MM-DD HH:MM:SS.ffffff" 형태로 바꾼다. mysql-connector
    가 문자열을 그대로 바인딩하므로, 타임존 오프셋(+00:00)이 붙은 채로
    넘기면 그대로 문자열 파싱 오류가 난다 — 이 프로젝트에서 시각은
    전부 UTC(Instant 기준)라 오프셋은 잘라내도 정보 손실이 없다.
    """
    if not iso_value:
        return None
    value = iso_value.replace("T", " ")
    for tz_marker in ("+00:00", "Z"):
        if value.endswith(tz_marker):
            value = value[: -len(tz_marker)]
            break
    return value
