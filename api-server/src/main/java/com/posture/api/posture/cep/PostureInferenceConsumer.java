package com.posture.api.posture.cep;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;
import tools.jackson.databind.json.JsonMapper;

import java.util.Map;
import java.util.Optional;

/**
 * {@code posture.inference} 토픽을 구독하는 Kafka 컨슈머.
 *
 * posture-cep(Python, {@code app/consumer.py})의 {@code PostureInferenceConsumer}를
 * 그대로 이식했다(D-13). inference-service(지금은 서버 PC, 전환 후에는
 * 외부 GPU PC)가 각 {@code posture.summary} 이벤트를 처리한 결과를 이
 * 토픽에 발행하면, 여기서 순서대로 읽어 {@link PostureCepEngine}에
 * 넘긴다.
 *
 * 메시지 값은 inference-service가 {@code json.dumps(...).encode()}로
 * 만든 평범한 JSON 문자열이다(Kafka 스키마 레지스트리 없음) — 그래서
 * String 역직렬화 후 이 클래스에서 직접 JSON을 파싱한다. v4 메시지
 * 규격 9장 원칙에 따라 모르는 필드는 무시한다(Map으로 파싱 후 필요한
 * 필드만 추출).
 */
@Component
public class PostureInferenceConsumer {

    private static final Logger log = LoggerFactory.getLogger(PostureInferenceConsumer.class);

    private final PostureCepEngine engine;
    private final CepJdbcRepository repository;
    private final JsonMapper jsonMapper;

    public PostureInferenceConsumer(PostureCepEngine engine, CepJdbcRepository repository, JsonMapper jsonMapper) {
        this.engine = engine;
        this.repository = repository;
        this.jsonMapper = jsonMapper;
    }

    /*
     * (D-15) concurrency = 컨슈머 스레드 수. posture.inference 파티션 수와
     * 같게 맞춘다(스레드가 파티션보다 많으면 남는 스레드는 놀기만 한다).
     * 파티션 하나는 항상 스레드 하나만 읽으므로, 같은 키(userId)의 메시지는
     * 여전히 순서대로 처리된다. 서로 다른 사용자는 병렬로 처리되어 DB
     * 커밋 대기가 겹친다 — 단일 스레드 직렬 처리 병목(DN-25)의 해소책.
     * PostureCepEngine은 내부 lock으로 보호되고, lock 안에서는 메모리
     * 연산만 하므로(DB 쓰기는 lock 밖) 스레드 간 경합은 무시할 수준이다.
     */
    @KafkaListener(
            topics = "${app.kafka.topic.posture-inference:posture.inference}",
            groupId = "${spring.kafka.consumer.group-id:api-server-cep}",
            concurrency = "${app.kafka.posture-inference-concurrency:3}")
    public void onMessage(String rawValue) {
        Map<String, Object> raw;
        try {
            raw = jsonMapper.readValue(rawValue, Map.class);
        } catch (Exception exc) {
            log.warn("JSON 파싱 실패, 메시지 건너뜀 (raw={}): {}", rawValue, exc.getMessage());
            return;
        }

        InferenceEvent event = new InferenceEvent(
                asString(raw.get("sessionId")),
                asString(raw.get("userId")),
                asString(raw.get("inferredStatus")),
                asString(raw.get("capturedAt")));

        // sessions 갱신(last_seen_at/sample_count)은 상태 전환 여부와 무관하게
        // 매 샘플마다 수행한다. 실패해도 판정 흐름에 영향을 주지 않는다
        // (repository 쪽이 방어적으로 구현되어 있음).
        repository.recordSample(event);

        Optional<CepOutcome> outcome = engine.handle(event);
        outcome.ifPresent(o -> {
            log.info("posture-cep 상태 전환: {} (sessionId={})", o.type(), o.sessionId());
            repository.recordEvent(o);
        });
    }

    private static String asString(Object value) {
        return value != null ? value.toString() : null;
    }
}
