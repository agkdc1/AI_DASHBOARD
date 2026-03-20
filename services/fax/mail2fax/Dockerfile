FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    postfix \
    python3 \
    python3-pip \
    python3-venv \
    certbot \
    python3-certbot-dns-route53 \
    curl \
    cron \
    supervisor \
    libsasl2-modules \
    sasl2-bin \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --break-system-packages \
    boto3 requests pyyaml

WORKDIR /app

COPY config/ /app/config/
COPY config/smtpd.conf /etc/postfix/sasl/smtpd.conf
COPY scripts/ /app/scripts/
COPY entrypoint.sh /app/entrypoint.sh

RUN chmod +x /app/entrypoint.sh /app/scripts/*.py /app/scripts/*.sh

# Cron job for monthly cert renewal
RUN echo "0 3 1 * * /app/scripts/cert_renewer.sh >> /var/log/certbot.log 2>&1" \
    | crontab -

EXPOSE 587

HEALTHCHECK --interval=60s --timeout=5s --retries=3 \
    CMD postfix status || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
