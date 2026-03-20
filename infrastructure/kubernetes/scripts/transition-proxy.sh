#!/usr/bin/env bash
# transition-proxy.sh — Set up Pi as TCP proxy forwarding 80/443 to K8s workers
#
# Stops InvenTree Docker on Pi, installs nginx with stream module for
# TLS passthrough (SNI) to K8s workers running nginx-ingress on hostPort.
# cert-manager on K8s manages TLS — Pi forwards raw TCP, no double-TLS.
#
# FAX stack (ports 8010/587) and Vault (8200) are NOT touched.
#
# Usage: sudo ./transition-proxy.sh [--rollback] [--dry-run]
#
# Rollback: sudo ./transition-proxy.sh --rollback
#   Removes nginx stream config, restarts InvenTree Docker stack.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

export KUBECONFIG="${KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}"

ROLLBACK=false
DRY_RUN=false

for arg in "$@"; do
    case "$arg" in
        --rollback) ROLLBACK=true ;;
        --dry-run) DRY_RUN=true ;;
        *) echo "Unknown option: $arg"; exit 1 ;;
    esac
done

# ── Colors ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

log()     { echo -e "${GREEN}[OK]${NC}     $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}   $*"; }
info()    { echo -e "${CYAN}[INFO]${NC}   $*"; }
err()     { echo -e "${RED}[ERROR]${NC}  $*" >&2; }
section() { echo -e "\n${BOLD}━━━ $* ━━━${NC}\n"; }

run() {
    if [ "${DRY_RUN}" = "true" ]; then
        info "[DRY RUN] $*"
    else
        "$@"
    fi
}

STREAM_CONF="/etc/nginx/stream.d/shinbee-k8s.conf"
NGINX_CONF="/etc/nginx/nginx.conf"
TIMER_NAME="shinbee-proxy-refresh"
UPDATE_SCRIPT="${SCRIPT_DIR}/update-proxy-upstreams.sh"

# ======================== ROOT CHECK ========================
if [ "$(id -u)" -ne 0 ]; then
    err "Must run as root"
    exit 1
fi

# ======================== ROLLBACK ========================
if [ "${ROLLBACK}" = "true" ]; then
    section "ROLLBACK: Restoring InvenTree Docker"

    # Stop nginx stream proxy
    if systemctl is-active nginx &>/dev/null; then
        info "Stopping nginx..."
        run systemctl stop nginx
    fi

    # Remove stream config
    if [ -f "${STREAM_CONF}" ]; then
        info "Removing ${STREAM_CONF}"
        run rm -f "${STREAM_CONF}"
    fi

    # Disable and remove refresh timer
    if systemctl is-enabled "${TIMER_NAME}.timer" &>/dev/null; then
        info "Disabling ${TIMER_NAME}.timer"
        run systemctl disable --now "${TIMER_NAME}.timer"
    fi

    # Re-enable InvenTree services
    info "Enabling vault-render-inventree.service..."
    run systemctl enable vault-render-inventree.service
    run systemctl start vault-render-inventree.service

    info "Enabling shinbee-inventree.service..."
    run systemctl enable shinbee-inventree.service
    run systemctl start shinbee-inventree.service

    # Wait for InvenTree Docker containers
    if [ "${DRY_RUN}" != "true" ]; then
        info "Waiting for InvenTree Docker containers..."
        ELAPSED=0
        while [ "${ELAPSED}" -lt 120 ]; do
            if sg docker -c "docker ps --filter name=inventree-server --format '{{.Status}}'" 2>/dev/null | grep -q "Up"; then
                break
            fi
            sleep 5
            ELAPSED=$((ELAPSED + 5))
        done

        if sg docker -c "docker ps --filter name=inventree-server --format '{{.Status}}'" 2>/dev/null | grep -q "Up"; then
            log "InvenTree Docker containers running"
        else
            warn "InvenTree containers may not be fully up yet — check manually"
        fi
    fi

    log ""
    log "=== ROLLBACK COMPLETE ==="
    log "  InvenTree Docker restored on Pi"
    log "  Verify: curl -k https://api.your-domain.com/api/"
    exit 0
fi

# ======================== PRE-FLIGHT ========================
section "Pre-flight checks"

