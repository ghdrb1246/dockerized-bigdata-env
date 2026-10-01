"""
posture-cep 최소 버전의 핵심 로직 (Kafka/FastAPI와 분리된 순수 로직).

계획서 "빅데이터 플랫폼 구성 > 처리·탐색 계층"의 Esper 기반
CEP(`posture-cep`)가 하기로 한 일 — 지속조건(3초 후보)·회복조건·
재알림 간격(60초 후보)을 판정해 에피소드를 확정 — 을 실제 Esper
엔진(EPL 쿼리) 없이, 세션별 상태 머신으로 최소 재현한다.

이것이 최종 구현이 아닌 이유: Esper는 EPL(Esper Processing
Language)로 "지난 3초 윈도우 안에서 WARNING/BAD가 연속으로
나타났는가" 같은 규칙을 선언적으로 표현하고, 늦게 도착한 이벤트나
윈도우 경계 처리 등을 엔진이 알아서 처리해준다. 여기서는 그 동작을
if/else로 직접 재현했으므로, 순서가 어긋나거나 이벤트가 누락되는
경우의 처리가 Esper보다 단순하다 — 지금 목표는 "지속조건·재알림
로직이 파이프라인 안에서 실제로 동작하는가"를 빠르게 검증하는
것이고, 계획서의 최종 구현 단계에서 Esper로 교체하는 것을 전제로
한다.

시간 기준: 이벤트 도착 순서(Kafka 오프셋)가 아니라 이벤트에 담긴
`capturedAt`(클라이언트가 실제로 자세를 측정한 시각)을 기준으로
지속시간을 계산한다 — 두 이벤트 사이의 실제 시간 간격이 표본률
(sampleRateHz)에 따라 달라지기 때문에, 이벤트 개수가 아니라 실제
경과 시간으로 판정해야 계획서의 "3초 지속" 정의와 맞는다.
"""
import logging
import os
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger("posture-cep.state_machine")

# 후보값은 계획서 원문 그대로("최초 구현에서는 3초 지속을 후보로",
# "초기 재알림 간격을 60초 후보로") — 사용자 실험 후 확정 예정이라
# 환경변수로 바꿀 수 있게 열어둔다.
PERSIST_SECONDS = float(os.getenv("CEP_PERSIST_SECONDS", "3"))
RECOVERY_SECONDS = float(os.getenv("CEP_RECOVERY_SECONDS", "3"))
REALERT_SECONDS = float(os.getenv("CEP_REALERT_SECONDS", "60"))

NORMAL_STATUS = "NORMAL"

_FRACTION_RE = re.compile(r"\.(\d+)")


def parse_instant(value: Optional[str]) -> datetime:
    """
    Java `Instant`가 직렬화한 ISO-8601 문자열(나노초 단위까지 가능,
    예: "2026-09-25T14:54:17.909678710Z")을 파싱한다.

    `datetime.fromisoformat()`은 "Z" 접미사는 처리하지만(3.11+),
    마이크로초(6자리)를 넘는 소수점 자릿수는 못 받는다 — Java Instant는
    9자리(나노초)까지 나올 수 있어 6자리로 잘라낸 뒤 파싱한다.
    """
    if not value:
        raise ValueError("timestamp is empty")
    s = value.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"

    def _truncate(match: "re.Match[str]") -> str:
        frac = match.group(1)[:6].ljust(6, "0")
        return f".{frac}"

    s = _FRACTION_RE.sub(_truncate, s, count=1)
    return datetime.fromisoformat(s)


@dataclass
class CollapseEvent:
    session_id: str
    user_id: Optional[str]
    started_at: datetime
    ended_at: Optional[datetime] = None
    alert_count: int = 1
    last_alert_at: Optional[datetime] = None
    recovered: bool = False


