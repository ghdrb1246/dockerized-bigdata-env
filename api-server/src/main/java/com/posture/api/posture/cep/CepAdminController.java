package com.posture.api.posture.cep;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

/**
 * posture-cep(Python)이 노출하던 {@code /cep/*} 조회·관리 API를 그대로
 * api-server로 옮긴 것(D-13). 응답 형태는 posture-cep과 동일하게
 * 유지해서, 기존에 이 엔드포인트를 참조하던 테스트 스크립트를 그대로
 * 쓸 수 있게 한다.
 */
@RestController
public class CepAdminController {

    private final PostureCepEngine engine;
    private final SessionExpiryScheduler sessionExpiryScheduler;

    public CepAdminController(PostureCepEngine engine, SessionExpiryScheduler sessionExpiryScheduler) {
        this.engine = engine;
        this.sessionExpiryScheduler = sessionExpiryScheduler;
    }

    /** 현재 지속조건을 충족해 진행 중인(아직 회복되지 않은) 붕괴 이벤트 목록. */
    @GetMapping("/cep/active")
    public Map<String, Object> activeEvents() {
        List<Map<String, Object>> events = engine.activeEvents();
        return Map.of("count", events.size(), "events", events);
    }

    /** 최근 종료(회복)된 붕괴 이벤트 목록. */
    @GetMapping("/cep/events/recent")
    public Map<String, Object> recentEvents(@RequestParam(defaultValue = "20") int limit) {
        int bounded = Math.max(1, Math.min(limit, 100));
        List<Map<String, Object>> events = engine.recentEvents(bounded);
        return Map.of("count", events.size(), "events", events);
    }

    /**
     * 세션 만료 검사를 즉시 한 번 수행한다 (D-10). 원래는
     * {@link SessionExpiryScheduler}가 주기적으로(기본 60초) 자동 실행하지만,
     * 타임아웃(기본 5분)을 기다리지 않고 바로 검증하고 싶을 때 이
     * 엔드포인트로 즉시 트리거할 수 있다.
     */
    @PostMapping("/cep/sessions/expire")
    public Map<String, Object> expireSessionsNow() {
        return sessionExpiryScheduler.runOnce();
    }
}
