"""
posture-cep 세션 만료·정리 워커 (D-10).

일정 시간(CEP_SESSION_TIMEOUT_SECONDS, 기본 300초=5분) 동안 새
posture.inference 이벤트가 오지 않은 세션을 "끊긴 세션"으로 보고
정리한다. 클라이언트가 브라우저를 닫거나 네트워크가 끊기는 등,
명시적인 "세션 종료" 신호 없이 스트림이 그냥 멈추는 경우를 다룬다
(명시적 종료 신호가 생기면 그쪽이 우선 처리되고, 이 워커는 그걸
놓친 세션을 뒤늦게 정리하는 안전망 역할).

정리 대상 두 가지:
  1. 메모리 상태(PostureCepEngine._sessions) — 세션이 재시작 전까지
     무한정 쌓이는 문제를 막는다. 정리 시점에 아직 회복되지 않은
     붕괴 이벤트가 진행 중이었다면, 마지막으로 이벤트를 받은 시각을
     종료 시각으로 하고 recovered=False로 확정해서 collapse_events에
     기록한다(engine.expire_stale_sessions() 참고) — 그러지 않으면
     그 이벤트가 영원히 "ongoing"으로 /cep/active에 남는다.
  2. DB(sessions.status) — posture-cep이 재시작되면 메모리 상태는
     사라지지만 DB의 sessions 행은 남아있으므로, last_seen_at 기준
     으로 별도로 ACTIVE → ENDED 마킹한다(db.expire_stale_sessions()).
     이건 엔진 메모리와 무관하게 동작해서 재시작 후에도 계속 오래된
     세션을 정리할 수 있다.

api-server/inference-service와 동일한 원칙으로, 이 워커가 실패해도
posture-cep의 핵심 기능(판정, 조회 API)은 절대 멈추지 않는다 — 만료
처리 실패는 로그만 남기고 다음 주기에 다시 시도한다.

환경변수:
  CEP_SESSION_TIMEOUT_SECONDS          세션을 "끊겼다"고 볼 침묵 시간(초). 기본 300(5분).
  CEP_SESSION_EXPIRY_INTERVAL_SECONDS  만료 검사 주기(초). 기본 60.
"""
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Optional

from app import db
from app.state_machine import PostureCepEngine

logger = logging.getLogger("posture-cep.session_expiry")

SESSION_TIMEOUT_SECONDS = float(os.getenv("CEP_SESSION_TIMEOUT_SECONDS", "300"))
EXPIRY_CHECK_INTERVAL_SECONDS = float(os.getenv("CEP_SESSION_EXPIRY_INTERVAL_SECONDS", "60"))


class SessionExpiryWorker:
    """일정 주기로 끊긴 세션을 정리하는 백그라운드 워커. consumer의
    PostureInferenceConsumer와 동일한 스레드 관리 패턴을 따른다."""

    def __init__(self, engine: PostureCepEngine) -> None:
        self._engine = engine
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="posture-cep-session-expiry", daemon=True
        )
        self._thread.start()
        logger.info(
            "세션 만료 워커 시작 (timeout=%.0fs, interval=%.0fs)",
            SESSION_TIMEOUT_SECONDS, EXPIRY_CHECK_INTERVAL_SECONDS,
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
            self._thread = None
        logger.info("세션 만료 워커 종료")

    def _run(self) -> None:
        # wait()가 True를 반환(=stop 신호)할 때까지 interval마다 반복.
        # 서비스가 막 뜬 직후에는 만료 대상이 없을 가능성이 높으므로
        # 시작하자마자 한 번 돌리지 않고 첫 주기만큼 기다렸다가 시작한다.
        while not self._stop_event.wait(EXPIRY_CHECK_INTERVAL_SECONDS):
            self.run_once()

    def run_once(self) -> dict:
        """
        만료 검사를 한 번 수행한다. 주기 실행뿐 아니라 테스트/수동
        트리거(예: 관리용 엔드포인트)에서도 직접 호출할 수 있도록
        분리했다. 결과를 dict로 반환한다(로그·응답 양쪽에 재사용).
        """
        result = {"finalized_events": 0, "ended_sessions_db": 0, "error": None}
        try:
            now = datetime.now(timezone.utc)
            outcomes = self._engine.expire_stale_sessions(now, SESSION_TIMEOUT_SECONDS)
            for outcome in outcomes:
                logger.info(
                    "세션 타임아웃으로 붕괴 이벤트 강제 종료: sessionId=%s",
                    outcome["event"]["sessionId"],
                )
                db.record_event(outcome)
            result["finalized_events"] = len(outcomes)

            expired_rows = db.expire_stale_sessions(int(SESSION_TIMEOUT_SECONDS))
            result["ended_sessions_db"] = expired_rows
            if expired_rows:
                logger.info("sessions 테이블 %d건을 ENDED로 마킹함", expired_rows)
        except Exception as exc:  # noqa: BLE001 - 워커 스레드가 죽지 않도록 방어
            logger.exception("세션 만료 처리 중 예외 발생 (다음 주기에 재시도)")
            result["error"] = str(exc)
        return result
