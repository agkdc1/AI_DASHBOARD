#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# deploy.sh — Generate a complete Docker deployment for InvenTree
#
# Architecture:
#   Nginx (port 80→301, port 443 TLS) → uWSGI unix socket → InvenTree Django app
#   InvenTree → MySQL unix socket → MySQL 8.0
#   InvenTree Worker → MySQL unix socket → MySQL 8.0
#   Certbot → Route53 DNS-01 challenge → Let's Encrypt certificates
#
# All inter-container communication uses Unix sockets via shared named volumes.
# MySQL password is managed via Docker secrets (never in .env or config.yaml).
# TLS certificates are managed by a dedicated certbot container.
#
# Usage:
#   chmod +x deploy.sh && ./deploy.sh
#   cd shinbee-deploy && docker compose up -d
# =============================================================================

DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)/shinbee-deploy"

echo "Generating deployment files in: ${DEPLOY_DIR}"
mkdir -p "${DEPLOY_DIR}/secrets"

# =============================================================================
# secrets/mysql_password — auto-generated 32-char random password
# =============================================================================
if [ ! -f "${DEPLOY_DIR}/secrets/mysql_password" ]; then
    python3 -c "import secrets; print(secrets.token_urlsafe(24), end='')" > "${DEPLOY_DIR}/secrets/mysql_password"
    chmod 600 "${DEPLOY_DIR}/secrets/mysql_password"
    echo "Generated new MySQL password in secrets/mysql_password"
else
    echo "Keeping existing secrets/mysql_password"
fi

# =============================================================================
# .env — image tag, site URL, ports, domain (no passwords)
# =============================================================================
cat > "${DEPLOY_DIR}/.env" << 'DOTENV'
# InvenTree deployment configuration
# Passwords are managed via Docker secrets — not stored here.

INVENTREE_TAG=stable

# Domain name (used by nginx + certbot)
INVENTREE_DOMAIN=api.your-domain.com

# Certbot notification email
CERTBOT_EMAIL=admin@your-domain.com

# DNS mode: "production" = external IPs (A + AAAA), "test" = internal IPv4 only
DNS_MODE=production

# Route53 hosted zone ID (skips auto-detection if set)
ROUTE53_ZONE_ID=YOUR_ZONE_ID

# Site URL (used by Django's ALLOWED_HOSTS / CSRF)
INVENTREE_SITE_URL=https://api.your-domain.com

# Exposed ports on the host
INVENTREE_WEB_PORT=80
INVENTREE_HTTPS_PORT=443

# Database name and user
INVENTREE_DB_ENGINE=mysql
INVENTREE_DB_NAME=inventree
INVENTREE_DB_USER=inventree

# Background workers
INVENTREE_BACKGROUND_WORKERS=4

# Debug mode (set to True for development only)
INVENTREE_DEBUG=False

# Plugins (enabled for future ecommerce integration)
INVENTREE_PLUGINS_ENABLED=true
INVENTREE_PLUGIN_DIR=/home/inventree/plugins

# Google OAuth2 — enable Google as a social auth backend
# Provider config (including hd domain restriction) is in config.yaml.
INVENTREE_SOCIAL_BACKENDS=google
DOTENV
echo "  Created .env"

# =============================================================================
# config.yaml — Django DB config with OPTIONS.unix_socket
# =============================================================================
cat > "${DEPLOY_DIR}/config.yaml" << 'CONFIG'
# InvenTree configuration file (provisioned by deploy.sh)
# PASSWORD is intentionally omitted — injected via Docker secret / env var.
# HOST is empty string so Django uses the unix_socket option.

database:
  ENGINE: mysql
  NAME: inventree
  USER: inventree
  HOST: ''
  PORT: ''
  OPTIONS:
    unix_socket: /var/run/mysqld/mysqld.sock
    charset: utf8mb4
    init_command: "SET sql_mode='STRICT_TRANS_TABLES'"

# Plugins (enabled for future ecommerce integration)
plugins_enabled: true
plugin_dir: /home/inventree/plugins

