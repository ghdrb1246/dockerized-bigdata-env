FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
# --extra-index-url로 PyPI에 더해 PyTorch 공식 CPU wheel 저장소도
# 함께 찾게 한다. 이 VM/컨테이너에는 GPU가 없으므로 pip이 기본으로
# 고르는 CUDA 포함 wheel(수백MB~수GB) 대신 CPU 전용 wheel(훨씬
# 작음)을 쓰게 하기 위함이다 — torch 외 나머지 패키지는 그대로 PyPI에서
# 받는다. (사내/VM 네트워크가 download.pytorch.org를 막고 있다면 이
# 줄을 지우고 기본 PyPI wheel을 쓰면 된다 — 용량만 더 클 뿐 동작은
# 동일하다.)
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu \
    -r requirements.txt

COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
