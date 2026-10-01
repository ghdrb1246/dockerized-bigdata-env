package com.posture.api.posture.event;

import com.posture.api.posture.dto.PostureSummaryRequest;

import java.time.Instant;
import java.util.List;

/**
 * Kafka `posture.summary` 토픽에 실제로 발행되는 이벤트 형태.
 *
 * 클라이언트 요청(PostureSummaryRequest)에 서버 수신 시각과 스키마
 * 버전을 더해 downstream(CEP, Spark, HDFS 적재)이 파싱할 수 있는
 * 안정적인 계약(schema)을 유지한다.
 */
public record PostureSummaryEvent(
        int schemaVersion,
        String sessionId,
        String userId,
        Instant capturedAt,
        Instant serverReceivedAt,
        List<Double> featureVector,
        Double deviationScore,
        String ruleStatus,
        Double sampleRateHz
) {
    public static final int CURRENT_SCHEMA_VERSION = 1;

    public static PostureSummaryEvent from(PostureSummaryRequest request, Instant serverReceivedAt) {
        Instant capturedAt = request.capturedAt() != null ? request.capturedAt() : serverReceivedAt;
        return new PostureSummaryEvent(
                CURRENT_SCHEMA_VERSION,
                request.sessionId(),
                request.userId(),
                capturedAt,
                serverReceivedAt,
                request.featureVector(),
                request.deviationScore(),
                request.ruleStatus(),
                request.sampleRateHz()
        );
    }
}