# Google OAuth2 — domain-restricted login via "hd" parameter.
# The "hd" param restricts Google's account picker to @your-domain.com.
# For server-side enforcement, also set LOGIN_SIGNUP_MAIL_RESTRICTION
# to "@your-domain.com" in InvenTree Admin → Settings.
social_providers:
  google:
    SCOPE:
      - profile
      - email
    AUTH_PARAMS:
      access_type: online
      hd: your-domain.com
    APP:
      client_id: REPLACE_WITH_GOOGLE_CLIENT_ID
      secret: REPLACE_WITH_GOOGLE_CLIENT_SECRET
CONFIG
echo "  Created config.yaml"

# =============================================================================
# uwsgi.ini — uWSGI configuration
# =============================================================================
cat > "${DEPLOY_DIR}/uwsgi.ini" << 'UWSGI'
[uwsgi]
# WSGI application
module = InvenTree.wsgi:application
chdir = /home/inventree/src/backend/InvenTree

# Unix socket (shared with Nginx via named volume)
socket = /var/run/uwsgi/inventree.sock
chmod-socket = 666
vacuum = true

# Process management
master = true
processes = 4
threads = 2
enable-threads = true

# Large buffer for InvenTree auth headers
buffer-size = 65535

# Request timeout (seconds)
harakiri = 120

# Graceful shutdown
die-on-term = true

# Worker recycling
max-requests = 1000

# Logging
logto = /dev/stderr
UWSGI
echo "  Created uwsgi.ini"

# =============================================================================
# nginx.conf.template — Nginx reverse proxy with HTTPS + envsubst
# =============================================================================
cat > "${DEPLOY_DIR}/nginx.conf.template" << 'NGINXTEMPLATE'
upstream inventree {
    server unix:///var/run/uwsgi/inventree.sock;
}

# HTTP — redirect everything to HTTPS
server {
    listen 80;
    server_name ${INVENTREE_DOMAIN};

    return 301 https://$host$request_uri;
}

