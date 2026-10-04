package com.posture.api.posture.cep;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.sql.Timestamp;
import java.time.Instant;

/**
 * posture-cep(Python, {@code app/db.py})이 {@code sessions}/{@code collapse_events}
 * 테이블에 쓰던 upsert 로직을 그대로 옮긴 것. (D-13)
 *
 * 원본과 동일한 방어 원칙을 유지한다 — 이 레포지토리의 쓰기가
 * 실패해도(DB 일시 단절 등) 상태머신 판정 흐름 자체는 멈추지 않는다.
 * 호출부({@link PostureInferenceConsumer}, {@link SessionExpiryScheduler})는
 * 예외를 잡아 로그만 남기고 계속 진행한다.
 */
@Repository
public class CepJdbcRepository {

    private static final Logger log = LoggerFactory.getLogger(CepJdbcRepository.class);

    private static final String SESSION_UPSERT_SQL = """
            INSERT INTO sessions
                (session_id, user_id, started_at, last_seen_at, sample_count, status)
            VALUES (?, ?, ?, ?, 1, 'ACTIVE')
            ON DUPLICATE KEY UPDATE
                last_seen_at = VALUES(last_seen_at),
                sample_count = sample_count + 1
            """;

    private static final String COLLAPSE_EVENT_UPSERT_SQL = """
            INSERT INTO collapse_events
                (session_id, user_id, started_at, ended_at, duration_seconds,
                 alert_count, last_alert_at, recovered, ongoing)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE
                ended_at = VALUES(ended_at),
                duration_seconds = VALUES(duration_seconds),
                alert_count = VALUES(alert_count),
                last_alert_at = VALUES(last_alert_at),
                recovered = VALUES(recovered),
                ongoing = VALUES(ongoing)
            """;

    private static final String EXPIRE_SESSIONS_SQL = """
            UPDATE sessions
            SET status = 'ENDED'
            WHERE status = 'ACTIVE'
              AND last_seen_at < (UTC_TIMESTAMP(3) - INTERVAL ? SECOND)
            """;

    private final JdbcTemplate jdbcTemplate;

    public CepJdbcRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    /**
     * {@code posture.inference}에서 들어온 원본 이벤트(상태 전환 여부와
     * 무관한 "매 샘플")를 받아 {@code sessions} 테이블을 upsert한다.
     * D-12(sessions upsert)에서 이미 검증된 SQL을 그대로 옮긴 것이다.
     */
    public boolean recordSample(InferenceEvent event) {
        if (event.sessionId() == null) {
            return false;
        }
        Instant capturedAt;
        try {
            capturedAt = Instant.parse(event.capturedAt());
        } catch (Exception exc) {
            log.warn("capturedAt을 파싱할 수 없어 세션 upsert를 건너뜀 (sessionId={}): {}",
                    event.sessionId(), exc.getMessage());
            return false;
        }
        try {
            jdbcTemplate.update(SESSION_UPSERT_SQL,
                    event.sessionId(), event.userId(), Timestamp.from(capturedAt), Timestamp.from(capturedAt));
            return true;
        } catch (Exception exc) {
            log.warn("세션 upsert 실패 (sessionId={}): {}", event.sessionId(), exc.getMessage());
            return false;
        }
    }

    /**
     * {@link PostureCepEngine}이 반환한 상태 전환 결과를
     * {@code collapse_events} 테이블에 upsert한다.
     */
    public boolean recordEvent(CepOutcome outcome) {
        try {
            jdbcTemplate.update(COLLAPSE_EVENT_UPSERT_SQL,
                    outcome.sessionId(),
                    outcome.userId(),
                    Timestamp.from(outcome.startedAt()),
                    outcome.endedAt() != null ? Timestamp.from(outcome.endedAt()) : null,
                    outcome.durationSeconds(),
                    outcome.alertCount(),
                    outcome.lastAlertAt() != null ? Timestamp.from(outcome.lastAlertAt()) : null,
                    outcome.recovered() ? 1 : 0,
                    outcome.ongoing() ? 1 : 0);
            return true;
        } catch (Exception exc) {
            log.warn("붕괴 이벤트 DB 기록 실패 (sessionId={}, type={}): {}",
                    outcome.sessionId(), outcome.type(), exc.getMessage());
            return false;
        }
    }

    /**
     * {@code last_seen_at}이 {@code timeoutSeconds}초 이상 갱신되지 않은
     * ACTIVE 세션을 한 번에 ENDED로 마킹한다 (D-10).
     *
     * @return 이번 호출로 ENDED로 바뀐 행 수. 실패 시 0을 반환하고
     *         예외를 던지지 않는다.
     */
    public int expireStaleSessions(int timeoutSeconds) {
        try {
            return jdbcTemplate.update(EXPIRE_SESSIONS_SQL, timeoutSeconds);
        } catch (Exception exc) {
            log.warn("세션 만료 처리(sessions UPDATE) 실패: {}", exc.getMessage());
            return 0;
        }
    }
}
