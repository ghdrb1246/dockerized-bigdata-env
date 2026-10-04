package com.posture.api.posture.cep;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.locks.ReentrantLock;

/**
 * posture-cep(Python, {@code app/state_machine.py})의 {@code PostureCepEngine}을
 * 그대로 Java로 이식한 상태머신. (2026-10-02 아키텍처 v4 전환 결정, D-13)
 *
 * posture-cep을 별도 서비스로 운영하는 대신 이 엔진을 api-server 안에
 * 두기로 했으나, 판정 로직 자체(지속조건·회복조건·재알림 간격)는 VM에서
 * 이미 검증된 것(T-01, DN-07/DN-19/DN-21)을 그대로 재사용한다 — 숫자
 * 하나 바뀌지 않았다. 달라진 건 "어느 프로세스 안에서 도는가"뿐이다.
 *
 * 원본과 마찬가지로 이벤트 도착 순서(Kafka 오프셋)가 아니라 이벤트에
 * 담긴 {@code capturedAt}을 기준으로 지속시간을 계산한다.
 */
@Component
public class PostureCepEngine {

    private static final Logger log = LoggerFactory.getLogger(PostureCepEngine.class);

    static final String NORMAL_STATUS = "NORMAL";
    static final String UNKNOWN_STATUS = "UNKNOWN";

    private final double persistSeconds;
    private final double recoverySeconds;
    private final double realertSeconds;

    private final Map<String, SessionState> sessions = new HashMap<>();
    private final List<CollapseEvent> completedEvents = new ArrayList<>();
    private final ReentrantLock lock = new ReentrantLock();

    public PostureCepEngine(
            @Value("${cep.persist-seconds:3}") double persistSeconds,
            @Value("${cep.recovery-seconds:3}") double recoverySeconds,
            @Value("${cep.realert-seconds:60}") double realertSeconds) {
        this.persistSeconds = persistSeconds;
        this.recoverySeconds = recoverySeconds;
        this.realertSeconds = realertSeconds;
    }

    /**
     * {@code posture.inference} 이벤트 하나를 처리한다. 상태 전환(에피소드
     * 시작/재알림/종료)이 발생했으면 그 결과를, 아니면 빈 Optional을
     * 반환한다.
     */
    public Optional<CepOutcome> handle(InferenceEvent event) {
        String sessionId = event.sessionId() != null ? event.sessionId() : "unknown";
        String inferredStatus = event.inferredStatus() != null ? event.inferredStatus() : UNKNOWN_STATUS;

        Instant now;
        try {
            now = Instant.parse(event.capturedAt());
        } catch (DateTimeParseException | NullPointerException exc) {
            log.warn("capturedAt을 파싱할 수 없어 이 이벤트는 건너뜀 (sessionId={}): {}",
                    sessionId, exc.getMessage());
            return Optional.empty();
        }

        boolean isCandidate = !NORMAL_STATUS.equals(inferredStatus) && !UNKNOWN_STATUS.equals(inferredStatus);

        lock.lock();
        try {
            SessionState state = sessions.computeIfAbsent(sessionId, id -> new SessionState());
            state.lastSeen = now;

            if (isCandidate) {
                return handleCandidate(sessionId, event, state, now);
            }
            return handleNormal(sessionId, state, now);
        } finally {
            lock.unlock();
        }
    }

    private Optional<CepOutcome> handleCandidate(
            String sessionId, InferenceEvent event, SessionState state, Instant now) {
        // 정상으로 돌아왔다가 다시 붕괴 후보가 됐으면 회복 타이머는 취소
        state.recoverySince = null;

        if (state.activeEvent != null) {
            // 이미 확정된 이벤트가 진행 중 — 재알림 간격만 확인
            CollapseEvent evt = state.activeEvent;
            Double sinceLastAlert = evt.lastAlertAt != null
                    ? (now.toEpochMilli() - evt.lastAlertAt.toEpochMilli()) / 1000.0
                    : null;
            if (sinceLastAlert == null || sinceLastAlert >= realertSeconds) {
                evt.alertCount += 1;
                evt.lastAlertAt = now;
                log.info("재알림 (sessionId={}, alertCount={}, 지속={}s)",
                        sessionId, evt.alertCount,
                        (now.toEpochMilli() - evt.startedAt.toEpochMilli()) / 1000.0);
                return Optional.of(new CepOutcome(CepOutcome.Type.RE_ALERT, evt));
            }
            return Optional.empty();
        }

        if (state.candidateSince == null) {
            state.candidateSince = now;
            return Optional.empty();
        }

        double elapsed = (now.toEpochMilli() - state.candidateSince.toEpochMilli()) / 1000.0;
        if (elapsed < persistSeconds) {
            return Optional.empty();
        }

        // 지속조건 충족 — 붕괴 이벤트 확정
        CollapseEvent evt = new CollapseEvent(sessionId, event.userId(), state.candidateSince, now);
        state.activeEvent = evt;
        log.info("붕괴 이벤트 확정 (sessionId={}, startedAt={}, 지속조건={}s 충족)",
                sessionId, evt.startedAt, elapsed);
        return Optional.of(new CepOutcome(CepOutcome.Type.EVENT_STARTED, evt));
    }