# HTTPS — TLS termination + reverse proxy
server {
    listen 443 ssl;
    server_name ${INVENTREE_DOMAIN};

    # TLS certificates (managed by certbot container)
    ssl_certificate     /etc/letsencrypt/live/${INVENTREE_DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${INVENTREE_DOMAIN}/privkey.pem;

    # Modern TLS settings
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305;
    ssl_prefer_server_ciphers off;

    # HSTS (1 year)
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # SSL session caching
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;

    client_max_body_size 100M;

    # Static files — served directly by Nginx
    location /static/ {
        alias /home/inventree/data/static/;
        expires 30d;
        access_log off;
        add_header Cache-Control "public, immutable";
    }

    # Media files — require authentication via InvenTree
    location /media/ {
        alias /home/inventree/data/media/;
        # Subrequest to InvenTree for auth check
        auth_request /auth;
    }

    # Internal auth endpoint — proxied to InvenTree via uWSGI
    location = /auth {
        internal;
        uwsgi_pass inventree;
        include uwsgi_params;

        uwsgi_pass_request_body off;
        uwsgi_param CONTENT_LENGTH "";

        # Forward original request info
        uwsgi_param X-Original-URI $request_uri;
        uwsgi_param X-Forwarded-Host $host;
    }

    # All other requests — proxy to InvenTree via uWSGI
    location / {
        uwsgi_pass inventree;
        include uwsgi_params;

        uwsgi_param Host $host;
        uwsgi_param X-Real-IP $remote_addr;
        uwsgi_param X-Forwarded-For $proxy_add_x_forwarded_for;
        uwsgi_param X-Forwarded-Proto $scheme;
    }
}
NGINXTEMPLATE
echo "  Created nginx.conf.template"

# =============================================================================
# init-wrapper.sh — reads Docker secret, runs migrations, starts server/worker
# =============================================================================
cat > "${DEPLOY_DIR}/init-wrapper.sh" << 'WRAPPER'
#!/bin/bash
set -e

# Read MySQL password from Docker secret and export as env var.
# This is the only place the password is read — it never appears in
# config.yaml or .env files.
if [ -f /run/secrets/mysql_password ]; then
    export INVENTREE_DB_PASSWORD="$(cat /run/secrets/mysql_password)"
else
    echo "WARNING: /run/secrets/mysql_password not found"
fi

# Copy config.yaml into the data volume on first run
if [ ! -f "${INVENTREE_CONFIG_FILE}" ]; then
    echo "First run: copying config.yaml.default → ${INVENTREE_CONFIG_FILE}"
    cp /home/inventree/config.yaml.default "${INVENTREE_CONFIG_FILE}"
fi

# ---------- Replicate essential init.sh setup ----------
# (We cannot source init.sh because it ends with exec "$@")

if command -v git &> /dev/null; then
    git config --global --add safe.directory /home/inventree 2>/dev/null || true
fi

mkdir -p "${INVENTREE_STATIC_ROOT}" "${INVENTREE_MEDIA_ROOT}" "${INVENTREE_BACKUP_DIR}"

if [ -f "${INVENTREE_CONFIG_FILE}" ]; then
    echo "Loading config file : ${INVENTREE_CONFIG_FILE}"
fi

# Activate Python venv if configured
if [[ -n "${INVENTREE_PY_ENV}" ]] && [[ -d "${INVENTREE_PY_ENV}" ]]; then
    echo "Using Python virtual environment: ${INVENTREE_PY_ENV}"
    source "${INVENTREE_PY_ENV}/bin/activate"
fi

cd "${INVENTREE_HOME}"

# ---------- Run database migrations + collect static ----------
# Only the server should run migrations/static. The worker (invoke worker)
# skips these to avoid MySQL lock contention on simultaneous startup.
if [ "$1" != "invoke" ]; then
    echo "Running database migrations..."
    invoke migrate
    echo "Collecting static files..."
    invoke static
fi

# Start the requested command (uWSGI for server, invoke worker for worker)
exec "$@"
WRAPPER
chmod +x "${DEPLOY_DIR}/init-wrapper.sh"
echo "  Created init-wrapper.sh"

# =============================================================================
# Dockerfile — extends inventree/inventree:stable, adds uWSGI
# =============================================================================
cat > "${DEPLOY_DIR}/Dockerfile" << 'DOCKERFILE'
ARG INVENTREE_TAG=stable
FROM inventree/inventree:${INVENTREE_TAG}

# Install uWSGI (requires compilation)
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc python3-dev \
    && pip install --no-cache-dir uwsgi \
    && apt-get purge -y gcc python3-dev \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create socket directories
RUN mkdir -p /var/run/uwsgi /var/run/mysqld

# Copy deployment config files
COPY uwsgi.ini /home/inventree/uwsgi.ini
COPY config.yaml /home/inventree/config.yaml.default
COPY init-wrapper.sh /home/inventree/init-wrapper.sh
RUN chmod +x /home/inventree/init-wrapper.sh

# Override entrypoint to use our wrapper (which reads Docker secrets)
ENTRYPOINT ["/bin/bash", "/home/inventree/init-wrapper.sh"]

# Default command: start uWSGI
CMD ["uwsgi", "--ini", "/home/inventree/uwsgi.ini"]
DOCKERFILE
echo "  Created Dockerfile"

# =============================================================================
# Dockerfile.certbot — certbot with Route53 DNS plugin + helper scripts
# =============================================================================
cat > "${DEPLOY_DIR}/Dockerfile.certbot" << 'CERTBOTDOCKERFILE'
FROM certbot/dns-route53:latest

# Install curl (for Docker API + public IP check), jq (for JSON parsing), bash
RUN apk add --no-cache curl jq bash

# Copy scripts
COPY certbot-entrypoint.sh /usr/local/bin/certbot-entrypoint.sh
COPY route53-update.py /usr/local/bin/route53-update.py
COPY reload-nginx.sh /usr/local/bin/reload-nginx.sh
RUN chmod +x /usr/local/bin/certbot-entrypoint.sh \
             /usr/local/bin/route53-update.py \
             /usr/local/bin/reload-nginx.sh

ENTRYPOINT ["/bin/bash", "/usr/local/bin/certbot-entrypoint.sh"]
CERTBOTDOCKERFILE
echo "  Created Dockerfile.certbot"

# =============================================================================
# certbot-entrypoint.sh — placeholder cert, real cert, renewal loop
# =============================================================================
cat > "${DEPLOY_DIR}/certbot-entrypoint.sh" << 'CERTBOTENTRY'
#!/bin/bash
set -euo pipefail

DOMAIN="${INVENTREE_DOMAIN:?INVENTREE_DOMAIN must be set}"
EMAIL="${CERTBOT_EMAIL:-}"
DNS_MODE="${DNS_MODE:-production}"
CERT_DIR="/etc/letsencrypt/live/${DOMAIN}"

echo "=== Certbot entrypoint ==="
echo "Domain:   ${DOMAIN}"
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
    echo "WARNING: Route53 update failed (continuing anyway)"

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
    --keep-until-expiring \
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
            echo "WARNING: Route53 update failed"
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
CERTBOTENTRY
chmod +x "${DEPLOY_DIR}/certbot-entrypoint.sh"
echo "  Created certbot-entrypoint.sh"

# =============================================================================
# route53-update.py — update Route53 A/AAAA records with current IP
# =============================================================================
cat > "${DEPLOY_DIR}/route53-update.py" << 'ROUTE53'
#!/usr/bin/env python3
"""Update Route53 A and AAAA records with the host's current IP.

Usage: python route53-update.py [--mode production|test] [--zone-id ID] <domain>

  production (default): A = external IPv4, AAAA = external IPv6 (if available)
  test:                 A = internal/private IPv4, no AAAA

Auto-detects the Route53 hosted zone ID from the domain name.
Set ROUTE53_ZONE_ID env var or --zone-id to skip auto-detection.
Requires AWS credentials (via ~/.aws, env vars, or IAM role).
"""
import argparse
import os
import socket
import sys
import urllib.request

import boto3


def get_public_ipv4():
    """Get public IPv4 from AWS checkip service."""
    resp = urllib.request.urlopen("https://checkip.amazonaws.com", timeout=10)
    return resp.read().decode().strip()


def get_public_ipv6():
    """Get public IPv6 address. Returns None if unavailable."""
    try:
        resp = urllib.request.urlopen("https://api6.ipify.org", timeout=10)
        addr = resp.read().decode().strip()
        # Sanity-check: must contain a colon (IPv6)
        if ":" in addr:
            return addr
        return None
    except Exception:
        return None


def get_internal_ipv4():
    """Get the host's internal/private IPv4 address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


def find_hosted_zone(client, domain):
    """Find the Route53 hosted zone ID for the given domain.

    Walks up the domain hierarchy to find the matching zone.
    e.g. for 'api.your-domain.com', tries:
      - api.your-domain.com.
      - your-domain.com.

    Uses list_hosted_zones (paginated) instead of list_hosted_zones_by_name
    to avoid needing the route53:ListHostedZonesByName permission.
    """
    # Build all candidate zone names (most specific first)
    parts = domain.split(".")
    candidates = set()
    for i in range(len(parts) - 1):
        candidates.add(".".join(parts[i:]) + ".")

    # Paginate through all hosted zones
    paginator = client.get_paginator("list_hosted_zones")
    for page in paginator.paginate():
        for zone in page["HostedZones"]:
            if zone["Name"] in candidates:
                zone_id = zone["Id"].split("/")[-1]
                print(f"Found hosted zone: {zone['Name']} -> {zone_id}")
                return zone_id
    return None


def resolve_cname(domain):
    """Resolve CNAME target for a domain via DNS query. Returns target or None."""
    import re
    import subprocess
    # nslookup is available on Alpine (busybox)
    try:
        result = subprocess.run(
            ["nslookup", "-type=cname", domain],
            capture_output=True, text=True, timeout=10
        )
        # Parse "api.your-domain.com  canonical name = target.example.com."
        for line in result.stdout.splitlines():
            m = re.search(r"canonical name\s*=\s*(\S+?)\.?$", line, re.IGNORECASE)
            if m:
                target = m.group(1)
                if not target.endswith("."):
                    target += "."
                return target
    except Exception:
        pass
    return None


def delete_and_create_record(client, zone_id, domain, cname_target, record_type, value, ttl=300):
    """Delete a conflicting CNAME and create the desired record in one batch."""
    print(f"Attempting to delete CNAME ({cname_target}) and create {record_type} record...")
    # Try common TTL values since we can't query the exact TTL
    for try_ttl in [300, 60, 3600, 86400, 900, 600, 120, 1800, 7200, 43200]:
        try:
            client.change_resource_record_sets(
                HostedZoneId=zone_id,
                ChangeBatch={
                    "Comment": f"Replace CNAME with {record_type} for dynamic DNS",
                    "Changes": [
                        {
                            "Action": "DELETE",
                            "ResourceRecordSet": {
                                "Name": domain,
                                "Type": "CNAME",
                                "TTL": try_ttl,
                                "ResourceRecords": [{"Value": cname_target}],
                            },
                        },
                        {
                            "Action": "CREATE",
                            "ResourceRecordSet": {
                                "Name": domain,
                                "Type": record_type,
                                "TTL": ttl,
                                "ResourceRecords": [{"Value": value}],
                            },
                        },
                    ],
                },
            )
            print(f"CNAME deleted (TTL was {try_ttl}), {record_type} record created.")
            return
        except client.exceptions.InvalidChangeBatch:
            continue
    raise RuntimeError(
        f"Could not delete CNAME for {domain}. "
        f"Please delete it manually in the AWS Route53 console."
    )


def upsert_record(client, zone_id, domain, record_type, value, ttl=300):
    """UPSERT a single DNS record. Handles CNAME conflicts automatically."""
    try:
        client.change_resource_record_sets(
            HostedZoneId=zone_id,
            ChangeBatch={
                "Comment": f"Auto-update {record_type} from certbot container",
                "Changes": [
                    {
                        "Action": "UPSERT",
                        "ResourceRecordSet": {
                            "Name": domain,
                            "Type": record_type,
                            "TTL": ttl,
                            "ResourceRecords": [{"Value": value}],
                        },
                    }
                ],
            },
        )
    except client.exceptions.InvalidChangeBatch as e:
        if "CNAME" in str(e):
            cname_target = resolve_cname(domain)
            if cname_target:
                print(f"CNAME conflict detected (target: {cname_target}). Replacing...")
                delete_and_create_record(
                    client, zone_id, domain, cname_target,
                    record_type, value, ttl
                )
            else:
                print(f"CNAME conflict but could not resolve target. "
                      f"Delete the CNAME manually in Route53.", file=sys.stderr)
                raise
        else:
            raise


def main():
    parser = argparse.ArgumentParser(description="Update Route53 DNS records")
    parser.add_argument("domain", help="Domain name to update")
    parser.add_argument(
        "--mode",
        choices=["production", "test"],
        default="production",
        help="production: external IPs; test: internal IPv4 only",
    )
    parser.add_argument(
        "--zone-id",
        default=os.environ.get("ROUTE53_ZONE_ID", ""),
        help="Route53 hosted zone ID (skips auto-detection)",
    )
    args = parser.parse_args()

    # ── Resolve IPs based on mode ──
    if args.mode == "test":
        ipv4 = get_internal_ipv4()
        ipv6 = None
        print(f"Mode: test (internal IPv4)")
    else:
        ipv4 = get_public_ipv4()
        ipv6 = get_public_ipv6()
        print(f"Mode: production (external IPs)")

    if not ipv4:
        print("ERROR: Could not determine IPv4 address", file=sys.stderr)
        sys.exit(1)
    print(f"IPv4: {ipv4}")

    if ipv6:
        print(f"IPv6: {ipv6}")
    else:
        print("IPv6: not available — skipping AAAA record")

    # ── Find hosted zone ──
    client = boto3.client("route53")
    if args.zone_id:
        zone_id = args.zone_id
        print(f"Using provided zone ID: {zone_id}")
    else:
        zone_id = find_hosted_zone(client, args.domain)
        if not zone_id:
            print(f"ERROR: No hosted zone found for {args.domain}", file=sys.stderr)
            sys.exit(1)

    # ── UPSERT A record ──
    print(f"Upserting A record: {args.domain} -> {ipv4}")
    upsert_record(client, zone_id, args.domain, "A", ipv4)
    print(f"A record updated: {args.domain} -> {ipv4} (TTL 300)")

    # ── UPSERT AAAA record (production only, if IPv6 available) ──
    if ipv6:
        print(f"Upserting AAAA record: {args.domain} -> {ipv6}")
        upsert_record(client, zone_id, args.domain, "AAAA", ipv6)
        print(f"AAAA record updated: {args.domain} -> {ipv6} (TTL 300)")


if __name__ == "__main__":
    main()
ROUTE53
chmod +x "${DEPLOY_DIR}/route53-update.py"
echo "  Created route53-update.py"

# =============================================================================
# reload-nginx.sh — send SIGHUP to nginx via Docker socket API
# =============================================================================
cat > "${DEPLOY_DIR}/reload-nginx.sh" << 'RELOADNGINX'
#!/bin/bash
# Reload nginx configuration by sending SIGHUP via the Docker Engine API.
# Requires /var/run/docker.sock to be mounted into this container.
set -euo pipefail

SOCK="/var/run/docker.sock"

if [ ! -S "${SOCK}" ]; then
    echo "ERROR: Docker socket not found at ${SOCK}" >&2
    exit 1
fi

# Find the nginx container ID (inventree-proxy)
CONTAINER_ID=$(curl -s --unix-socket "${SOCK}" \
    "http://localhost/containers/json" | \
    jq -r '.[] | select(.Names[] | test("inventree-proxy")) | .Id' | head -1)

if [ -z "${CONTAINER_ID}" ]; then
    echo "ERROR: Could not find inventree-proxy container" >&2
    exit 1
fi

echo "Sending HUP to nginx container ${CONTAINER_ID:0:12}..."
curl -s --unix-socket "${SOCK}" \
    -X POST "http://localhost/containers/${CONTAINER_ID}/kill?signal=HUP"

echo "Nginx reload signal sent."
RELOADNGINX
chmod +x "${DEPLOY_DIR}/reload-nginx.sh"
echo "  Created reload-nginx.sh"

# =============================================================================
# docker-compose.yml — 5 services: mysql, certbot, inventree-server, worker, nginx
# =============================================================================
cat > "${DEPLOY_DIR}/docker-compose.yml" << 'COMPOSE'
services:
  # ---------------------------------------------------------------------------
  # MySQL 8.0 — database backend
  # ---------------------------------------------------------------------------
  inventree-db:
    image: mysql:8.0
    restart: unless-stopped
    environment:
      MYSQL_DATABASE: ${INVENTREE_DB_NAME:-inventree}
      MYSQL_USER: ${INVENTREE_DB_USER:-inventree}
      MYSQL_PASSWORD_FILE: /run/secrets/mysql_password
      MYSQL_ROOT_PASSWORD_FILE: /run/secrets/mysql_password
    secrets:
      - mysql_password
    volumes:
      - mysql-data:/var/lib/mysql
      - mysql-socket:/var/run/mysqld
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "--socket=/var/run/mysqld/mysqld.sock"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 30s

  # ---------------------------------------------------------------------------
  # Certbot — DNS-01 certificate + Route53 dynamic DNS
  # ---------------------------------------------------------------------------
  inventree-certbot:
    build:
      context: .
      dockerfile: Dockerfile.certbot
    restart: unless-stopped
    environment:
      INVENTREE_DOMAIN: ${INVENTREE_DOMAIN:-api.your-domain.com}
      CERTBOT_EMAIL: ${CERTBOT_EMAIL:-}
      DNS_MODE: ${DNS_MODE:-production}
      ROUTE53_ZONE_ID: ${ROUTE53_ZONE_ID:-}
    volumes:
      - certbot-data:/etc/letsencrypt
      - ../.aws:/root/.aws:ro
      - /var/run/docker.sock:/var/run/docker.sock:ro
    healthcheck:
      test: ["CMD", "test", "-f", "/etc/letsencrypt/.ready"]
      interval: 5s
      timeout: 3s
      retries: 60
      start_period: 10s

  # ---------------------------------------------------------------------------
  # InvenTree server — uWSGI serving the Django application
  # ---------------------------------------------------------------------------
  inventree-server:
    build:
      context: .
      args:
        INVENTREE_TAG: ${INVENTREE_TAG:-stable}
    restart: unless-stopped
    depends_on:
      inventree-db:
        condition: service_healthy
    environment:
      INVENTREE_DB_ENGINE: ${INVENTREE_DB_ENGINE:-mysql}
      INVENTREE_DB_NAME: ${INVENTREE_DB_NAME:-inventree}
      INVENTREE_DB_USER: ${INVENTREE_DB_USER:-inventree}
      # INVENTREE_DB_HOST is intentionally absent — empty HOST lets
      # config.yaml's OPTIONS.unix_socket take effect.
      INVENTREE_SITE_URL: ${INVENTREE_SITE_URL:-https://api.your-domain.com}
      INVENTREE_DEBUG: ${INVENTREE_DEBUG:-False}
      INVENTREE_PLUGINS_ENABLED: ${INVENTREE_PLUGINS_ENABLED:-true}
      INVENTREE_PLUGIN_DIR: ${INVENTREE_PLUGIN_DIR:-/home/inventree/plugins}
      INVENTREE_SOCIAL_BACKENDS: ${INVENTREE_SOCIAL_BACKENDS:-google}
    secrets:
      - mysql_password
    volumes:
      - mysql-socket:/var/run/mysqld
      - uwsgi-socket:/var/run/uwsgi
      - inventree-data:/home/inventree/data
      - ../plugins:/home/inventree/plugins:ro

  # ---------------------------------------------------------------------------
  # InvenTree background worker (django-q2)
  # ---------------------------------------------------------------------------
  inventree-worker:
    build:
      context: .
      args:
        INVENTREE_TAG: ${INVENTREE_TAG:-stable}
    restart: unless-stopped
    command: invoke worker
    depends_on:
      inventree-server:
        condition: service_started
    environment:
      INVENTREE_DB_ENGINE: ${INVENTREE_DB_ENGINE:-mysql}
      INVENTREE_DB_NAME: ${INVENTREE_DB_NAME:-inventree}
      INVENTREE_DB_USER: ${INVENTREE_DB_USER:-inventree}
      INVENTREE_SITE_URL: ${INVENTREE_SITE_URL:-https://api.your-domain.com}
      INVENTREE_DEBUG: ${INVENTREE_DEBUG:-False}
      INVENTREE_BACKGROUND_WORKERS: ${INVENTREE_BACKGROUND_WORKERS:-4}
      INVENTREE_PLUGINS_ENABLED: ${INVENTREE_PLUGINS_ENABLED:-true}
      INVENTREE_PLUGIN_DIR: ${INVENTREE_PLUGIN_DIR:-/home/inventree/plugins}
      INVENTREE_SOCIAL_BACKENDS: ${INVENTREE_SOCIAL_BACKENDS:-google}
    secrets:
      - mysql_password
    volumes:
      - mysql-socket:/var/run/mysqld
      - inventree-data:/home/inventree/data
      - ../plugins:/home/inventree/plugins:ro

  # ---------------------------------------------------------------------------
  # Nginx reverse proxy — HTTPS termination
  # ---------------------------------------------------------------------------
  inventree-proxy:
    image: nginx:1.25-alpine
    restart: unless-stopped
    depends_on:
      inventree-server:
        condition: service_started
      inventree-certbot:
        condition: service_healthy
    ports:
      - "${INVENTREE_WEB_PORT:-80}:80"
      - "${INVENTREE_HTTPS_PORT:-443}:443"
    environment:
      INVENTREE_DOMAIN: ${INVENTREE_DOMAIN:-api.your-domain.com}
    volumes:
      - uwsgi-socket:/var/run/uwsgi
      - inventree-data:/home/inventree/data:ro
      - certbot-data:/etc/letsencrypt:ro
      - ./nginx.conf.template:/etc/nginx/templates/default.conf.template:ro

# =============================================================================
# Named volumes
# =============================================================================
volumes:
  mysql-data:        # Persistent MySQL data
  mysql-socket:      # /var/run/mysqld/ shared between mysql + inventree
  uwsgi-socket:      # /var/run/uwsgi/ shared between inventree + nginx
  inventree-data:    # /home/inventree/data (static, media, config, backups)
  certbot-data:      # /etc/letsencrypt/ shared between certbot + nginx

# =============================================================================
# Docker secrets
# =============================================================================
secrets:
  mysql_password:
    file: ./secrets/mysql_password
COMPOSE
echo "  Created docker-compose.yml"

# =============================================================================
# Done
# =============================================================================
echo ""
echo "========================================="
echo "  Deployment files generated successfully"
echo "========================================="
echo ""
echo "Directory: ${DEPLOY_DIR}"
echo ""
echo "Next steps:"
echo "  cd shinbee-deploy"
echo "  docker compose build"
echo "  docker compose up -d"
echo ""
echo "Verify:"
echo "  docker compose logs -f inventree-certbot  # watch cert acquisition"
echo "  docker compose logs -f inventree-server   # watch startup"
echo "  curl -k https://localhost/api/             # test API (self-signed)"
echo "  curl https://api.your-domain.com/api/    # test API (real cert)"
echo ""
