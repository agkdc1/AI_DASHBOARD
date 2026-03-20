FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    chromium chromium-driver \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY agent/ ./agent/

ENV DISPLAY=:99
ENV VAULT_ADDR=http://host.docker.internal:8200

ENTRYPOINT ["python", "-m", "agent.main"]