@dataclass
class _SessionState:
    candidate_since: Optional[datetime] = None
    recovery_since: Optional[datetime] = None
    active_event: Optional[CollapseEvent] = None
    # 이 세션에서 마지막으로 이벤트를 받은 시각(capturedAt 기준). 상태
    # 전환(candidate_since 등)과는 별개로, "세션이 아직 살아있는가"를
    # 판단하는 용도로만 쓴다 — 세션 만료 정리(SessionExpiryWorker)가
    # 이 값을 기준으로 오래된 세션을 골라낸다.
    last_seen: Optional[datetime] = None


class PostureCepEngine:
    """세션별 상태 머신을 관리하는 엔진. 스레드 세이프."""

    def __init__(self) -> None:
        self._sessions: Dict[str, _SessionState] = {}
        self._completed_events: List[CollapseEvent] = []
        self._lock = threading.Lock()

    def handle(self, event: dict) -> Optional[dict]:
        """
        posture.inference 이벤트 하나를 처리한다. 상태 전환(에피소드
        시작/재알림/종료)이 발생했으면 그 설명을 dict로, 아니면 None을
        반환한다.
        """
        session_id = event.get("sessionId") or "unknown"
        inferred_status = event.get("inferredStatus") or "UNKNOWN"

        try:
            now = parse_instant(event.get("capturedAt"))
        except (ValueError, TypeError) as exc:
            logger.warning(
                "capturedAt을 파싱할 수 없어 이 이벤트는 건너뜀 (sessionId=%s): %s",
                session_id, exc,
            )
            return None

        is_candidate = inferred_status not in (NORMAL_STATUS, "UNKNOWN")

        with self._lock:
            state = self._sessions.setdefault(session_id, _SessionState())
            state.last_seen = now

            if is_candidate:
                return self._handle_candidate(session_id, event, state, now)
            return self._handle_normal(session_id, state, now)

    def _handle_candidate(
        self, session_id: str, event: dict, state: "_SessionState", now: datetime
    ) -> Optional[dict]:
        # 정상으로 돌아왔다가 다시 붕괴 후보가 됐으면 회복 타이머는 취소
        state.recovery_since = None

        if state.active_event is not None:
            # 이미 확정된 이벤트가 진행 중 — 재알림 간격만 확인
            evt = state.active_event
            since_last_alert = (now - evt.last_alert_at).total_seconds() if evt.last_alert_at else None
            if since_last_alert is None or since_last_alert >= REALERT_SECONDS:
                evt.alert_count += 1
                evt.last_alert_at = now
                logger.info(
                    "재알림 (sessionId=%s, alertCount=%d, 지속=%.1fs)",
                    session_id, evt.alert_count, (now - evt.started_at).total_seconds(),
                )
                return {"type": "RE_ALERT", "event": self._serialize(evt, ongoing=True)}
            return None

        if state.candidate_since is None:
            state.candidate_since = now
            return None

        elapsed = (now - state.candidate_since).total_seconds()
        if elapsed < PERSIST_SECONDS:
            return None

        # 지속조건 충족 — 붕괴 이벤트 확정
        evt = CollapseEvent(
            session_id=session_id,
            user_id=event.get("userId"),
            started_at=state.candidate_since,
            last_alert_at=now,
        )
        state.active_event = evt
        logger.info(
            "붕괴 이벤트 확정 (sessionId=%s, startedAt=%s, 지속조건=%.1fs 충족)",
            session_id, evt.started_at.isoformat(), elapsed,
        )
        return {"type": "EVENT_STARTED", "event": self._serialize(evt, ongoing=True)}

    def _handle_normal(
        self, session_id: str, state: "_SessionState", now: datetime
    ) -> Optional[dict]:
        state.candidate_since = None

        if state.active_event is None:
            return None

        if state.recovery_since is None:
            state.recovery_since = now
            return None

        elapsed = (now - state.recovery_since).total_seconds()
        if elapsed < RECOVERY_SECONDS:
            return None

        evt = state.active_event
        evt.ended_at = now
        evt.recovered = True
        state.active_event = None
        state.recovery_since = None
        self._completed_events.append(evt)
        logger.info(
            "붕괴 이벤트 종료 (sessionId=%s, 지속시간=%.1fs, alertCount=%d)",
            session_id, (evt.ended_at - evt.started_at).total_seconds(), evt.alert_count,
        )
        return {"type": "EVENT_ENDED", "event": self._serialize(evt, ongoing=False)}

    def expire_stale_sessions(self, now: datetime, timeout_seconds: float) -> List[dict]:
        """
        `timeout_seconds` 이상 새 이벤트가 오지 않은 세션을 만료 처리한다
        (D-10: 세션 만료·정리 로직).

        - 진행 중이던 붕괴 이벤트가 있었다면, 마지막으로 이벤트를 받은
          시각(last_seen)을 종료 시각으로 확정하고 recovered=False로
          기록한다 — 회복을 확인하지 못한 채 세션이 끊긴 것이므로
          "정상 복귀"로 볼 수 없다. 이 결과는 기존 EVENT_ENDED와 같은
          형태의 outcome으로 반환되므로, 호출부(SessionExpiryWorker)가
          그대로 `db.record_event()`에 넘겨 collapse_events에 기록할
          수 있다. 진행 중이던 이벤트가 없었으면 outcome 없이 상태만
          제거된다.
        - 만료된 세션은 내부 dict에서 완전히 제거된다 — 이게 없으면
          한 번이라도 이벤트를 보낸 세션이 재시작 전까지 메모리에
          영원히 남는다(원래 D-10이 지적한 문제).

        `now`는 호출 시점의 현재 시각(보통 datetime.now(timezone.utc))
        이며, 이벤트에 담긴 capturedAt과는 다른 시계열이다 — 만료
        판단은 "지금 기준으로 얼마나 오래 조용했는가"를 보는 것이므로
        실제 벽시계 시각을 써야 한다.
        """
        outcomes: List[dict] = []
        with self._lock:
            stale_ids = [
                sid for sid, state in self._sessions.items()
                if state.last_seen is not None
                and (now - state.last_seen).total_seconds() >= timeout_seconds
            ]
            for sid in stale_ids:
                state = self._sessions.pop(sid)
                if state.active_event is not None:
                    evt = state.active_event
                    evt.ended_at = state.last_seen
                    evt.recovered = False
                    self._completed_events.append(evt)
                    logger.info(
                        "세션 타임아웃으로 진행 중이던 붕괴 이벤트 강제 종료 "
                        "(sessionId=%s, 마지막 수신=%s)",
                        sid, state.last_seen.isoformat(),
                    )
                    outcomes.append({"type": "EVENT_ENDED", "event": self._serialize(evt, ongoing=False)})
                else:
                    logger.info(
                        "세션 만료로 상태 정리 (sessionId=%s, 마지막 수신=%s)",
                        sid, state.last_seen.isoformat(),
                    )
        return outcomes

    def active_events(self) -> List[dict]:
        with self._lock:
            return [
                self._serialize(state.active_event, ongoing=True)
                for state in self._sessions.values()
                if state.active_event is not None
            ]

    def recent_events(self, limit: int = 20) -> List[dict]:
        with self._lock:
            items = self._completed_events[-limit:]
            return [self._serialize(evt, ongoing=False) for evt in items]

    @staticmethod
    def _serialize(evt: CollapseEvent, ongoing: bool) -> dict:
        duration = None
        if evt.ended_at is not None:
            duration = round((evt.ended_at - evt.started_at).total_seconds(), 3)
        return {
            "sessionId": evt.session_id,
            "userId": evt.user_id,
            "startedAt": evt.started_at.isoformat(),
            "endedAt": evt.ended_at.isoformat() if evt.ended_at else None,
            "durationSeconds": duration,
            "alertCount": evt.alert_count,
            "lastAlertAt": evt.last_alert_at.isoformat() if evt.last_alert_at else None,
            "recovered": evt.recovered,
            "ongoing": ongoing,
        }
