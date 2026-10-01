package com.posture.api.posture.controller;

import com.posture.api.posture.service.KafkaPublishException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * 요청 검증 실패(@Valid) 시 필드별 오류 메시지를 담아 400을 반환하고,
 * Kafka 전송 실패(KafkaPublishException) 시 502를 반환한다. 기본 Spring
 * 오류 응답보다 클라이언트(프론트엔드)가 다루기 쉬운 형태로 단순화했다.
 */
@RestControllerAdvice
public class ValidationExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(ValidationExceptionHandler.class);

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, Object>> handleValidation(MethodArgumentNotValidException ex) {
        Map<String, String> fieldErrors = new LinkedHashMap<>();
        ex.getBindingResult().getFieldErrors().forEach(
                error -> fieldErrors.put(error.getField(), error.getDefaultMessage()));

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("timestamp", Instant.now().toString());
        body.put("status", HttpStatus.BAD_REQUEST.value());
        body.put("error", "Bad Request");
        body.put("fieldErrors", fieldErrors);

        return ResponseEntity.badRequest().body(body);
    }

    /**
     * 요청 자체는 유효했지만(검증 통과) Kafka로 전송하는 단계에서 문제가
     * 생긴 경우다. 클라이언트 잘못이 아니라 서버(인프라) 쪽 문제라는
     * 뜻에서 502(Bad Gateway)로 응답한다.
     */
    @ExceptionHandler(KafkaPublishException.class)
    public ResponseEntity<Map<String, Object>> handleKafkaPublishFailure(KafkaPublishException ex) {
        log.error("Kafka publish 실패로 502 응답", ex);

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("timestamp", Instant.now().toString());
        body.put("status", HttpStatus.BAD_GATEWAY.value());
        body.put("error", "Bad Gateway");
        body.put("message", ex.getMessage());

        return ResponseEntity.status(HttpStatus.BAD_GATEWAY).body(body);
    }
}
