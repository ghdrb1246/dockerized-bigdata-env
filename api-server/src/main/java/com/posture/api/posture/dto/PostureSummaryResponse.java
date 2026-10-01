package com.posture.api.posture.dto;

/**
 * 수집 API 응답. 이 단계에서는 실제 저장(DB) 없이 Kafka publish 성공 여부만
 * 알려준다 — MySQL 연동(세션/이벤트 영속화)은 다음 단계에서 추가한다.
 */
public record PostureSummaryResponse(
        String sessionId,
        String status,      // ACCEPTED
        String topic,       // 실제 발행된 Kafka 토픽명
        long serverReceivedAtEpochMs
) {
}
