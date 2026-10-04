package com.posture.api.posture.cep;

import java.time.Instant;

/**
 * posture-cep(Python)의 {@code CollapseEvent} dataclass를 그대로 옮긴
 * 가변(mutable) 모델. 세션당 하나의 진행 중인 붕괴 이벤트를 표현한다.
 */
final class CollapseEvent {
    final String sessionId;
    final String userId;
    final Instant startedAt;
    Instant endedAt;
    int alertCount = 1;
    Instant lastAlertAt;
    boolean recovered;

    CollapseEvent(String sessionId, String userId, Instant startedAt, Instant lastAlertAt) {
        this.sessionId = sessionId;
        this.userId = userId;
        this.startedAt = startedAt;
        this.lastAlertAt = lastAlertAt;
    }

    /** 지속 시간(초). 아직 종료되지 않았으면 {@code null}. */
    Double durationSeconds() {
        if (endedAt == null) {
            return null;
        }
        return (endedAt.toEpochMilli() - startedAt.toEpochMilli()) / 1000.0;
    }
}
