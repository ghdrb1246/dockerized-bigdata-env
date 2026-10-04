package com.posture.api.posture.cep;

import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * (D-04) 상태머신 상태 외부 저장 — "api-server 재시작"을 엔진 인스턴스를 새로
 * 만드는 것으로 흉내 내서, 같은 저장소를 공유한 새 엔진이 판정을 이어가는지
 * 검증한다. Redis 대신 메모리 저장소를 쓴다(Redis 연결 코드는 단순 위임).
 */
class PostureCepEngineStateStoreTest {

    private static final Instant BASE = Instant.parse("2026-01-01T00:00:00Z");

    /** Redis Hash 저장을 흉내 내는 메모리 저장소 — toHash/fromHash 왕복까지 거친다. */
    static final class MemoryStore implements CepStateStore {
        final Map<String, Map<String, String>> data = new HashMap<>();
        int saves;
        int deletes;

        @Override
        public Optional<PersistedSessionState> load(String key) {
            return Optional.ofNullable(PersistedSessionState.fromHash(data.get(key)));
        }

        @Override
        public void save(String key, PersistedSessionState state) {
            saves++;
            data.put(key, state.toHash());
        }

        @Override
        public void delete(String key) {
            deletes++;
            data.remove(key);
        }

        String state(String key) {
            Map<String, String> h = data.get(key);
            return h != null ? h.get("state") : null;
        }
    }

    private static PostureCepEngine engine(MemoryStore store) {
        return new PostureCepEngine(3, 3, 60, 300, store);
    }

    private static InferenceEvent event(String sessionId, String userId, String status, double offsetSeconds) {
        return new InferenceEvent(sessionId, userId, status,
                BASE.plusMillis(Math.round(offsetSeconds * 1000)).toString());
    }

    @Test
    void restartDuringActiveEventContinuesWithReAlertInsteadOfNewEvent() {
        MemoryStore store = new MemoryStore();
        PostureCepEngine before = engine(store);
        before.handle(event("s1", "u1", "WARNING", 0.0));
        Optional<CepOutcome> started = before.handle(event("s1", "u1", "WARNING", 3.5));
        assertThat(started.get().type()).isEqualTo(CepOutcome.Type.EVENT_STARTED);
        assertThat(store.state("u1")).isEqualTo("BAD");

        // 재시작: 메모리 상태가 없는 새 엔진, 같은 저장소
        PostureCepEngine after = engine(store);
        Optional<CepOutcome> realert = after.handle(event("s1", "u1", "WARNING", 63.6));
        assertThat(realert.isPresent()).isTrue();
        assertThat(realert.get().type()).isEqualTo(CepOutcome.Type.RE_ALERT);
        assertThat(realert.get().alertCount()).isEqualTo(2);
        assertThat(realert.get().startedAt()).isEqualTo(BASE);

        after.handle(event("s1", "u1", "NORMAL", 64.0));
        assertThat(store.state("u1")).isEqualTo("RECOVERING");
        Optional<CepOutcome> ended = after.handle(event("s1", "u1", "NORMAL", 67.5));
        assertThat(ended.get().type()).isEqualTo(CepOutcome.Type.EVENT_ENDED);
        assertThat(ended.get().durationSeconds()).isEqualTo(67.5);
        assertThat(ended.get().alertCount()).isEqualTo(2);
        // 정상으로 돌아오면 키를 지운다
        assertThat(store.data.containsKey("u1")).isFalse();
    }

    @Test
    void restartDuringSuspectKeepsPersistTimerRunning() {
        MemoryStore store = new MemoryStore();
        engine(store).handle(event("s1", "u1", "WARNING", 0.0));
        assertThat(store.state("u1")).isEqualTo("SUSPECT");

        Optional<CepOutcome> outcome = engine(store).handle(event("s1", "u1", "WARNING", 3.5));
        assertThat(outcome.isPresent()).isTrue();
        assertThat(outcome.get().type()).isEqualTo(CepOutcome.Type.EVENT_STARTED);
        assertThat(outcome.get().startedAt()).isEqualTo(BASE);
    }

    @Test
    void storedStateOfAnotherSessionIsDiscarded() {
        MemoryStore store = new MemoryStore();
        engine(store).handle(event("s1", "u1", "WARNING", 0.0));

        PostureCepEngine after = engine(store);
        // 같은 사용자의 새 세션 — 이전 세션의 후보 타이머(0초)를 이어받으면 안 된다
        assertThat(after.handle(event("s2", "u1", "WARNING", 2.0)).isPresent()).isFalse();
        assertThat(after.handle(event("s2", "u1", "WARNING", 4.0)).isPresent()).isFalse();
        Optional<CepOutcome> outcome = after.handle(event("s2", "u1", "WARNING", 5.5));
        assertThat(outcome.get().type()).isEqualTo(CepOutcome.Type.EVENT_STARTED);
        assertThat(outcome.get().startedAt()).isEqualTo(BASE.plusSeconds(2));
        assertThat(store.data.get("u1").get("sessionId")).isEqualTo("s2");
    }

    @Test
    void staleStoredStateIsDiscarded() {
        MemoryStore store = new MemoryStore();
        engine(store).handle(event("s1", "u1", "WARNING", 0.0));

        PostureCepEngine after = engine(store);
        // 세션 타임아웃(300초)보다 오래 지난 뒤의 메시지 — 처음부터 다시 판정
        assertThat(after.handle(event("s1", "u1", "WARNING", 400.0)).isPresent()).isFalse();
        assertThat(after.handle(event("s1", "u1", "WARNING", 401.0)).isPresent()).isFalse();
    }

    @Test
    void normalSamplesDoNotTouchStore() {
        MemoryStore store = new MemoryStore();
        PostureCepEngine engine = engine(store);
        for (int i = 0; i < 100; i++) {
            engine.handle(event("s1", "u1", "NORMAL", i * 0.1));
        }
        assertThat(store.saves).isEqualTo(0);
        assertThat(store.deletes).isEqualTo(0);
    }

    @Test
    void sessionExpiryDeletesStoredState() {
        MemoryStore store = new MemoryStore();
        PostureCepEngine engine = engine(store);
        engine.handle(event("s1", "u1", "WARNING", 0.0));
        engine.handle(event("s1", "u1", "WARNING", 3.5));
        assertThat(store.data.containsKey("u1")).isTrue();

        engine.expireStaleSessions(BASE.plusSeconds(1000), 300);
        assertThat(store.data.containsKey("u1")).isFalse();
    }

    @Test
    void missingUserIdFallsBackToSessionIdKey() {
        MemoryStore store = new MemoryStore();
        engine(store).handle(event("s9", null, "WARNING", 0.0));
        assertThat(store.data.containsKey("s9")).isTrue();
    }
}
