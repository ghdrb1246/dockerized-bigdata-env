package com.posture.api.posture.cep;

import java.util.Optional;

/**
 * 상태머신 상태의 외부 저장소 (D-04, PRD FR-BE-04).
 *
 * api-server가 재시작돼도 진행 중이던 판정(붕괴 후보·진행 중 이벤트·회복
 * 대기)을 이어갈 수 있도록 세션 상태를 프로세스 밖에 보관한다. 운영 구현은
 * {@link RedisCepStateStore}(키 {@code posture:state:{userId}})이고, 단위
 * 테스트는 {@link #NO_OP} 또는 메모리 구현을 쓴다.
 *
 * 구현체는 예외를 밖으로 던지지 않는다 — 저장소가 죽어도 판정 흐름은
 * 멈추지 않고 인메모리 상태만으로 계속 돈다.
 */
public interface CepStateStore {

    Optional<PersistedSessionState> load(String key);

    void save(String key, PersistedSessionState state);

    void delete(String key);

    /** 저장소를 쓰지 않는 구현 (기존 동작과 동일 — 상태는 메모리에만). */
    CepStateStore NO_OP = new CepStateStore() {
        @Override
        public Optional<PersistedSessionState> load(String key) {
            return Optional.empty();
        }

        @Override
        public void save(String key, PersistedSessionState state) {
        }

        @Override
        public void delete(String key) {
        }
    };
}