# K8s cluster reachable
if ! kubectl get nodes &>/dev/null; then
    err "Cannot reach K8s API server (kubectl get nodes failed)"
    err "  Is K3s running? Check: systemctl status k3s"
    exit 1
fi
log "K8s cluster reachable"

# Workers ready
WORKER_IPS=()
while IFS= read -r line; do
    [ -z "$line" ] && continue
    WORKER_IPS+=("$line")
done < <(kubectl get nodes -l node-role.kubernetes.io/worker --no-headers -o jsonpath='{range .items[?(@.status.conditions[-1].type=="Ready")]}{.status.addresses[?(@.type=="InternalIP")].address}{"\n"}{end}' 2>/dev/null)

if [ "${#WORKER_IPS[@]}" -eq 0 ]; then
    err "No Ready amd64 worker nodes found"
    err "  Check: kubectl get nodes -o wide"
    exit 1
fi
log "${#WORKER_IPS[@]} Ready worker(s): ${WORKER_IPS[*]}"

# FAX stack running
FAX_HEALTH=$(curl -sf http://localhost:8010/health 2>/dev/null || echo "")
if [ -n "${FAX_HEALTH}" ]; then
    log "FAX stack healthy (faxapi :8010)"
else
    warn "FAX stack health check failed — continuing (may not be running)"
fi

# Vault healthy
VAULT_STATUS=$(curl -sf http://127.0.0.1:8200/v1/sys/health 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('sealed','error'))" 2>/dev/null || echo "error")
if [ "${VAULT_STATUS}" = "false" ]; then
    log "Vault unsealed and healthy"
else
    warn "Vault may not be healthy (sealed=${VAULT_STATUS}) — continuing"
fi

# Ports 80/443 check (who owns them now)
for port in 80 443; do
    OWNER=$(ss -tlnp "sport = :${port}" 2>/dev/null | grep -v "State" | head -1 || true)
    if [ -n "${OWNER}" ]; then
        info "Port ${port} currently held by: ${OWNER}"
    else
        info "Port ${port} is free"
    fi
done

if [ "${DRY_RUN}" = "true" ]; then
    info ""
    info "=== DRY RUN — no changes will be made ==="
    info ""
fi

# ======================== STEP 1: Stop InvenTree Docker ========================
section "Step 1: Stopping InvenTree Docker services"

# Disable systemd units so they don't restart on reboot
info "Disabling vault-render-inventree.service..."
run systemctl disable vault-render-inventree.service
run systemctl stop vault-render-inventree.service 2>/dev/null || true

info "Disabling shinbee-inventree.service..."
run systemctl disable shinbee-inventree.service
run systemctl stop shinbee-inventree.service 2>/dev/null || true

# Bring down InvenTree Docker compose
info "Running docker compose down for InvenTree..."
if [ "${DRY_RUN}" != "true" ]; then
    cd "${REPO_ROOT}/services/inventory/shinbee-deploy"
    sg docker -c "docker compose down" || {
        warn "docker compose down returned non-zero — containers may already be stopped"
    }
    cd "${REPO_ROOT}"
fi

log "InvenTree Docker services stopped and disabled"

# Wait for ports to free up
if [ "${DRY_RUN}" != "true" ]; then
    info "Waiting for ports 80/443 to be released..."
    ELAPSED=0
    while [ "${ELAPSED}" -lt 30 ]; do
        PORT_80=$(ss -tlnp "sport = :80" 2>/dev/null | grep -v "State" | wc -l)
        PORT_443=$(ss -tlnp "sport = :443" 2>/dev/null | grep -v "State" | wc -l)
        if [ "${PORT_80}" -eq 0 ] && [ "${PORT_443}" -eq 0 ]; then
            break
        fi
        sleep 2
        ELAPSED=$((ELAPSED + 2))
    done

    # Final check
    for port in 80 443; do
        if ss -tlnp "sport = :${port}" 2>/dev/null | grep -qv "State"; then
            err "Port ${port} still in use after 30s — something else is binding it"
            err "  Check: ss -tlnp sport = :${port}"
            exit 1
        fi
    done
    log "Ports 80 and 443 are free"
fi

# ======================== STEP 2: Install nginx ========================
section "Step 2: Installing nginx with stream module"

if ! command -v nginx &>/dev/null; then
    info "Installing nginx..."
    run apt-get update -qq
    run apt-get install -y -qq nginx libnginx-mod-stream
    log "nginx installed"
else
    log "nginx already installed"
fi

# Verify stream module is available
if [ "${DRY_RUN}" != "true" ]; then
    if ! nginx -V 2>&1 | grep -q "stream"; then
        # Try installing the stream module separately
        info "Stream module not found, installing libnginx-mod-stream..."
        apt-get install -y -qq libnginx-mod-stream
        if ! nginx -V 2>&1 | grep -q "stream"; then
            err "nginx stream module is not available"
            err "  nginx-ingress TLS passthrough requires the stream module"
            exit 1
        fi
    fi
    log "nginx stream module available"
fi

# Stop nginx if it was auto-started by apt (we configure first)
run systemctl stop nginx 2>/dev/null || true

# ======================== STEP 3: Configure nginx stream proxy ========================
section "Step 3: Configuring nginx stream proxy"

# Create stream.d directory
run mkdir -p /etc/nginx/stream.d

# Ensure nginx.conf loads stream.d configs at the top level
# The stream{} block must be at the top level of nginx.conf (not inside http{})
if [ "${DRY_RUN}" != "true" ]; then
    if ! grep -q 'include /etc/nginx/stream.d/\*.conf' "${NGINX_CONF}" 2>/dev/null; then
        info "Adding stream include to ${NGINX_CONF}..."

        # Check if there's already a stream block
        if grep -q '^stream\s*{' "${NGINX_CONF}" 2>/dev/null; then
            warn "Existing stream{} block found in nginx.conf — adding include inside it"
            # Insert include inside existing stream block
            sed -i '/^stream\s*{/a\    include /etc/nginx/stream.d/*.conf;' "${NGINX_CONF}"
        else
            # Append a stream block that includes our configs
            cat >> "${NGINX_CONF}" << 'STREAM_BLOCK'

# K8s worker proxy — managed by transition-proxy.sh
stream {
    include /etc/nginx/stream.d/*.conf;
}
STREAM_BLOCK
        fi
        log "Added stream{} block to nginx.conf"
    else
        log "stream.d include already present in nginx.conf"
    fi
fi

# Disable default HTTP server to avoid port 80 conflict
if [ "${DRY_RUN}" != "true" ]; then
    if [ -L /etc/nginx/sites-enabled/default ] || [ -f /etc/nginx/sites-enabled/default ]; then
        info "Disabling default nginx HTTP site (port 80 conflict)..."
        rm -f /etc/nginx/sites-enabled/default
        log "Default site disabled"
    fi
fi

# Generate upstream config
info "Generating ${STREAM_CONF}..."

UPSTREAM_HTTPS=""
UPSTREAM_HTTP=""
UPSTREAM_LDAP=""
UPSTREAM_PROVISION=""
for ip in "${WORKER_IPS[@]}"; do
    UPSTREAM_HTTPS+="    server ${ip}:443;
"
    UPSTREAM_HTTP+="    server ${ip}:80;
"
    UPSTREAM_LDAP+="    server ${ip}:30389;
"
    UPSTREAM_PROVISION+="    server ${ip}:30080;
"
done

if [ "${DRY_RUN}" != "true" ]; then
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
    log "Stream config written to ${STREAM_CONF}"

    # Phone provisioning HTTP proxy (:9080 → K8s phone-provision NodePort)
    PROVISION_CONF="/etc/nginx/conf.d/phone-provision.conf"
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
    log "Provision HTTP proxy config written to ${PROVISION_CONF}"
else
    info "Would write stream config with workers: ${WORKER_IPS[*]}"
fi

# Test and start nginx
if [ "${DRY_RUN}" != "true" ]; then
    info "Testing nginx configuration..."
    if ! nginx -t 2>&1; then
        err "nginx config test failed"
        err "  Check: nginx -t"
        err "  Config: ${STREAM_CONF}"
        exit 1
    fi
    log "nginx config OK"

    info "Enabling and starting nginx..."
    systemctl enable --now nginx
    log "nginx is running"
else
    info "Would test and start nginx"
fi

# ======================== STEP 4: Install systemd timer ========================
section "Step 4: Installing proxy upstream refresh timer"

TIMER_UNIT="/etc/systemd/system/${TIMER_NAME}.timer"
SERVICE_UNIT="/etc/systemd/system/${TIMER_NAME}.service"

if [ "${DRY_RUN}" != "true" ]; then
    cat > "${SERVICE_UNIT}" << EOF
[Unit]
Description=Refresh K8s worker IPs in nginx stream proxy

[Service]
Type=oneshot
ExecStart=${UPDATE_SCRIPT}
Environment=KUBECONFIG=/etc/rancher/k3s/k3s.yaml
EOF

    cat > "${TIMER_UNIT}" << EOF
[Unit]
Description=Refresh K8s worker IPs every 5 minutes

[Timer]
OnBootSec=60
OnUnitActiveSec=300
RandomizedDelaySec=15

[Install]
WantedBy=timers.target
EOF

    systemctl daemon-reload
    systemctl enable --now "${TIMER_NAME}.timer"
    log "Timer ${TIMER_NAME}.timer installed and started"
else
    info "Would install ${TIMER_NAME}.timer (every 5 min)"
fi

# ======================== STEP 5: Verify ========================
section "Verification"

if [ "${DRY_RUN}" != "true" ]; then
    # Check nginx owns 80/443
    for port in 80 443; do
        if ss -tlnp "sport = :${port}" 2>/dev/null | grep -q "nginx"; then
            log "nginx listening on port ${port}"
        else
            warn "nginx may not be listening on port ${port} — check manually"
        fi
    done

    # Check FAX stack
    FAX_CHECK=$(curl -sf http://localhost:8010/health 2>/dev/null || echo "")
    if [ -n "${FAX_CHECK}" ]; then
        log "FAX stack still healthy"
    else
        warn "FAX health check failed — verify manually"
    fi

    # Check Vault
    VAULT_CHECK=$(curl -sf http://127.0.0.1:8200/v1/sys/health 2>/dev/null || echo "")
    if [ -n "${VAULT_CHECK}" ]; then
        log "Vault still healthy"
    else
        warn "Vault health check failed — verify manually"
    fi

    # Check Docker containers (FAX should still be running)
    FAX_CONTAINERS=$(sg docker -c "docker ps --filter name=raspbx --filter name=faxapi --filter name=mail2fax --format '{{.Names}}'" 2>/dev/null | wc -l)
    log "FAX Docker containers running: ${FAX_CONTAINERS}"

    # Check InvenTree containers are gone
    INVENTREE_CONTAINERS=$(sg docker -c "docker ps --filter name=inventree --format '{{.Names}}'" 2>/dev/null | wc -l)
    if [ "${INVENTREE_CONTAINERS}" -eq 0 ]; then
        log "InvenTree Docker containers stopped (expected)"
    else
        warn "InvenTree Docker containers still running: ${INVENTREE_CONTAINERS}"
    fi
fi

# ======================== Summary ========================
section "Transition Complete"

echo ""
log "Pi is now proxying 80/443 → K8s workers via nginx stream (TLS passthrough)"
echo ""
info "Worker IPs configured: ${WORKER_IPS[*]}"
info "Timer: ${TIMER_NAME}.timer refreshes worker IPs every 5 min"
echo ""
info "What happened:"
info "  - shinbee-inventree.service: disabled + stopped"
info "  - vault-render-inventree.service: disabled + stopped"
info "  - InvenTree Docker: compose down (data volumes preserved)"
info "  - nginx: stream proxy on 80/443 → workers"
info "  - FAX + Vault: untouched"
echo ""
info "Verify from another machine:"
info "  curl -sk https://api.your-domain.com/api/"
info "  curl -sk https://portal.your-domain.com/"
echo ""
info "On this Pi:"
info "  ss -tlnp | grep -E ':80|:443'     # nginx owns these"
info "  curl -sf http://localhost:8010/health   # FAX still works"
info "  systemctl status ${TIMER_NAME}.timer    # IP refresh timer"
echo ""
info "Rollback: sudo $0 --rollback"
