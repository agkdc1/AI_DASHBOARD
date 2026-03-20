#!/bin/bash
set -e

CONFIG=/app/config.yaml

if [ ! -f "$CONFIG" ]; then
    echo "ERROR: config.yaml not found. Copy config.yaml.sample and edit it."
    exit 1
fi

# Parse config values with Python (outputs shell-safe VAR=value lines)
eval "$(python3 -c "
import yaml, shlex
with open('$CONFIG') as f:
    c = yaml.safe_load(f)
print(f'DOMAIN={shlex.quote(str(c[\"domain\"]))}')
print(f'HOSTED_ZONE_ID={shlex.quote(str(c.get(\"aws\",{}).get(\"hosted_zone_id\",\"\")))}')
print(f'FAX_ENDPOINT={shlex.quote(str(c.get(\"fax_api\",{}).get(\"endpoint\",\"\")))}')
print(f'FAX_API_KEY={shlex.quote(str(c.get(\"fax_api\",{}).get(\"api_key\",\"\")))}')
print(f'CERTBOT_EMAIL={shlex.quote(str(c.get(\"certbot\",{}).get(\"email\",\"\")))}')
print(f'SMTP_AUTH_USER={shlex.quote(str(c.get(\"smtp_auth\",{}).get(\"username\",\"\")))}')
print(f'SMTP_AUTH_PASS={shlex.quote(str(c.get(\"smtp_auth\",{}).get(\"password\",\"\")))}')
print(f'RELAY_HOST={shlex.quote(str(c.get(\"smtp_relay\",{}).get(\"host\",\"smtp.gmail.com\")))}')
print(f'RELAY_PORT={shlex.quote(str(c.get(\"smtp_relay\",{}).get(\"port\",\"587\")))}')
print(f'RELAY_USER={shlex.quote(str(c.get(\"smtp_relay\",{}).get(\"username\",\"\")))}')
print(f'RELAY_PASS={shlex.quote(str(c.get(\"smtp_relay\",{}).get(\"password\",\"\")))}')
")"

echo "=== Mail2Fax Gateway Starting ==="
echo "Domain: $DOMAIN"

# Step 1: Update DNS (Route53 A + MX records)
echo "--- Updating DNS records ---"
python3 /app/scripts/dns_updater.py "$CONFIG" || echo "WARNING: DNS update failed, continuing..."

# Step 2: Obtain/renew TLS certificate
echo "--- Obtaining TLS certificate ---"
certbot certonly \
    --non-interactive \
    --agree-tos \
    --email "$CERTBOT_EMAIL" \
    --dns-route53 \
    -d "$DOMAIN" \
    --keep-until-expiring \
    || echo "WARNING: certbot failed, TLS may not work"

CERT_DIR="/etc/letsencrypt/live/$DOMAIN"

# Step 3: Generate Postfix config from templates
echo "--- Configuring Postfix ---"

sed \
    -e "s|{{DOMAIN}}|$DOMAIN|g" \
    -e "s|{{CERT_DIR}}|$CERT_DIR|g" \
    -e "s|{{RELAY_HOST}}|$RELAY_HOST|g" \
    -e "s|{{RELAY_PORT}}|$RELAY_PORT|g" \
    /app/config/main.cf.template > /etc/postfix/main.cf

# Step 3a: Set up outbound relay credentials
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

# Step 3b: Set up SASL authentication
if [ -n "$SMTP_AUTH_USER" ] && [ -n "$SMTP_AUTH_PASS" ]; then
    echo "--- Configuring SMTP authentication ---"
    echo "$SMTP_AUTH_PASS" | saslpasswd2 -p -c -u "$DOMAIN" "$SMTP_AUTH_USER"
    chown postfix /etc/sasldb2
    echo "SASL user $SMTP_AUTH_USER@$DOMAIN created"
else
    echo "WARNING: smtp_auth credentials not set, SASL authentication disabled"
fi

# Step 4: Create virtual mailbox map (accept all @fax)
echo "fax    anything" > /etc/postfix/virtual_domains
postmap /etc/postfix/virtual_domains

# Ensure mail spool directory exists
mkdir -p /var/spool/postfix/pid
mkdir -p /var/mail

# Step 6: Start services via supervisord
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

[program:cron]
command=/usr/sbin/cron -f
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
EOF

exec /usr/bin/supervisord -c /etc/supervisor/conf.d/mail2fax.conf
