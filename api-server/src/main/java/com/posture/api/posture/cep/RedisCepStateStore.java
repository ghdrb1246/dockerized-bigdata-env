package com.posture.api.posture.cep;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.util.Map;
import java.util.Optional;

/**
 * 상태머신 상태를 Redis Hash {@code posture:state:{userId}}에 저장한다
 * (D-04, PRD FR-BE-04, Posture_Architecture_v4.md 5.9 — TTL 1시간).
 *
 * 쓰기는 상태가 바뀔 때만 일어난다(정상 판정이 계속되는 동안에는 Redis를
 * 건드리지 않음). 상태가 NORMAL로 돌아가면 키를 지운다.
 *
 * Redis 오류 시: 예외를 삼키고 경고 로그를 남긴 뒤 {@value #BACKOFF_MILLIS}ms
 * 동안 Redis 호출 자체를 건너뛴다. Redis가 죽어 있는 동안 매 메시지마다
 * 명령 타임아웃(spring.data.redis.timeout)만큼 컨슈머가 멈추는 것을 막기
 * 위함이다. 그동안 판정은 인메모리 상태로 계속된다.
 */
@Component
public class RedisCepStateStore implements CepStateStore {

    private static final Logger log = LoggerFactory.getLogger(RedisCepStateStore.class);

    static final String KEY_PREFIX = "posture:state:";
    static final long BACKOFF_MILLIS = 10_000;

    private final StringRedisTemplate redis;
    private final boolean enabled;
    private final Duration ttl;
    private volatile long suspendedUntilMillis;

    public RedisCepStateStore(
            StringRedisTemplate redis,
            @Value("${cep.state-store.enabled:true}") boolean enabled,
            @Value("${cep.state-store.ttl-seconds:3600}") long ttlSeconds) {
        this.redis = redis;
        this.enabled = enabled;
        this.ttl = Duration.ofSeconds(ttlSeconds);
        log.info("상태머신 상태 저장소: Redis {} (키 {}{{userId}}, TTL {}s)",
                enabled ? "사용" : "미사용", KEY_PREFIX, ttlSeconds);
    }

    @Override
    public Optional<PersistedSessionState> load(String key) {
        if (!available()) {
            return Optional.empty();
        }
        try {
            Map<Object, Object> hash = redis.opsForHash().entries(KEY_PREFIX + key);
            return Optional.ofNullable(PersistedSessionState.fromHash(hash));
        } catch (Exception exc) {
            suspend("조회", key, exc);
            return Optional.empty();
        }
    }

    @Override
    public void save(String key, PersistedSessionState state) {
        if (!available()) {
            return;
        }
        String redisKey = KEY_PREFIX + key;
        try {
            // toHash()는 모든 필드를 항상 채우므로(없는 값은 빈 문자열) 덮어쓰기만으로 충분
            redis.opsForHash().putAll(redisKey, state.toHash());
            redis.expire(redisKey, ttl);
        } catch (Exception exc) {
            suspend("저장", key, exc);
        }
    }

    @Override
    public void delete(String key) {
        if (!available()) {
            return;
        }
        try {
            redis.delete(KEY_PREFIX + key);
        } catch (Exception exc) {
            suspend("삭제", key, exc);
        }
    }

    private boolean available() {
        return enabled && System.currentTimeMillis() >= suspendedUntilMillis;
    }

    private void suspend(String op, String key, Exception exc) {
        suspendedUntilMillis = System.currentTimeMillis() + BACKOFF_MILLIS;
        log.warn("Redis 상태 {} 실패 (key={}) — {}초 동안 Redis 없이 인메모리 상태로 판정 계속: {}",
                op, key, BACKOFF_MILLIS / 1000, exc.getMessage());
    }
}
