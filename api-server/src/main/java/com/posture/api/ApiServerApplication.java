package com.posture.api;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * 자세 분석 시스템 API 서버 진입점.
 *
 * 현재 단계(헬스체크 골격)에서는 별도의 컨트롤러를 두지 않고,
 * Spring Boot Actuator가 자동 등록하는 /actuator/health 로
 * 외부 MySQL / Redis / Kafka 연결 상태만 확인한다.
 * 인증·비즈니스 로직(수집 API, 조회 API 등)은 다음 단계에서 추가한다.
 */
@SpringBootApplication
public class ApiServerApplication {
    public static void main(String[] args) {
        SpringApplication.run(ApiServerApplication.class, args);
    }
}
