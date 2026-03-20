#!/bin/bash
set -euo pipefail

DOMAIN="${INVENTREE_DOMAIN:?INVENTREE_DOMAIN must be set}"
PORTAL="${PORTAL_DOMAIN:-}"
EMAIL="${CERTBOT_EMAIL:-}"
DNS_MODE="${DNS_MODE:-production}"
CERT_DIR="/etc/letsencrypt/live/${DOMAIN}"

echo "=== Certbot entrypoint ==="
echo "Domain:   ${DOMAIN}"
echo "Portal:   ${PORTAL:-<not set>}"
echo "Email:    ${EMAIL:-<not set>}"
echo "DNS mode: ${DNS_MODE}"

# -------------------------------------------------------------------------
# 1. Create placeholder self-signed certificate (if none exists)
#    This lets nginx start immediately with HTTPS before the real cert
#    is obtained from Let's Encrypt.
# -------------------------------------------------------------------------
if [ ! -f "${CERT_DIR}/fullchain.pem" ]; then
    echo "Creating placeholder self-signed certificate..."
    mkdir -p "${CERT_DIR}"
    openssl req -x509 -nodes -days 1 \
        -newkey rsa:2048 \
        -keyout "${CERT_DIR}/privkey.pem" \
        -out "${CERT_DIR}/fullchain.pem" \
        -subj "/CN=${DOMAIN}" 2>/dev/null
    echo "Placeholder certificate created."
else
    echo "Certificate already exists at ${CERT_DIR}"
fi

# -------------------------------------------------------------------------
# 2. Mark ready — nginx depends on this via healthcheck
# -------------------------------------------------------------------------
touch /etc/letsencrypt/.ready
echo "Marked ready (nginx can start now)."

# -------------------------------------------------------------------------
# 3. Initial Route53 DNS update (A + AAAA)
# -------------------------------------------------------------------------
echo "Initial Route53 DNS update..."
python /usr/local/bin/route53-update.py --mode "${DNS_MODE}" "${DOMAIN}" || \
    echo "WARNING: Route53 update failed for ${DOMAIN} (continuing anyway)"
if [ -n "${PORTAL}" ]; then
    python /usr/local/bin/route53-update.py --mode "${DNS_MODE}" "${PORTAL}" || \
        echo "WARNING: Route53 update failed for ${PORTAL} (continuing anyway)"
fi

# -------------------------------------------------------------------------
# 4. Obtain real certificate from Let's Encrypt via DNS-01 challenge
# -------------------------------------------------------------------------
echo "Requesting certificate from Let's Encrypt..."
EMAIL_ARG=""
if [ -n "${EMAIL}" ]; then
    EMAIL_ARG="--email ${EMAIL}"
else
    EMAIL_ARG="--register-unsafely-without-email"
fi

# If the cert directory exists but has no valid certbot renewal config,
# it's our placeholder self-signed cert (or a failed attempt). Remove it
# so certbot can create a proper managed certificate.
RENEWAL_CONF="/etc/letsencrypt/renewal/${DOMAIN}.conf"
if [ -d "${CERT_DIR}" ] && [ ! -s "${RENEWAL_CONF}" ]; then
    echo "Placeholder cert detected (no valid renewal config). Cleaning up for certbot..."
    rm -rf "${CERT_DIR}"
    rm -f "${RENEWAL_CONF}"
fi

certbot certonly \
    --dns-route53 \
    --non-interactive \
    --agree-tos \
    ${EMAIL_ARG} \
    --domain "${DOMAIN}" \
    ${PORTAL:+--domain "${PORTAL}"} \
    --keep-until-expiring \
    --expand \
    || echo "WARNING: certbot certonly failed (will retry on next cycle)"

# -------------------------------------------------------------------------
# 5. Reload nginx to pick up the real certificate
# -------------------------------------------------------------------------
echo "Reloading nginx..."
/usr/local/bin/reload-nginx.sh || echo "WARNING: nginx reload failed"

# -------------------------------------------------------------------------
# 6. Background loop: update DNS every 5 minutes
# -------------------------------------------------------------------------
dns_update_loop() {
    while true; do
        sleep 300
        echo "=== DNS update $(date) ==="
        python /usr/local/bin/route53-update.py --mode "${DNS_MODE}" "${DOMAIN}" || \
            echo "WARNING: Route53 update failed for ${DOMAIN}"
        if [ -n "${PORTAL}" ]; then
            python /usr/local/bin/route53-update.py --mode "${DNS_MODE}" "${PORTAL}" || \
                echo "WARNING: Route53 update failed for ${PORTAL}"
        fi
    done
}

echo "Starting DNS update loop (every 5 minutes)..."
dns_update_loop &

# -------------------------------------------------------------------------
# 7. Foreground loop: renew certificate every 30 days
# -------------------------------------------------------------------------
echo "Entering certificate renewal loop (every 30 days)..."
while true; do
    sleep 30d

    echo "=== Certificate renewal cycle $(date) ==="

    # Renew certificate if needed; reload nginx on success
    certbot renew --deploy-hook "/usr/local/bin/reload-nginx.sh" || \
        echo "WARNING: certbot renew failed"
done
