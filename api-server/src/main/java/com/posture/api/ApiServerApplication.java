package com.posture.api;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * 자세 분석 시스템 API 서버 진입점.
 *
 * posture-cep(Python)을 제거하고 그 상태머신·세션 만료 로직을 이
 * 서버로 이식하면서(2026-10-02 아키텍처 v4 전환 결정, D-13)
 * {@code @EnableScheduling}이 추가됐다 —
 * {@link com.posture.api.posture.cep.SessionExpiryScheduler}가 주기적으로
 * 도는 데 필요하다.
 */
@SpringBootApplication
@EnableScheduling
public class ApiServerApplication {
    public static void main(String[] args) {
        SpringApplication.run(ApiServerApplication.class, args);
    }
}
