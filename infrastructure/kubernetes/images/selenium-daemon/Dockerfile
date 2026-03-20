# x86_64 variant for K8s workers
FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    chromium chromium-driver \
    fonts-noto-cjk \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY services/selenium-daemon/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/selenium-daemon/daemon/ ./daemon/

RUN mkdir -p /app/pdfs/yamato /app/pdfs/sagawa /app/cookies /app/logs /app/screenshots /app/state

ENV DISPLAY=:99

COPY infrastructure/kubernetes/images/selenium-daemon/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8020

ENTRYPOINT ["/app/entrypoint.sh"]
