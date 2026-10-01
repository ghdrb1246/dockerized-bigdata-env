package com.posture.api.posture.service;

import com.posture.api.posture.dto.PostureSummaryRequest;
import com.posture.api.posture.dto.PostureSummaryResponse;
import com.posture.api.posture.event.PostureSummaryEvent;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.json.JsonMapper;

import java.time.Instant;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

/**
 * 자세 요약 이벤트를 Kafka `posture.summary` 토픽으로 발행한다.
 *
 * 현재 단계 범위: MySQL 영속화(세션/이벤트 저장)는 아직 붙이지 않는다 —
 * 우선 "클라이언트 → API 서버 → Kafka" 구간이 정상 동작하는지만
 * 검증한다. DB가 아직 구축되지 않아도 이 경로는 독립적으로 동작한다.
 *
 * 전송 결과는 최대 5초까지 기다린 뒤 확인한다(완전한 fire-and-forget이
 * 아님) — 지금은 "정말 Kafka까지 도달하는지"를 검증하는 헬스체크 단계라,
 * API 응답이 실제 전송 결과를 반영해야 문제를 바로 알 수 있다. 처리량이
 * 중요해지는 다음 단계에서는 필요하면 완전 비동기로 되돌릴 수 있다.
 *
 * Spring Boot 4 / Jackson 3 기준: ObjectMapper·JsonMapper는 이제
 * `tools.jackson.*` 패키지(Jackson 3)에서 온다(`com.fasterxml.jackson.*`는
 * Jackson 2 호환 모듈에서만 남아 있다). writeValueAsString()도 더 이상
 * 체크 예외를 던지지 않고 unchecked JacksonException을 던진다.
 */
@Service
public class PostureSummaryProducerService {

    private static final Logger log = LoggerFactory.getLogger(PostureSummaryProducerService.class);

    private final KafkaTemplate<String, String> kafkaTemplate;
    private final JsonMapper jsonMapper;
    private final String topic;

    public PostureSummaryProducerService(
            KafkaTemplate<String, String> kafkaTemplate,
            JsonMapper jsonMapper,
            @Value("${app.kafka.topic.posture-summary:posture.summary}") String topic) {
        this.kafkaTemplate = kafkaTemplate;
        this.jsonMapper = jsonMapper;
        this.topic = topic;
    }

    public PostureSummaryResponse publish(PostureSummaryRequest request) {
        Instant serverReceivedAt = Instant.now();
        PostureSummaryEvent event = PostureSummaryEvent.from(request, serverReceivedAt);

        String payload;
        try {
            payload = jsonMapper.writeValueAsString(event);
        } catch (JacksonException e) {
            // 직렬화 실패는 요청 자체가 잘못된 게 아니라 서버 내부 문제이므로 500으로 전파한다.
            // (Jackson 3에서는 unchecked 예외지만, 명확한 원인 메시지로 감싸기 위해 명시적으로 잡는다.)
            throw new IllegalStateException("posture summary 이벤트 직렬화 실패", e);
        }

        // sessionId를 키로 사용해 같은 세션의 이벤트가 같은 파티션 순서를 유지하게 한다
        // (파티션이 여러 개로 늘어나는 2단계 확장을 대비).
        try {
            SendResult<String, String> result = kafkaTemplate
                    .send(topic, request.sessionId(), payload)
                    .get(5, TimeUnit.SECONDS);
            log.info("Kafka publish 성공 (topic={}, partition={}, offset={}, sessionId={})",
                    topic,
                    result.getRecordMetadata().partition(),
                    result.getRecordMetadata().offset(),
                    request.sessionId());
        } catch (ExecutionException e) {
            Throwable cause = e.getCause() != null ? e.getCause() : e;
            throw new KafkaPublishException(
                    "Kafka publish 실패 (topic=%s, sessionId=%s): %s"
                            .formatted(topic, request.sessionId(), cause.getMessage()),
                    cause);
        } catch (TimeoutException e) {
            throw new KafkaPublishException(
                    "Kafka publish 타임아웃(5초 초과) (topic=%s, sessionId=%s)"
                            .formatted(topic, request.sessionId()),
                    e);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new KafkaPublishException(
                    "Kafka publish 중 인터럽트 발생 (topic=%s, sessionId=%s)"
                            .formatted(topic, request.sessionId()),
                    e);
        }

        return new PostureSummaryResponse(
                request.sessionId(),
                "ACCEPTED",
                topic,
                serverReceivedAt.toEpochMilli()
        );
    }
}
