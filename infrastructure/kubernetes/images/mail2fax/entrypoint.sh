#!/bin/bash
set -e

# ---------------------------------------------------------------------------
# K8s mode: read config from environment variables (no config.yaml needed)
# ---------------------------------------------------------------------------
DOMAIN="${DOMAIN:-fax.your-domain.com}"
FAX_ENDPOINT="${FAX_ENDPOINT:-http://faxapi.fax-system.svc.cluster.local:8010/send_fax}"
FAX_API_KEY="${FAX_API_KEY:-}"
SMTP_AUTH_USER="${SMTP_AUTH_USER:-}"
SMTP_AUTH_PASS="${SMTP_AUTH_PASS:-}"
RELAY_HOST="${RELAY_HOST:-smtp.gmail.com}"
RELAY_PORT="${RELAY_PORT:-587}"
RELAY_USER="${RELAY_USER:-}"
RELAY_PASS="${RELAY_PASS:-}"

echo "=== Mail2Fax Gateway Starting ==="
echo "Domain: $DOMAIN"
echo "Fax endpoint: $FAX_ENDPOINT"

# ---------------------------------------------------------------------------
# Step 1: Skip certbot (cert-manager handles TLS in K8s)
# ---------------------------------------------------------------------------
if [ "${SKIP_CERTBOT:-0}" = "1" ]; then
    echo "--- Skipping certbot (cert-manager manages TLS) ---"
else
    echo "--- Obtaining TLS certificate ---"
    CERTBOT_EMAIL="${CERTBOT_EMAIL:-admin@your-domain.com}"
    certbot certonly \
        --non-interactive \
        --agree-tos \
        --email "$CERTBOT_EMAIL" \
        --dns-route53 \
        -d "$DOMAIN" \
        --keep-until-expiring \
        || echo "WARNING: certbot failed, TLS may not work"
fi

CERT_DIR="${CERT_DIR:-/etc/letsencrypt/live/$DOMAIN}"

# ---------------------------------------------------------------------------
# Step 2: Generate Postfix config from templates
# ---------------------------------------------------------------------------
echo "--- Configuring Postfix ---"

sed \
    -e "s|{{DOMAIN}}|$DOMAIN|g" \
    -e "s|{{CERT_DIR}}|$CERT_DIR|g" \
    -e "s|{{RELAY_HOST}}|$RELAY_HOST|g" \
    -e "s|{{RELAY_PORT}}|$RELAY_PORT|g" \
    /app/config/main.cf.template > /etc/postfix/main.cf

# Step 2a: Set up outbound relay credentials
if [ -n "$RELAY_HOST" ] && [ -n "$RELAY_USER" ]; then
    echo "--- Configuring outbound relay ---"
    echo "[$RELAY_HOST]:$RELAY_PORT $RELAY_USER:$RELAY_PASS" > /etc/postfix/sasl_passwd
    postmap /etc/postfix/sasl_passwd
    chmod 0600 /etc/postfix/sasl_passwd /etc/postfix/sasl_passwd.db
    echo "Outbound relay: [$RELAY_HOST]:$RELAY_PORT"
fi

sed \
    -e "s|{{DOMAIN}}|$DOMAIN|g" \
    /app/config/master.cf.template > /etc/postfix/master.cf

# Step 2b: Set up SASL authentication
if [ -n "$SMTP_AUTH_USER" ] && [ -n "$SMTP_AUTH_PASS" ]; then
    echo "--- Configuring SMTP authentication ---"
    echo "$SMTP_AUTH_PASS" | saslpasswd2 -p -c -u "$DOMAIN" "$SMTP_AUTH_USER"
    chown postfix /etc/sasldb2
    echo "SASL user $SMTP_AUTH_USER@$DOMAIN created"
else
    echo "WARNING: smtp_auth credentials not set, SASL authentication disabled"
fi

# ---------------------------------------------------------------------------
# Step 3: Create virtual mailbox map (accept all @fax)
# ---------------------------------------------------------------------------
echo "fax    anything" > /etc/postfix/virtual_domains
postmap /etc/postfix/virtual_domains

# ---------------------------------------------------------------------------
# Step 4: Write runtime config for email_processor.py
# ---------------------------------------------------------------------------
cat > /app/config.yaml << EOF
domain: "$DOMAIN"
fax_api:
  endpoint: "$FAX_ENDPOINT"
  api_key: "$FAX_API_KEY"
EOF

# Ensure mail spool directory exists
mkdir -p /var/spool/postfix/pid
mkdir -p /var/mail

# ---------------------------------------------------------------------------
# Step 5: Start services via supervisord
# ---------------------------------------------------------------------------
echo "--- Starting services ---"

cat > /etc/supervisor/conf.d/mail2fax.conf << 'EOF'
[supervisord]
nodaemon=true
logfile=/var/log/supervisord.log

[program:postfix]
command=/usr/sbin/postfix start-fg
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
EOF

exec /usr/bin/supervisord -c /etc/supervisor/conf.d/mail2fax.conf
