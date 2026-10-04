package com.posture.api.posture.cep;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * posture-cep(Python, {@code app/session_expiry.py})의
 * {@code SessionExpiryWorker}를 그대로 이식한 것 (D-10 로직, D-13으로
 * api-server에 이식).
 *
 * {@code cep.session-expiry-interval-seconds}(기본 60초)마다 자동으로
 * 돌며, {@code POST /cep/sessions/expire}로 즉시 트리거할 수도 있다
 * (VM에서 5분 타임아웃을 기다리지 않고 바로 검증할 때 썼던 것과 동일한
 * 용도 — {@link CepAdminController} 참고).
 */
@Component
public class SessionExpiryScheduler {

    private static final Logger log = LoggerFactory.getLogger(SessionExpiryScheduler.class);

    private final PostureCepEngine engine;
    private final CepJdbcRepository repository;
    private final double timeoutSeconds;

    public SessionExpiryScheduler(
            PostureCepEngine engine,
            CepJdbcRepository repository,
            @Value("${cep.session-timeout-seconds:300}") double timeoutSeconds) {
        this.engine = engine;
        this.repository = repository;
        this.timeoutSeconds = timeoutSeconds;
    }

    @Scheduled(
            initialDelayString = "#{${cep.session-expiry-interval-seconds:60} * 1000}",
            fixedDelayString = "#{${cep.session-expiry-interval-seconds:60} * 1000}")
    public void scheduledRun() {
        runOnce();
    }

    /**
     * 만료 검사를 한 번 수행한다. 주기 실행뿐 아니라 수동 트리거
     * ({@code POST /cep/sessions/expire})에서도 직접 호출한다. 원본
     * Python 워커와 같은 모양의 결과 맵({@code finalized_events},
     * {@code ended_sessions_db}, {@code error})을 반환한다.
     */
    public Map<String, Object> runOnce() {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("finalized_events", 0);
        result.put("ended_sessions_db", 0);
        result.put("error", null);
        try {
            Instant now = Instant.now();
            List<CepOutcome> outcomes = engine.expireStaleSessions(now, timeoutSeconds);
            for (CepOutcome outcome : outcomes) {
                log.info("세션 타임아웃으로 붕괴 이벤트 강제 종료: sessionId={}", outcome.sessionId());
                repository.recordEvent(outcome);
            }
            result.put("finalized_events", outcomes.size());

            int expiredRows = repository.expireStaleSessions((int) timeoutSeconds);
            result.put("ended_sessions_db", expiredRows);
            if (expiredRows > 0) {
                log.info("sessions 테이블 {}건을 ENDED로 마킹함", expiredRows);
            }
        } catch (Exception exc) {
            log.error("세션 만료 처리 중 예외 발생 (다음 주기에 재시도)", exc);
            result.put("error", exc.getMessage());
        }
        return result;
    }
}
