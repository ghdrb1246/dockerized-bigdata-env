package com.posture.api.posture.config;

import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;

/**
 * `posture.summary` 토픽 정의.
 *
 * KafkaAdmin(Spring Boot가 spring.kafka.bootstrap-servers 설정으로 자동
 * 등록)이 애플리케이션 시작 시 이 NewTopic이 없으면 생성한다. 단일
 * 브로커(KRaft) 테스트 환경이므로 partitions=1, replication-factor=1로
 * 둔다 — 운영/2단계 확장 시 파티션 수만 조정하면 된다.
 */
@Configuration
public class PostureKafkaConfig {

    @Bean
    public NewTopic postureSummaryTopic(
            @Value("${app.kafka.topic.posture-summary:posture.summary}") String topicName) {
        return TopicBuilder.name(topicName)
                .partitions(1)
                .replicas(1)
                .build();
    }
}
