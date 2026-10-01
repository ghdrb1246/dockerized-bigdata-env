package com.posture.api.posture.service;

/**
 * Kafka 전송이 확인 가능한 시간 안에 성공하지 못했을 때 던진다
 * (전송 실패, 타임아웃, 인터럽트 등). 클라이언트에는 502로 응답해
 * "요청 자체는 유효했지만 뒤쪽 인프라(Kafka)에 문제가 있었다"는
 * 것을 구분해 알려준다.
 */
public class KafkaPublishException extends RuntimeException {
    public KafkaPublishException(String message, Throwable cause) {
        super(message, cause);
    }
}
