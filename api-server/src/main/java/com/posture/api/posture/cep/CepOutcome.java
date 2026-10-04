package com.posture.api.posture.cep;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * {@link PostureCepEngine#handle}/{@link PostureCepEngine#expireStaleSessions}가
 * 반환하는 상태 전환 결과. posture-cep(Python)의
 * {@code {"type": ..., "event": {...}}} dict와 같은 모양을 유지한다 —
 * {@link CepAdminController}가 그대로 JSON으로 내려주고,
 * {@link CepJdbcRepository#recordEvent}가 그대로 받아 DB에 기록한다.
 */
public final class CepOutcome {

    public enum Type { EVENT_STARTED, RE_ALERT, EVENT_ENDED }

    private final Type type;
    private final CollapseEvent event;

    CepOutcome(Type type, CollapseEvent event) {
        this.type = type;
        this.event = event;
    }

    public Type type() {
        return type;
    }

    String sessionId() {
        return event.sessionId;
    }

    String userId() {
        return event.userId;
    }

    Instant startedAt() {
        return event.startedAt;
    }

    Instant endedAt() {
        return event.endedAt;
    }

    Double durationSeconds() {
        return event.durationSeconds();
    }

    int alertCount() {
        return event.alertCount;
    }

    Instant lastAlertAt() {
        return event.lastAlertAt;
    }

    boolean recovered() {
        return event.recovered;
    }

    boolean ongoing() {
        return event.endedAt == null;
    }

    /** 조회 API(/cep/active, /cep/events/recent) 응답용 JSON 직렬화 맵. */
    public Map<String, Object> toResponseMap() {
        Map<String, Object> map = new LinkedHashMap<>();
        map.put("sessionId", sessionId());
        map.put("userId", userId());
        map.put("startedAt", startedAt().toString());
        map.put("endedAt", endedAt() != null ? endedAt().toString() : null);
        map.put("durationSeconds", durationSeconds());
        map.put("alertCount", alertCount());
        map.put("lastAlertAt", lastAlertAt() != null ? lastAlertAt().toString() : null);
        map.put("recovered", recovered());
        map.put("ongoing", ongoing());
        return map;
    }
}
