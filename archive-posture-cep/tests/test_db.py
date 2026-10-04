"""
app/db.py 테스트. 실제 MySQL 없이도 검증 가능한 부분만 다룬다:

  - CEP_DB_ENABLED=false / DB_HOST 미설정 시 조용히 스킵되는지
    (record_event가 False를 반환하고 예외를 던지지 않는지)
  - datetime 문자열 변환(_to_mysql_datetime)이 정확한지
  - 커넥션 풀을 흉내낸 가짜 객체로 record_event가 올바른 SQL 파라미터를
    만들어 execute/commit을 호출하는지

실제 MySQL 커넥션 풀 생성·쿼리 실행은 VM에서 진짜 MySQL을 붙여
검증한다(README_MySQL_구축_가이드.md).
"""
import importlib

import pytest


@pytest.fixture(autouse=True)
def reset_db_module(monkeypatch):
    """매 테스트마다 app.db를 새로 로드해 모듈 전역 캐시(_pool 등)를 초기화한다."""
    import app.db as db_module

    importlib.reload(db_module)
    yield db_module
    importlib.reload(db_module)


def test_record_event_skips_when_db_disabled(monkeypatch, reset_db_module):
    db = reset_db_module
    monkeypatch.setattr(db, "DB_ENABLED", False)

    outcome = {
        "type": "EVENT_STARTED",
        "event": {"sessionId": "s1", "userId": "u1", "startedAt": "2026-01-01T00:00:03+00:00",
                   "endedAt": None, "durationSeconds": None, "alertCount": 1,
                   "lastAlertAt": "2026-01-01T00:00:03+00:00", "recovered": False, "ongoing": True},
    }
    assert db.record_event(outcome) is False


def test_record_event_skips_when_host_missing(monkeypatch, reset_db_module):
    db = reset_db_module
    monkeypatch.setattr(db, "DB_ENABLED", True)
    monkeypatch.setattr(db, "DB_HOST", "")

    outcome = {"type": "EVENT_STARTED", "event": {"sessionId": "s1"}}
    assert db.record_event(outcome) is False


def test_to_mysql_datetime_strips_utc_offset(reset_db_module):
    db = reset_db_module
    assert db._to_mysql_datetime("2026-01-01T00:00:03.032994+00:00") == "2026-01-01 00:00:03.032994"


def test_to_mysql_datetime_strips_z_suffix(reset_db_module):
    db = reset_db_module
    assert db._to_mysql_datetime("2026-01-01T00:00:03Z") == "2026-01-01 00:00:03"


def test_to_mysql_datetime_none_passthrough(reset_db_module):
    db = reset_db_module
    assert db._to_mysql_datetime(None) is None


class _FakeCursor:
    def __init__(self):
        self.executed = None

    def execute(self, sql, params):
        self.executed = (sql, params)

    def close(self):
        pass


class _FakeConnection:
    def __init__(self):
        self.cursor_obj = _FakeCursor()
        self.committed = False
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


class _FakePool:
    def __init__(self):
        self.connection = _FakeConnection()

    def get_connection(self):
        return self.connection


def test_record_event_upserts_with_fake_pool(monkeypatch, reset_db_module):
    db = reset_db_module
    fake_pool = _FakePool()
    monkeypatch.setattr(db, "_get_pool", lambda: fake_pool)

    outcome = {
        "type": "EVENT_ENDED",
        "event": {
            "sessionId": "session-1",
            "userId": "user-1",
            "startedAt": "2026-01-01T00:00:00+00:00",
            "endedAt": "2026-01-01T00:00:07.5+00:00",
            "durationSeconds": 7.5,
            "alertCount": 1,
            "lastAlertAt": "2026-01-01T00:00:03+00:00",
            "recovered": True,
            "ongoing": False,
        },
    }

    assert db.record_event(outcome) is True
    assert fake_pool.connection.committed is True
    assert fake_pool.connection.closed is True

    _, params = fake_pool.connection.cursor_obj.executed
    assert params == (
        "session-1", "user-1",
        "2026-01-01 00:00:00", "2026-01-01 00:00:07.5",
        7.5, 1, "2026-01-01 00:00:03", 1, 0,
    )


def test_record_event_returns_false_on_execute_error(monkeypatch, reset_db_module):
    db = reset_db_module

    class _BrokenCursor(_FakeCursor):
        def execute(self, sql, params):
            raise RuntimeError("connection lost")

    class _BrokenConnection(_FakeConnection):
        def cursor(self):
            return _BrokenCursor()

    class _BrokenPool:
        def get_connection(self):
            return _BrokenConnection()

    monkeypatch.setattr(db, "_get_pool", lambda: _BrokenPool())

    outcome = {"type": "EVENT_STARTED", "event": {"sessionId": "s1"}}
    assert db.record_event(outcome) is False


def test_record_sample_skips_when_db_disabled(monkeypatch, reset_db_module):
    db = reset_db_module
    monkeypatch.setattr(db, "DB_ENABLED", False)

    event = {"sessionId": "s1", "userId": "u1", "capturedAt": "2026-01-01T00:00:00Z"}
    assert db.record_sample(event) is False