    private Optional<CepOutcome> handleNormal(String sessionId, SessionState state, Instant now) {
        state.candidateSince = null;

        if (state.activeEvent == null) {
            return Optional.empty();
        }

        if (state.recoverySince == null) {
            state.recoverySince = now;
            return Optional.empty();
        }

        double elapsed = (now.toEpochMilli() - state.recoverySince.toEpochMilli()) / 1000.0;
        if (elapsed < recoverySeconds) {
            return Optional.empty();
        }

        CollapseEvent evt = state.activeEvent;
        evt.endedAt = now;
        evt.recovered = true;
        state.activeEvent = null;
        state.recoverySince = null;
        completedEvents.add(evt);
        log.info("붕괴 이벤트 종료 (sessionId={}, 지속시간={}s, alertCount={})",
                sessionId, evt.durationSeconds(), evt.alertCount);
        return Optional.of(new CepOutcome(CepOutcome.Type.EVENT_ENDED, evt));
    }

    /**
     * {@code timeoutSeconds} 이상 새 이벤트가 오지 않은 세션을 만료 처리한다
     * (D-10: 세션 만료·정리 — posture-cep에서 그대로 이식).
     */
    public List<CepOutcome> expireStaleSessions(Instant now, double timeoutSeconds) {
        List<CepOutcome> outcomes = new ArrayList<>();
        lock.lock();
        try {
            List<String> staleIds = new ArrayList<>();
            for (Map.Entry<String, SessionState> entry : sessions.entrySet()) {
                SessionState state = entry.getValue();
                if (state.lastSeen != null
                        && (now.toEpochMilli() - state.lastSeen.toEpochMilli()) / 1000.0 >= timeoutSeconds) {
                    staleIds.add(entry.getKey());
                }
            }
            for (String sid : staleIds) {
                SessionState state = sessions.remove(sid);
                if (state.activeEvent != null) {
                    CollapseEvent evt = state.activeEvent;
                    evt.endedAt = state.lastSeen;
                    evt.recovered = false;
                    completedEvents.add(evt);
                    log.info("세션 타임아웃으로 진행 중이던 붕괴 이벤트 강제 종료 (sessionId={}, 마지막 수신={})",
                            sid, state.lastSeen);
                    outcomes.add(new CepOutcome(CepOutcome.Type.EVENT_ENDED, evt));
                } else {
                    log.info("세션 만료로 상태 정리 (sessionId={}, 마지막 수신={})", sid, state.lastSeen);
                }
            }
        } finally {
            lock.unlock();
        }
        return outcomes;
    }

    public List<Map<String, Object>> activeEvents() {
        lock.lock();
        try {
            List<Map<String, Object>> result = new ArrayList<>();
            for (SessionState state : sessions.values()) {
                if (state.activeEvent != null) {
                    result.add(new CepOutcome(CepOutcome.Type.EVENT_STARTED, state.activeEvent).toResponseMap());
                }
            }
            return result;
        } finally {
            lock.unlock();
        }
    }

    public List<Map<String, Object>> recentEvents(int limit) {
        lock.lock();
        try {
            int from = Math.max(0, completedEvents.size() - limit);
            List<Map<String, Object>> result = new ArrayList<>();
            for (CollapseEvent evt : completedEvents.subList(from, completedEvents.size())) {
                result.add(new CepOutcome(CepOutcome.Type.EVENT_ENDED, evt).toResponseMap());
            }
            return result;
        } finally {
            lock.unlock();
        }
    }

    /** 테스트 전용 — Python 테스트의 {@code engine._sessions} 직접 접근에 대응. */
    boolean hasSession(String sessionId) {
        lock.lock();
        try {
            return sessions.containsKey(sessionId);
        } finally {
            lock.unlock();
        }
    }
}
