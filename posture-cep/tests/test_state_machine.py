"""
posture-cep 상태 머신(app/state_machine.py) 단위 테스트. Kafka 없이
PostureCepEngine.handle()을 직접 호출해서 지속조건/회복조건/재알림
로직만 검증한다. 시간은 실제 wall-clock이 아니라 이벤트의
capturedAt 필드로 제어하므로 3초/60초를 실제로 기다릴 필요가 없다.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.state_machine import PostureCepEngine, parse_instant

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def iso(offset_seconds: float, nanos: bool = True) -> str:
    """Java Instant.toString()과 비슷한 나노초 단위 ISO 문자열 생성."""
    dt = BASE + timedelta(seconds=offset_seconds)
    if nanos:
        # 9자리(나노초) 정밀도를 흉내낸다 — parse_instant가 6자리로
        # 잘라내는 것까지 같이 검증
        frac = f"{int((offset_seconds % 1) * 1e9):09d}"
        return dt.strftime("%Y-%m-%dT%H:%M:%S") + f".{frac}Z"
    return dt.isoformat()


def make_event(session_id: str, status: str, offset_seconds: float, user_id="user-1") -> dict:
    return {
        "sessionId": session_id,
        "userId": user_id,
        "inferredStatus": status,
        "deviationScore": 0.5,
        "capturedAt": iso(offset_seconds),
        "serverReceivedAt": iso(offset_seconds),
        "model": "test-lstm-v0",
    }


def test_parse_instant_truncates_nanoseconds():
    dt = parse_instant("2026-09-25T14:54:17.909678710Z")
    assert dt.microsecond == 909678
    assert dt.tzinfo is not None


def test_candidate_below_persist_threshold_produces_no_event():
    engine = PostureCepEngine()
    outcomes = [
        engine.handle(make_event("s1", "WARNING", 0.0)),
        engine.handle(make_event("s1", "WARNING", 1.0)),
        engine.handle(make_event("s1", "WARNING", 2.0)),
    ]
    assert all(o is None for o in outcomes)
    assert engine.active_events() == []


def test_candidate_persisting_3s_confirms_event():
    engine = PostureCepEngine()
    engine.handle(make_event("s1", "WARNING", 0.0))
    engine.handle(make_event("s1", "WARNING", 1.5))
    outcome = engine.handle(make_event("s1", "WARNING", 3.5))

    assert outcome is not None
    assert outcome["type"] == "EVENT_STARTED"
    active = engine.active_events()
    assert len(active) == 1
    assert active[0]["sessionId"] == "s1"
    assert active[0]["ongoing"] is True
    assert active[0]["alertCount"] == 1


def test_realert_after_interval_but_not_before():
    engine = PostureCepEngine()
    engine.handle(make_event("s1", "WARNING", 0.0))
    engine.handle(make_event("s1", "WARNING", 3.5))  # EVENT_STARTED, alertCount=1

    # 아직 60초가 안 지남 -> 재알림 없음
    no_realert = engine.handle(make_event("s1", "WARNING", 30.0))
    assert no_realert is None
    assert engine.active_events()[0]["alertCount"] == 1

    # 최초 알림(3.5s)로부터 60초 이상 지남 -> 재알림
    realert = engine.handle(make_event("s1", "WARNING", 65.0))
    assert realert is not None
    assert realert["type"] == "RE_ALERT"
    assert engine.active_events()[0]["alertCount"] == 2


def test_recovery_after_3s_normal_ends_event():
    engine = PostureCepEngine()
    engine.handle(make_event("s1", "WARNING", 0.0))
    engine.handle(make_event("s1", "WARNING", 3.5))  # EVENT_STARTED at t=0

    engine.handle(make_event("s1", "NORMAL", 4.0))
    outcome = engine.handle(make_event("s1", "NORMAL", 7.5))  # 3.5s of NORMAL >= 3s

    assert outcome is not None
    assert outcome["type"] == "EVENT_ENDED"
    assert outcome["event"]["recovered"] is True
    assert outcome["event"]["durationSeconds"] == pytest.approx(7.5, abs=0.01)
    assert engine.active_events() == []
    recent = engine.recent_events()
    assert len(recent) == 1
    assert recent[0]["sessionId"] == "s1"


def test_brief_recovery_relapse_does_not_end_event():
    engine = PostureCepEngine()
    engine.handle(make_event("s1", "WARNING", 0.0))
    engine.handle(make_event("s1", "WARNING", 3.5))  # EVENT_STARTED

    engine.handle(make_event("s1", "NORMAL", 4.0))  # 회복 타이머 시작
    outcome = engine.handle(make_event("s1", "WARNING", 5.0))  # 3초 전에 다시 붕괴 후보
    assert outcome is None  # 이미 활성 이벤트가 있고 재알림 간격도 안 지남 -> None

    # 이벤트는 여전히 진행 중이어야 한다 (회복으로 종료되지 않음)
    assert len(engine.active_events()) == 1
    assert engine.recent_events() == []


def test_independent_sessions_do_not_interfere():
    engine = PostureCepEngine()
    engine.handle(make_event("s1", "WARNING", 0.0))
    engine.handle(make_event("s2", "WARNING", 0.0))
    engine.handle(make_event("s1", "WARNING", 3.5))

    active = {e["sessionId"] for e in engine.active_events()}
    assert active == {"s1"}


def test_unparseable_captured_at_is_skipped_without_error():
    engine = PostureCepEngine()
    bad_event = make_event("s1", "WARNING", 0.0)
    bad_event["capturedAt"] = "not-a-timestamp"
    outcome = engine.handle(bad_event)
    assert outcome is None
    assert engine.active_events() == []


# --- expire_stale_sessions (D-10: 세션 만료·정리) ---------------------


def test_expire_removes_quiet_session_without_active_event():
    engine = PostureCepEngine()
    engine.handle(make_event("s1", "NORMAL", 0.0))
    assert "s1" in engine._sessions

    # 마지막 이벤트(capturedAt=BASE+0s)로부터 실제 시각 기준 400초가
    # 지났다고 가정 -> timeout(300s) 초과로 만료
    now = BASE + timedelta(seconds=400)
    outcomes = engine.expire_stale_sessions(now, timeout_seconds=300)

    assert outcomes == []  # 진행 중인 이벤트가 없었으니 종료 이벤트도 없음
    assert "s1" not in engine._sessions  # 메모리에서 완전히 제거됨


def test_expire_keeps_sessions_within_timeout():
    engine = PostureCepEngine()
    engine.handle(make_event("s1", "NORMAL", 0.0))

    now = BASE + timedelta(seconds=100)  # 아직 300초 안 지남
    outcomes = engine.expire_stale_sessions(now, timeout_seconds=300)

    assert outcomes == []
    assert "s1" in engine._sessions  # 살아있어야 함


def test_expire_finalizes_active_event_as_not_recovered():
    engine = PostureCepEngine()
    engine.handle(make_event("s1", "WARNING", 0.0))
    engine.handle(make_event("s1", "WARNING", 3.5))  # EVENT_STARTED, last_seen=BASE+3.5s
    assert len(engine.active_events()) == 1

    # 마지막 이벤트(BASE+3.5s) 이후로 아무 것도 안 옴 -> 세션이 끊김
    now = BASE + timedelta(seconds=400)
    outcomes = engine.expire_stale_sessions(now, timeout_seconds=300)

    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome["type"] == "EVENT_ENDED"
    assert outcome["event"]["sessionId"] == "s1"
    assert outcome["event"]["recovered"] is False  # 회복을 확인 못 하고 끊김
    assert outcome["event"]["ongoing"] is False

    # 진행 중 이벤트가 사라지고, 최근 종료 이벤트 목록에는 들어감
    assert engine.active_events() == []
    recent = engine.recent_events()
    assert len(recent) == 1
    assert recent[0]["sessionId"] == "s1"
    assert "s1" not in engine._sessions


def test_expire_is_independent_per_session():
    engine = PostureCepEngine()
    engine.handle(make_event("stale", "NORMAL", 0.0))
    engine.handle(make_event("fresh", "NORMAL", 390.0))  # 훨씬 나중에 도착

    now = BASE + timedelta(seconds=400)
    outcomes = engine.expire_stale_sessions(now, timeout_seconds=300)

    assert outcomes == []
    assert "stale" not in engine._sessions  # 400 - 0 = 400s >= 300s -> 만료
    assert "fresh" in engine._sessions      # 400 - 390 = 10s < 300s -> 유지
