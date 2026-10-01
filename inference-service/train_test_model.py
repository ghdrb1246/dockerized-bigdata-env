"""
테스트용 LSTM 모델 학습 스크립트 (합성 예시 키포인트 데이터 사용).

실제 자세 데이터가 아직 없으므로, deviationScore/ruleStatus의 규칙
기반 골격(consumer.infer_rule_based)과 같은 직관으로 3개 클래스
(NORMAL/WARNING/BAD)를 구분할 수 있는 합성 시계열 데이터를 만들어
학습한다. 목적은 정확도가 아니라 "LSTM 모델을 실제로 학습·저장·
로드·추론하는 전체 경로가 하드웨어/빅데이터 플랫폼(Docker 컨테이너
자원, inference-service 파이프라인)에서 문제없이 도는지" 검증하는
것이다 — 실제 자세 데이터가 준비되면 build_dataset()만 실제 데이터
로더로 교체하면 된다.

사용법:
    cd inference-service
    pip install -r requirements.txt
    python train_test_model.py

app/models/test_lstm.pt(가중치)와 app/models/test_lstm.meta.json
(모델 구조 메타데이터)를 생성/덮어쓴다. 이 두 파일이 있어야
inference-service가 기동 시 모델을 로드해 실제 LSTM 추론을 쓴다 —
없으면 자동으로 규칙 기반(infer_rule_based)으로 폴백한다.
"""
import json
import random

import torch
import torch.nn as nn
import torch.optim as optim

from app.model import CLASS_NAMES, MODEL_DIR, MODEL_META_PATH, MODEL_WEIGHTS_PATH, build_model

# api-server 수집 API curl 예시(featureVector: [0.12, -0.03, 0.41])와
# 같은 길이로 맞췄다 — 실제 키포인트 수가 정해지면 이 값과
# app/model.py의 패딩/절단 로직을 함께 재검토해야 한다.
FEATURE_VECTOR_SIZE = 3
WINDOW_SIZE = 10          # 세션당 연속 이벤트 10개를 모아 한 번 추론 (consumer.py와 맞춰야 함)
HIDDEN_SIZE = 16
NUM_LAYERS = 1
SAMPLES_PER_CLASS = 300
EPOCHS = 30
SEED = 42


def make_sequence(base_noise: float, drift: float) -> list:
    """
    base_noise: 평상시 미세한 흔들림 크기.
    drift: 자세가 시간이 지날수록 무너지는 정도(시퀀스 끝으로 갈수록 커짐).
    NORMAL은 drift가 거의 없고, BAD는 drift가 크고 지속적으로 커진다 —
    api-server의 deviationScore 임계값(0.4/0.7)과 같은 직관을 시계열
    형태로 옮긴 합성 데이터다.
    """
    seq = []
    value = [0.0] * FEATURE_VECTOR_SIZE
    for t in range(WINDOW_SIZE):
        value = [
            v + random.uniform(-base_noise, base_noise) + drift * (t / WINDOW_SIZE)
            for v in value
        ]
        seq.append(value)
    return seq


def build_dataset():
    random.seed(SEED)
    sequences, labels = [], []

    for _ in range(SAMPLES_PER_CLASS):
        sequences.append(make_sequence(base_noise=0.02, drift=0.0))    # NORMAL
        labels.append(CLASS_NAMES.index("NORMAL"))

        sequences.append(make_sequence(base_noise=0.05, drift=0.15))   # WARNING
        labels.append(CLASS_NAMES.index("WARNING"))

        sequences.append(make_sequence(base_noise=0.08, drift=0.4))    # BAD
        labels.append(CLASS_NAMES.index("BAD"))

    return (
        torch.tensor(sequences, dtype=torch.float32),
        torch.tensor(labels, dtype=torch.long),
    )


def main():
    torch.manual_seed(SEED)

    X, y = build_dataset()
    model = build_model(
        nn,
        input_size=FEATURE_VECTOR_SIZE,
        hidden_size=HIDDEN_SIZE,
        num_layers=NUM_LAYERS,
        num_classes=len(CLASS_NAMES),
    )

    optimizer = optim.Adam(model.parameters(), lr=0.01)
    criterion = nn.CrossEntropyLoss()

    model.train()
    for epoch in range(1, EPOCHS + 1):
        optimizer.zero_grad()
        logits = model(X)
        loss = criterion(logits, y)
        loss.backward()
        optimizer.step()

        if epoch == 1 or epoch % 5 == 0 or epoch == EPOCHS:
            with torch.no_grad():
                accuracy = (logits.argmax(dim=-1) == y).float().mean().item()
            print(f"epoch {epoch:>3}/{EPOCHS}  loss={loss.item():.4f}  train_acc={accuracy:.3f}")

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), MODEL_WEIGHTS_PATH)
    with open(MODEL_META_PATH, "w") as f:
        json.dump(
            {
                "input_size": FEATURE_VECTOR_SIZE,
                "hidden_size": HIDDEN_SIZE,
                "num_layers": NUM_LAYERS,
                "window_size": WINDOW_SIZE,
                "class_names": CLASS_NAMES,
                "note": "합성 예시 데이터로 학습한 테스트 모델 — 실제 자세 데이터 아님",
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(f"저장 완료: {MODEL_WEIGHTS_PATH}, {MODEL_META_PATH}")


if __name__ == "__main__":
    main()
