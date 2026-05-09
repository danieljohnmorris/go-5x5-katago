FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates unzip libzip4 \
    && rm -rf /var/lib/apt/lists/*

# Download KataGo eigenavx2 (CPU) prebuilt binary.
ARG KATAGO_VERSION=1.16.4
RUN curl -L -o /tmp/katago.zip \
      "https://github.com/lightvector/KataGo/releases/download/v${KATAGO_VERSION}/katago-v${KATAGO_VERSION}-eigenavx2-linux-x64.zip" \
    && unzip -o /tmp/katago.zip -d /tmp/katago \
    && install -m 0755 /tmp/katago/katago /usr/local/bin/katago \
    && rm -rf /tmp/katago /tmp/katago.zip

WORKDIR /app
COPY requirements.txt /app/
RUN pip install -r requirements.txt

COPY analysis.cfg /app/analysis.cfg
COPY katago-network.bin.gz /app/network.bin.gz
COPY server.py /app/server.py

ENV KATAGO_BIN=/usr/local/bin/katago \
    KATAGO_MODEL=/app/network.bin.gz \
    KATAGO_CONFIG=/app/analysis.cfg \
    PORT=8000

EXPOSE 8000
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
