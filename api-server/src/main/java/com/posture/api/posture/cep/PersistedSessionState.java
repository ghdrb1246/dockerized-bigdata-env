package com.posture.api.posture.cep;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;

/**
 * {@link SessionState}를 외부 저장소(Redis Hash)에 담기 위한 불변 스냅샷 (D-04).
 *
 * {@code state}는 v4 설계(Posture_Architecture_v4.md 5.4)의 상태 이름으로
 * 파생해서 함께 저장한다 — 판정 로직은 기존 필드(candidateSince 등)만 보고,
 * {@code state}/{@code since}는 사람이 redis-cli로 볼 때와 향후 FE 재접속 시
 * 현재 상태 표시용이다.
 * <ul>
 *   <li>NORMAL — 아무 진행 상황 없음 (저장하지 않고 키를 지운다)</li>
 *   <li>SUSPECT — 붕괴 후보 진행 중, 아직 지속조건 미충족</li>
 *   <li>BAD — 붕괴 이벤트 확정, 진행 중</li>
 *   <li>RECOVERING — 이벤트 진행 중이나 정상 판정이 이어지는 중(회복 대기)</li>
 * </ul>
 * 시각은 v4 메시지 규격과 같이 epoch milliseconds 문자열로 저장한다. 값이 없는
 * 필드는 빈 문자열로 저장한다(Hash 전체를 매번 덮어써 이전 값이 남지 않게).
 */
public record PersistedSessionState(
        String sessionId,
        String userId,
        Instant candidateSince,
        Instant recoverySince,
        Instant eventStartedAt,
        Instant eventLastAlertAt,
        int eventAlertCount,
        Instant lastSeen
) {

    static final String NORMAL = "NORMAL";
    static final String SUSPECT = "SUSPECT";
    static final String BAD = "BAD";
    static final String RECOVERING = "RECOVERING";

    static PersistedSessionState of(String sessionId, SessionState s) {
        CollapseEvent evt = s.activeEvent;
        return new PersistedSessionState(
                sessionId,
                s.userId,
                s.candidateSince,
                s.recoverySince,
                evt != null ? evt.startedAt : null,
                evt != null ? evt.lastAlertAt : null,
                evt != null ? evt.alertCount : 0,
                s.lastSeen);
    }

    String state() {
        if (eventStartedAt != null) {
            return recoverySince != null ? RECOVERING : BAD;
        }
        return candidateSince != null ? SUSPECT : NORMAL;
    }

    /** 현재 상태가 시작된 시각 (v4 Hash의 {@code since}). */
    Instant since() {
        return switch (state()) {
            case SUSPECT -> candidateSince;
            case BAD -> eventStartedAt;
            case RECOVERING -> recoverySince;
            default -> null;
        };
    }

    boolean isNormal() {
        return NORMAL.equals(state());
    }

    /** lastSeen을 뺀 판정 관련 필드가 같은지 — 같으면 저장소에 다시 쓸 필요가 없다. */
    boolean sameJudgmentAs(PersistedSessionState other) {
        return other != null
                && Objects.equals(sessionId, other.sessionId)
                && Objects.equals(candidateSince, other.candidateSince)
                && Objects.equals(recoverySince, other.recoverySince)
                && Objects.equals(eventStartedAt, other.eventStartedAt)
                && Objects.equals(eventLastAlertAt, other.eventLastAlertAt)
                && eventAlertCount == other.eventAlertCount;
    }

    SessionState toSessionState(String stateKey) {
        SessionState s = new SessionState();
        s.stateKey = stateKey;
        s.userId = userId;
        s.candidateSince = candidateSince;
        s.recoverySince = recoverySince;
        s.lastSeen = lastSeen;
        if (eventStartedAt != null) {
            CollapseEvent evt = new CollapseEvent(sessionId, userId, eventStartedAt, eventLastAlertAt);
            evt.alertCount = Math.max(1, eventAlertCount);
            s.activeEvent = evt;
        }
        return s;
    }

    Map<String, String> toHash() {
        Map<String, String> h = new LinkedHashMap<>();
        put(h, "sessionId", sessionId);
        put(h, "userId", userId);
        put(h, "state", state());
        put(h, "since", millis(since()));
        put(h, "candidateSince", millis(candidateSince));
        put(h, "recoverySince", millis(recoverySince));
        put(h, "episodeStartedAt", millis(eventStartedAt));
        put(h, "lastAlertAt", millis(eventLastAlertAt));
        put(h, "alertCount", eventStartedAt != null ? Integer.toString(eventAlertCount) : null);
        put(h, "lastSeen", millis(lastSeen));
        return h;
    }

    /** Redis Hash → 스냅샷. 필수 필드(sessionId)가 없거나 형식이 깨졌으면 {@code null}. */
    static PersistedSessionState fromHash(Map<?, ?> h) {
        if (h == null || h.isEmpty()) {
            return null;
        }
        try {
            String sessionId = str(h, "sessionId");
            if (sessionId == null) {
                return null;
            }
            String alertCount = str(h, "alertCount");
            return new PersistedSessionState(
                    sessionId,
                    str(h, "userId"),
                    instant(h, "candidateSince"),
                    instant(h, "recoverySince"),
                    instant(h, "episodeStartedAt"),
                    instant(h, "lastAlertAt"),
                    alertCount != null ? Integer.parseInt(alertCount) : 0,
                    instant(h, "lastSeen"));
        } catch (RuntimeException exc) {
            return null;
        }
    }

    /** null은 빈 문자열로 저장한다 — 매번 모든 필드를 덮어써서 이전 값이 남지 않게 하기 위함. */
    private static void put(Map<String, String> h, String k, String v) {
        h.put(k, v != null ? v : "");
    }

    private static String millis(Instant t) {
        return t != null ? Long.toString(t.toEpochMilli()) : null;
    }

    private static String str(Map<?, ?> h, String k) {
        Object v = h.get(k);
        return v != null && !v.toString().isEmpty() ? v.toString() : null;
    }

    private static Instant instant(Map<?, ?> h, String k) {
        String v = str(h, k);
        return v != null ? Instant.ofEpochMilli(Long.parseLong(v)) : null;
    }
}
