package com.posture.api.posture.cep;

import java.time.Instant;

/**
 * posture-cep(Python)의 {@code _SessionState} dataclass를 그대로 옮긴
 * 가변 모델. 세션 하나의 상태머신 진행 상황을 담는다.
 */
final class SessionState {
    /** (D-04) 외부 저장소 키 — userId, 없으면 sessionId. */
    String stateKey;
    String userId;
    Instant candidateSince;
    Instant recoverySince;
    CollapseEvent activeEvent;
    /**
     * 이 세션에서 마지막으로 이벤트를 받은 시각(capturedAt 기준). 상태
     * 전환과는 별개로 "세션이 아직 살아있는가"를 판단하는 용도로만
     * 쓴다 — {@link SessionExpiryScheduler}가 이 값을 기준으로 오래된
     * 세션을 골라낸다.
     */
    Instant lastSeen;
}