def test_record_sample_skips_when_host_missing(monkeypatch, reset_db_module):
    db = reset_db_module
    monkeypatch.setattr(db, "DB_ENABLED", True)
    monkeypatch.setattr(db, "DB_HOST", "")

    event = {"sessionId": "s1", "userId": "u1", "capturedAt": "2026-01-01T00:00:00Z"}
    assert db.record_sample(event) is False


def test_record_sample_skips_when_session_id_missing(monkeypatch, reset_db_module):
    db = reset_db_module
    fake_pool = _FakePool()
    monkeypatch.setattr(db, "_get_pool", lambda: fake_pool)

    event = {"userId": "u1", "capturedAt": "2026-01-01T00:00:00Z"}
    assert db.record_sample(event) is False
    assert fake_pool.connection.cursor_obj.executed is None


def test_record_sample_skips_when_captured_at_unparseable(monkeypatch, reset_db_module):
    db = reset_db_module
    fake_pool = _FakePool()
    monkeypatch.setattr(db, "_get_pool", lambda: fake_pool)

    event = {"sessionId": "s1", "userId": "u1", "capturedAt": "not-a-timestamp"}
    assert db.record_sample(event) is False
    assert fake_pool.connection.cursor_obj.executed is None


def test_record_sample_upserts_with_fake_pool(monkeypatch, reset_db_module):
    db = reset_db_module
    fake_pool = _FakePool()
    monkeypatch.setattr(db, "_get_pool", lambda: fake_pool)

    event = {
        "sessionId": "session-1",
        "userId": "user-1",
        "capturedAt": "2026-01-01T00:00:03.032994710Z",
        "inferredStatus": "NORMAL",
    }

    assert db.record_sample(event) is True
    assert fake_pool.connection.committed is True
    assert fake_pool.connection.closed is True

    sql, params = fake_pool.connection.cursor_obj.executed
    assert "INSERT INTO sessions" in sql
    assert "ON DUPLICATE KEY UPDATE" in sql
    # Java Instant의 나노초(9자리)는 마이크로초(6자리)로 잘려야 한다
    # (parse_instant()가 기존에도 collapse_events 쪽에서 하던 처리와 동일).
    assert params == (
        "session-1", "user-1",
        "2026-01-01 00:00:03.032994", "2026-01-01 00:00:03.032994",
    )


def test_record_sample_returns_false_on_execute_error(monkeypatch, reset_db_module):
    db = reset_db_module

    class _BrokenCursor(_FakeCursor):
        def execute(self, sql, params):
            raise RuntimeError("connection lost")

    class _BrokenConnection(_FakeConnection):
        def cursor(self):
            return _BrokenCursor()

    class _BrokenPool:
        def get_connection(self):
            return _BrokenConnection()

    monkeypatch.setattr(db, "_get_pool", lambda: _BrokenPool())

    event = {"sessionId": "s1", "userId": "u1", "capturedAt": "2026-01-01T00:00:00Z"}
    assert db.record_sample(event) is False


class _FakeCursorWithRowcount(_FakeCursor):
    def __init__(self, rowcount):
        super().__init__()
        self.rowcount = rowcount


def test_expire_stale_sessions_skips_when_db_disabled(monkeypatch, reset_db_module):
    db = reset_db_module
    monkeypatch.setattr(db, "DB_ENABLED", False)

    assert db.expire_stale_sessions(300) == 0


def test_expire_stale_sessions_returns_affected_rowcount(monkeypatch, reset_db_module):
    db = reset_db_module

    class _FakeConnectionWithRowcount(_FakeConnection):
        def __init__(self, rowcount):
            super().__init__()
            self.cursor_obj = _FakeCursorWithRowcount(rowcount)

    class _FakePoolWithRowcount:
        def __init__(self, rowcount):
            self.connection = _FakeConnectionWithRowcount(rowcount)

        def get_connection(self):
            return self.connection

    fake_pool = _FakePoolWithRowcount(rowcount=3)
    monkeypatch.setattr(db, "_get_pool", lambda: fake_pool)

    affected = db.expire_stale_sessions(300)

    assert affected == 3
    assert fake_pool.connection.committed is True
    assert fake_pool.connection.closed is True
    sql, params = fake_pool.connection.cursor_obj.executed
    assert "UPDATE sessions" in sql
    assert "status = 'ENDED'" in sql
    assert params == (300,)


def test_expire_stale_sessions_returns_zero_on_execute_error(monkeypatch, reset_db_module):
    db = reset_db_module

    class _BrokenCursor(_FakeCursor):
        def execute(self, sql, params):
            raise RuntimeError("connection lost")

    class _BrokenConnection(_FakeConnection):
        def cursor(self):
            return _BrokenCursor()

    class _BrokenPool:
        def get_connection(self):
            return _BrokenConnection()

    monkeypatch.setattr(db, "_get_pool", lambda: _BrokenPool())

    assert db.expire_stale_sessions(300) == 0
