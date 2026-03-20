#!/usr/bin/env bash
# update-proxy-upstreams.sh — Refresh K8s worker IPs in nginx stream config
#
# Called by shinbee-proxy-refresh.timer every 5 minutes.
# Queries kubectl for current amd64 worker Tailscale IPs, compares with
# the IPs in the nginx stream config, and reloads nginx if changed.
#
# Usage: sudo ./update-proxy-upstreams.sh
#   (normally invoked by systemd timer, not manually)

set -euo pipefail

export KUBECONFIG="${KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}"

STREAM_CONF="/etc/nginx/stream.d/shinbee-k8s.conf"
LOGGER_TAG="shinbee-proxy-refresh"

log() { logger -t "${LOGGER_TAG}" "$*"; echo "[$(date '+%H:%M:%S')] $*"; }

# Bail if nginx isn't running (transition-proxy.sh not yet run, or rolled back)
if [ ! -f "${STREAM_CONF}" ]; then
    log "No stream config at ${STREAM_CONF} — nothing to do"
    exit 0
fi

if ! systemctl is-active nginx &>/dev/null; then
    log "nginx is not running — nothing to do"
    exit 0
fi

# Get current worker IPs from K8s
NEW_IPS=()
while IFS= read -r ip; do
    [ -z "$ip" ] && continue
    NEW_IPS+=("$ip")
done < <(kubectl get nodes -l node-role.kubernetes.io/worker --no-headers -o jsonpath='{range .items[?(@.status.conditions[-1].type=="Ready")]}{.status.addresses[?(@.type=="InternalIP")].address}{"\n"}{end}' 2>/dev/null)

if [ "${#NEW_IPS[@]}" -eq 0 ]; then
    log "WARNING: No Ready amd64 workers found — keeping existing config"
    exit 0
fi

# Sort for stable comparison
IFS=$'\n' NEW_IPS_SORTED=($(printf '%s\n' "${NEW_IPS[@]}" | sort)); unset IFS

# Extract current IPs from config file
OLD_IPS_SORTED=()
while IFS= read -r ip; do
    [ -z "$ip" ] && continue
    OLD_IPS_SORTED+=("$ip")
done < <(grep -oP 'server \K[0-9.]+' "${STREAM_CONF}" 2>/dev/null | sort -u)

# Compare
OLD_STR=$(printf '%s\n' "${OLD_IPS_SORTED[@]}")
NEW_STR=$(printf '%s\n' "${NEW_IPS_SORTED[@]}")

if [ "${OLD_STR}" = "${NEW_STR}" ]; then
    log "Worker IPs unchanged (${NEW_IPS_SORTED[*]}) — no reload needed"
    exit 0
fi

log "Worker IPs changed: [${OLD_IPS_SORTED[*]}] → [${NEW_IPS_SORTED[*]}]"

# Regenerate config
UPSTREAM_HTTPS=""
UPSTREAM_HTTP=""
UPSTREAM_LDAP=""
UPSTREAM_PROVISION=""
for ip in "${NEW_IPS[@]}"; do
    UPSTREAM_HTTPS+="    server ${ip}:443;
"
    UPSTREAM_HTTP+="    server ${ip}:80;
"
    UPSTREAM_LDAP+="    server ${ip}:30389;
"
    UPSTREAM_PROVISION+="    server ${ip}:30080;
"
done

cat > "${STREAM_CONF}" << NGINX_EOF
# /etc/nginx/stream.d/shinbee-k8s.conf
# Managed by transition-proxy.sh — do not edit manually
# Worker IPs from: kubectl get nodes -l kubernetes.io/arch=amd64
# Generated: $(date -Iseconds)

upstream k8s_https {
${UPSTREAM_HTTPS}}

upstream k8s_http {
${UPSTREAM_HTTP}}

map \$ssl_preread_server_name \$k8s_backend {
    api.your-domain.com    k8s_https;
    portal.your-domain.com k8s_https;
    app.your-domain.com    k8s_https;
    tasks.your-domain.com  k8s_https;
    wiki.your-domain.com   k8s_https;
    default                  k8s_https;
}

server {
    listen 443;
    proxy_pass \$k8s_backend;
    ssl_preread on;
    proxy_connect_timeout 5s;
    proxy_timeout 3600s;
}

server {
    listen 80;
    proxy_pass k8s_http;
    proxy_connect_timeout 5s;
    proxy_timeout 60s;
}

# --- Phone provisioning: LDAP (TCP proxy) ---
upstream k8s_ldap {
${UPSTREAM_LDAP}}

server {
    listen 9389;
    proxy_pass k8s_ldap;
    proxy_connect_timeout 5s;
    proxy_timeout 60s;
}
NGINX_EOF

# Also update phone provisioning HTTP proxy
PROVISION_CONF="/etc/nginx/conf.d/phone-provision.conf"
if [ -f "${PROVISION_CONF}" ]; then
    cat > "${PROVISION_CONF}" << PROV_EOF
# /etc/nginx/conf.d/phone-provision.conf
# Phone provisioning HTTP proxy — managed by transition-proxy.sh
# Generated: $(date -Iseconds)

upstream k8s_provision {
${UPSTREAM_PROVISION}}

server {
    listen 9080;
    server_name _;

    location / {
        proxy_pass http://k8s_provision;
        proxy_connect_timeout 5s;
        proxy_read_timeout 30s;
    }
}
PROV_EOF
fi

# Test before reload
if nginx -t 2>&1; then
    nginx -s reload
    log "nginx reloaded with new worker IPs: ${NEW_IPS_SORTED[*]}"
else
    log "ERROR: nginx config test failed after IP update — manual fix required"
    exit 1
fi
