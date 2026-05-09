FROM debian:bookworm-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential cmake git zlib1g-dev libzip-dev libeigen3-dev ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ARG KATAGO_VERSION=v1.16.4
RUN git clone --depth 1 --branch ${KATAGO_VERSION} https://github.com/lightvector/KataGo.git /src

WORKDIR /src/cpp
RUN cmake . -DUSE_BACKEND=EIGEN -DBUILD_DISTRIBUTED=0 -DUSE_AVX2=0 \
    && make -j$(nproc)


FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
      libzip4 zlib1g \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /src/cpp/katago /usr/local/bin/katago
RUN /usr/local/bin/katago version | head -3

WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY analysis.cfg /app/analysis.cfg
COPY katago-network.bin.gz /app/network.bin.gz
COPY server.py /app/server.py

ENV KATAGO_BIN=/usr/local/bin/katago \
    KATAGO_MODEL=/app/network.bin.gz \
    KATAGO_CONFIG=/app/analysis.cfg

EXPOSE 8000
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
