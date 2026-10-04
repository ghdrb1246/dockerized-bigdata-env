package com.posture.api.posture.cep;

import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * posture-cep(Python, {@code tests/test_state_machine.py})의 시나리오를
 * 그대로 옮긴 단위테스트 (D-13). Kafka/DB 없이 {@link PostureCepEngine#handle}
 * 을 직접 호출해서 지속조건·회복조건·재알림·세션 만료 로직만 검증한다.
 *
 * 시간은 실제 wall-clock이 아니라 이벤트의 capturedAt 필드로 제어하므로
 * 3초/60초를 실제로 기다릴 필요가 없다 — 원본 파이썬 테스트와 동일한
 * 전략이다.
 */
class PostureCepEngineTest {

    private static final Instant BASE = Instant.parse("2026-01-01T00:00:00Z");

    private static PostureCepEngine newEngine() {
        return new PostureCepEngine(3, 3, 60);
    }

    private static String iso(double offsetSeconds) {
        return BASE.plusMillis(Math.round(offsetSeconds * 1000)).toString();
    }

    private static InferenceEvent event(String sessionId, String status, double offsetSeconds) {
        return event(sessionId, status, offsetSeconds, "user-1");
    }

    private static InferenceEvent event(String sessionId, String status, double offsetSeconds, String userId) {
        return new InferenceEvent(sessionId, userId, status, iso(offsetSeconds));
    }

    @Test
    void candidateBelowPersistThresholdProducesNoEvent() {
        PostureCepEngine engine = newEngine();
        assertThat(engine.handle(event("s1", "WARNING", 0.0))).isEmpty();
        assertThat(engine.handle(event("s1", "WARNING", 1.0))).isEmpty();
        assertThat(engine.handle(event("s1", "WARNING", 2.0))).isEmpty();
        assertThat(engine.activeEvents()).isEmpty();
    }

    @Test
    void candidatePersisting3sConfirmsEvent() {
        PostureCepEngine engine = newEngine();
        engine.handle(event("s1", "WARNING", 0.0));
        Optional<CepOutcome> outcome = engine.handle(event("s1", "WARNING", 3.5));

        assertThat(outcome).isPresent();
        assertThat(outcome.get().type()).isEqualTo(CepOutcome.Type.EVENT_STARTED);

        List<Map<String, Object>> active = engine.activeEvents();
        assertThat(active).hasSize(1);
        assertThat(active.get(0)).containsEntry("sessionId", "s1").containsEntry("ongoing", true)
                .containsEntry("alertCount", 1);
    }

    @Test
    void realertAfterIntervalButNotBefore() {
        PostureCepEngine engine = newEngine();
        engine.handle(event("s1", "WARNING", 0.0));
        engine.handle(event("s1", "WARNING", 3.5)); // EVENT_STARTED, alertCount=1

        // 아직 60초가 안 지남 -> 재알림 없음
        assertThat(engine.handle(event("s1", "WARNING", 30.0))).isEmpty();
        assertThat(engine.activeEvents().get(0)).containsEntry("alertCount", 1);

        // 최초 알림(3.5s)로부터 60초 이상 지남 -> 재알림
        Optional<CepOutcome> realert = engine.handle(event("s1", "WARNING", 65.0));
        assertThat(realert).isPresent();
        assertThat(realert.get().type()).isEqualTo(CepOutcome.Type.RE_ALERT);
        assertThat(engine.activeEvents().get(0)).containsEntry("alertCount", 2);
    }

    @Test
    void recoveryAfter3sNormalEndsEvent() {
        PostureCepEngine engine = newEngine();
        engine.handle(event("s1", "WARNING", 0.0));
        engine.handle(event("s1", "WARNING", 3.5)); // EVENT_STARTED at t=0

        engine.handle(event("s1", "NORMAL", 4.0));
        Optional<CepOutcome> outcome = engine.handle(event("s1", "NORMAL", 7.5)); // 3.5s of NORMAL >= 3s

        assertThat(outcome).isPresent();
        assertThat(outcome.get().type()).isEqualTo(CepOutcome.Type.EVENT_ENDED);
        assertThat(outcome.get().toResponseMap()).containsEntry("recovered", true);
        assertThat((Double) outcome.get().toResponseMap().get("durationSeconds")).isCloseTo(7.5, org.assertj.core.data.Offset.offset(0.01));
        assertThat(engine.activeEvents()).isEmpty();

        List<Map<String, Object>> recent = engine.recentEvents(20);
        assertThat(recent).hasSize(1);
        assertThat(recent.get(0)).containsEntry("sessionId", "s1");
    }

    @Test
    void briefRecoveryRelapseDoesNotEndEvent() {
        PostureCepEngine engine = newEngine();
        engine.handle(event("s1", "WARNING", 0.0));
        engine.handle(event("s1", "WARNING", 3.5)); // EVENT_STARTED

        engine.handle(event("s1", "NORMAL", 4.0)); // 회복 타이머 시작
        Optional<CepOutcome> outcome = engine.handle(event("s1", "WARNING", 5.0)); // 3초 전에 다시 붕괴 후보
        assertThat(outcome).isEmpty(); // 이미 활성 이벤트가 있고 재알림 간격도 안 지남 -> empty

        assertThat(engine.activeEvents()).hasSize(1);
        assertThat(engine.recentEvents(20)).isEmpty();
    }

    @Test
    void independentSessionsDoNotInterfere() {
        PostureCepEngine engine = newEngine();
        engine.handle(event("s1", "WARNING", 0.0));
        engine.handle(event("s2", "WARNING", 0.0));
        engine.handle(event("s1", "WARNING", 3.5));

        List<String> activeIds = engine.activeEvents().stream()
                .map(m -> (String) m.get("sessionId"))
                .toList();
        assertThat(activeIds).containsExactly("s1");
    }

    @Test
    void unparseableCapturedAtIsSkippedWithoutError() {
        PostureCepEngine engine = newEngine();
        InferenceEvent bad = new InferenceEvent("s1", "user-1", "WARNING", "not-a-timestamp");
        assertThat(engine.handle(bad)).isEmpty();
        assertThat(engine.activeEvents()).isEmpty();
    }

    // --- expireStaleSessions (D-10: 세션 만료·정리) ---------------------

    @Test
    void expireRemovesQuietSessionWithoutActiveEvent() {
        PostureCepEngine engine = newEngine();
        engine.handle(event("s1", "NORMAL", 0.0));
        assertThat(engine.hasSession("s1")).isTrue();

        // 마지막 이벤트(BASE+0s)로부터 실제 시각 기준 400초가 지났다고
        // 가정 -> timeout(300s) 초과로 만료
        Instant now = BASE.plusSeconds(400);
        List<CepOutcome> outcomes = engine.expireStaleSessions(now, 300);

        assertThat(outcomes).isEmpty(); // 진행 중인 이벤트가 없었으니 종료 이벤트도 없음
        assertThat(engine.hasSession("s1")).isFalse(); // 메모리에서 완전히 제거됨
    }

    @Test
    void expireKeepsSessionsWithinTimeout() {
        PostureCepEngine engine = newEngine();
        engine.handle(event("s1", "NORMAL", 0.0));

        Instant now = BASE.plusSeconds(100); // 아직 300초 안 지남
        List<CepOutcome> outcomes = engine.expireStaleSessions(now, 300);

        assertThat(outcomes).isEmpty();
        assertThat(engine.hasSession("s1")).isTrue(); // 살아있어야 함
    }

    @Test
    void expireFinalizesActiveEventAsNotRecovered() {
        PostureCepEngine engine = newEngine();
        engine.handle(event("s1", "WARNING", 0.0));
        engine.handle(event("s1", "WARNING", 3.5)); // EVENT_STARTED, lastSeen=BASE+3.5s
        assertThat(engine.activeEvents()).hasSize(1);

        // 마지막 이벤트(BASE+3.5s) 이후로 아무 것도 안 옴 -> 세션이 끊김
        Instant now = BASE.plusSeconds(400);
        List<CepOutcome> outcomes = engine.expireStaleSessions(now, 300);

        assertThat(outcomes).hasSize(1);
        CepOutcome outcome = outcomes.get(0);
        assertThat(outcome.type()).isEqualTo(CepOutcome.Type.EVENT_ENDED);
        Map<String, Object> map = outcome.toResponseMap();
        assertThat(map).containsEntry("sessionId", "s1").containsEntry("recovered", false)
                .containsEntry("ongoing", false);

        assertThat(engine.activeEvents()).isEmpty();
        List<Map<String, Object>> recent = engine.recentEvents(20);
        assertThat(recent).hasSize(1);
        assertThat(recent.get(0)).containsEntry("sessionId", "s1");
        assertThat(engine.hasSession("s1")).isFalse();
    }

    @Test
    void expireIsIndependentPerSession() {
        PostureCepEngine engine = newEngine();
        engine.handle(event("stale", "NORMAL", 0.0));
        engine.handle(event("fresh", "NORMAL", 390.0)); // 훨씬 나중에 도착

        Instant now = BASE.plusSeconds(400);
        List<CepOutcome> outcomes = engine.expireStaleSessions(now, 300);

        assertThat(outcomes).isEmpty();
        assertThat(engine.hasSession("stale")).isFalse(); // 400 - 0 = 400s >= 300s -> 만료
        assertThat(engine.hasSession("fresh")).isTrue();  // 400 - 390 = 10s < 300s -> 유지
    }
}
