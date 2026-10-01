package com.posture.api.posture.controller;

import com.posture.api.posture.dto.PostureSummaryRequest;
import com.posture.api.posture.dto.PostureSummaryResponse;
import com.posture.api.posture.service.PostureSummaryProducerService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 자세 요약 이벤트 수집 API.
 *
 * 클라이언트(브라우저)가 1~2Hz 주기로 정규화된 키포인트 특징값 요약을
 * 전송하는 엔드포인트. 원본 영상은 이 API로 전송되지 않는다(아키텍처
 * 원칙 — Posture_Architecture_v3_MVP_Vision.md §2.A.1).
 */
@RestController
@RequestMapping("/api/v1/posture")
public class PostureSummaryController {

    private final PostureSummaryProducerService producerService;

    public PostureSummaryController(PostureSummaryProducerService producerService) {
        this.producerService = producerService;
    }

    @PostMapping("/summary")
    public ResponseEntity<PostureSummaryResponse> submitSummary(
            @Valid @RequestBody PostureSummaryRequest request) {
        PostureSummaryResponse response = producerService.publish(request);
        return ResponseEntity.status(HttpStatus.ACCEPTED).body(response);
    }
}
