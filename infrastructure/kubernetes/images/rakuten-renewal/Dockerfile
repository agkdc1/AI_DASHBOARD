# x86_64 variant for K8s workers
FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    chromium chromium-driver \
    fonts-noto-cjk \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY services/rakuten-renewal/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/rakuten-renewal/agent/ ./agent/

RUN mkdir -p /app/logs /app/screenshots /app/state

ENV DISPLAY=:99

COPY infrastructure/kubernetes/images/rakuten-renewal/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
