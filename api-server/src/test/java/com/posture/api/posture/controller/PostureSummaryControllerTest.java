package com.posture.api.posture.controller;

import com.posture.api.posture.dto.PostureSummaryResponse;
import com.posture.api.posture.service.PostureSummaryProducerService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * 컨트롤러 계층만 검증한다(Kafka/DB 등 실제 인프라는 필요 없음).
 * PostureSummaryProducerService는 목(mock)으로 대체해 Kafka 브로커 없이도
 * 요청 검증·응답 매핑 로직을 테스트한다.
 *
 * Spring Boot 4 / Spring Framework 7 기준: @MockBean은 제거되었고
 * (3.4에서 deprecated → 4.0에서 삭제), spring-test의 @MockitoBean으로
 * 대체되었다.
 */
@WebMvcTest(PostureSummaryController.class)
class PostureSummaryControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private PostureSummaryProducerService producerService;

    @Test
    void validRequest_returns202Accepted() throws Exception {
        String requestJson = """
                {
                  "sessionId": "session-001",
                  "userId": "user-001",
                  "featureVector": [0.1, 0.2, 0.3],
                  "deviationScore": 0.42,
                  "ruleStatus": "NORMAL",
                  "sampleRateHz": 10.0
                }
                """;

        when(producerService.publish(any())).thenReturn(
                new PostureSummaryResponse("session-001", "ACCEPTED", "posture.summary", 1_700_000_000_000L));

        mockMvc.perform(post("/api/v1/posture/summary")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(requestJson))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.sessionId").value("session-001"))
                .andExpect(jsonPath("$.status").value("ACCEPTED"))
                .andExpect(jsonPath("$.topic").value("posture.summary"));
    }

    @Test
    void invalidRuleStatus_returns400WithFieldError() throws Exception {
        String requestJson = """
                {
                  "sessionId": "session-002",
                  "userId": "user-001",
                  "featureVector": [0.1],
                  "deviationScore": 0.1,
                  "ruleStatus": "UNKNOWN"
                }
                """;

        mockMvc.perform(post("/api/v1/posture/summary")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(requestJson))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fieldErrors.ruleStatus").exists());
    }

    @Test
    void missingFeatureVector_returns400() throws Exception {
        String requestJson = """
                {
                  "sessionId": "session-003",
                  "userId": "user-001",
                  "featureVector": [],
                  "deviationScore": 0.1,
                  "ruleStatus": "NORMAL"
                }
                """;

        mockMvc.perform(post("/api/v1/posture/summary")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(requestJson))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fieldErrors.featureVector").exists());
    }
}
