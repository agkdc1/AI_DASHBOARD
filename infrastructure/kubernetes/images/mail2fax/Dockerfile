FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    postfix \
    python3 \
    python3-pip \
    python3-venv \
    curl \
    supervisor \
    libsasl2-modules \
    sasl2-bin \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --break-system-packages \
    requests pyyaml

WORKDIR /app

COPY services/fax/mail2fax/config/ /app/config/
COPY services/fax/mail2fax/config/smtpd.conf /etc/postfix/sasl/smtpd.conf
COPY services/fax/mail2fax/scripts/ /app/scripts/
COPY infrastructure/kubernetes/images/mail2fax/entrypoint.sh /app/entrypoint.sh

RUN chmod +x /app/entrypoint.sh /app/scripts/*.py /app/scripts/*.sh

EXPOSE 587

HEALTHCHECK --interval=60s --timeout=5s --retries=3 \
    CMD postfix status || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
