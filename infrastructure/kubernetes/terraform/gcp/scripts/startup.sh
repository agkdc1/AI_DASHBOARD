#!/bin/bash
# startup.sh — GCP instance startup script
# Installs Tailscale, WireGuard tools, and K3s SERVER (control plane).
# Tailscale auth key is read from GCP Secret Manager at boot.
# This node is the cluster master — local nodes join it via Tailscale.
set -euo pipefail
exec &> >(tee -a /var/log/k3s-startup.log)

echo "[startup] Started at $(date)"

# ── Metadata ─────────────────────────────────────────────────────────────────

PROJECT_ID=$(curl -sf -H "Metadata-Flavor: Google" \
  http://metadata.google.internal/computeMetadata/v1/project/project-id)
SECRET_NAME=$(curl -sf -H "Metadata-Flavor: Google" \
  http://metadata.google.internal/computeMetadata/v1/instance/attributes/ts-secret-name)

# ── Skip if already provisioned ──────────────────────────────────────────────

if [ -f /var/lib/k3s-provisioned ]; then
    echo "[startup] Already provisioned, skipping."
    exit 0
fi

# ── SSH keypair (auto-generated, no external injection) ──────────────────────

if [ ! -d /root/.ssh ]; then
    mkdir -p /root/.ssh
    chmod 700 /root/.ssh
    ssh-keygen -t ed25519 -f /root/.ssh/id_ed25519 -N "" -q
    echo "[startup] SSH keypair generated for root"
fi

# ── System packages ──────────────────────────────────────────────────────────

apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    curl jq ca-certificates gnupg \
    openssh-server \
    wireguard-tools \
    linux-headers-$(uname -r) 2>/dev/null || true

# Enable WireGuard kernel module (loaded on boot)
modprobe wireguard 2>/dev/null || true
echo "wireguard" >> /etc/modules-load.d/wireguard.conf

# IP forwarding (required for WireGuard and K3s)
cat > /etc/sysctl.d/99-k3s.conf << 'SYSCTL_EOF'
net.ipv4.ip_forward = 1
net.ipv6.conf.all.forwarding = 1
SYSCTL_EOF
sysctl --system > /dev/null

echo "[startup] System packages installed"

# ── Tailscale ────────────────────────────────────────────────────────────────

curl -fsSL https://pkgs.tailscale.com/stable/debian/bookworm.noarmor.gpg \
    -o /usr/share/keyrings/tailscale-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/tailscale-archive-keyring.gpg] https://pkgs.tailscale.com/stable/debian bookworm main" \
    > /etc/apt/sources.list.d/tailscale.list
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq tailscale
systemctl enable --now tailscaled

# Read auth key from Secret Manager via REST API (no gcloud dependency)
ACCESS_TOKEN=$(curl -sf -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" \
  | jq -r '.access_token')

TS_AUTH_KEY=$(curl -sf \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  "https://secretmanager.googleapis.com/v1/projects/${PROJECT_ID}/secrets/${SECRET_NAME}/versions/latest:access" \
  | jq -r '.payload.data' | base64 -d) || {
    echo "[startup] ERROR: Failed to read Tailscale auth key from Secret Manager"
    exit 1
}

HOSTNAME=$(hostname)
tailscale up --authkey="${TS_AUTH_KEY}" --hostname="${HOSTNAME}" --ssh

# Wait for Tailscale to get an IP
for i in $(seq 1 30); do
    TS_IP=$(tailscale ip -4 2>/dev/null || true)
    if [ -n "${TS_IP}" ]; then
        break
    fi
    sleep 2
done

if [ -z "${TS_IP:-}" ]; then
    echo "[startup] ERROR: Tailscale did not get an IP after 60s"
    exit 1
fi

echo "[startup] Tailscale connected: ${TS_IP}"

# ── WireGuard placeholder ───────────────────────────────────────────────────
# Generate keypair now — actual tunnel config will be added later
# when this node is registered with the MikroTik WireGuard peer list.

if [ ! -f /etc/wireguard/private.key ]; then
    mkdir -p /etc/wireguard
    chmod 700 /etc/wireguard
    wg genkey > /etc/wireguard/private.key
    chmod 600 /etc/wireguard/private.key
    wg pubkey < /etc/wireguard/private.key > /etc/wireguard/public.key
    echo "[startup] WireGuard keypair generated"
    echo "[startup] Public key: $(cat /etc/wireguard/public.key)"
fi

# ── K3s server (control plane) ───────────────────────────────────────────────
# This is the cluster master. Workers join via Tailscale using the token
# generated here. Tainted as entrypoint-only to minimize GCP egress.

curl -sfL https://get.k3s.io | \
    INSTALL_K3S_EXEC="server" \
    INSTALL_K3S_CHANNEL="stable" \
    sh -s - \
    --disable traefik \
    --disable servicelb \
    --tls-san "${TS_IP}" \
    --bind-address "${TS_IP}" \
    --advertise-address "${TS_IP}" \
    --node-label="topology.kubernetes.io/zone=gcp" \
    --node-label="node.kubernetes.io/role=entrypoint" \
    --node-taint="node.kubernetes.io/role=entrypoint:NoSchedule" \
    --node-taint="node-role.kubernetes.io/control-plane:NoSchedule" \
    --flannel-iface=tailscale0

echo "[startup] K3s server installed"

# Wait for K3s API to be ready
for i in $(seq 1 60); do
    if /usr/local/bin/k3s kubectl get nodes &>/dev/null; then
        break
    fi
    sleep 2
done

echo "[startup] K3s API ready"
echo "[startup] Node token: $(cat /var/lib/rancher/k3s/server/node-token)"
echo "[startup] Server URL: https://${TS_IP}:6443"

# ── Artifact Registry credentials ────────────────────────────────────────
# Fetch the AR reader SA key from Secret Manager and write registries.yaml
# so containerd can pull images from Artifact Registry natively.

AR_KEY=$(curl -sf \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  "https://secretmanager.googleapis.com/v1/projects/${PROJECT_ID}/secrets/ar-reader-key/versions/latest:access" \
  | jq -r '.payload.data' | base64 -d) || {
    echo "[startup] WARNING: Failed to read AR key from Secret Manager — skipping registries.yaml"
    AR_KEY=""
}

if [ -n "${AR_KEY}" ]; then
    AR_KEY_B64=$(echo -n "${AR_KEY}" | base64 -w0)
    mkdir -p /etc/rancher/k3s
    cat > /etc/rancher/k3s/registries.yaml << REGISTRY_EOF
mirrors:
  asia-northeast1-docker.pkg.dev:
    endpoint:
      - "https://asia-northeast1-docker.pkg.dev"
configs:
  "asia-northeast1-docker.pkg.dev":
    auth:
      username: _json_key_base64
      password: "${AR_KEY_B64}"
REGISTRY_EOF
    chmod 600 /etc/rancher/k3s/registries.yaml
    echo "[startup] registries.yaml written for Artifact Registry"
fi

# ── Squid forward proxy for Rakuten API ───────────────────────────────────────
# Rakuten RMS requires IP allowlisting. This Squid proxy ensures all Rakuten
# API traffic exits through k3s-control-0's static IP.

DEBIAN_FRONTEND=noninteractive apt-get install -y -qq squid

cat > /etc/squid/squid.conf << 'SQUID_EOF'
# Squid forward proxy for Rakuten API traffic
http_port 3128

# ACL: Only allow Rakuten API endpoints
acl rakuten_api dstdomain api.rms.rakuten.co.jp
acl rakuten_api dstdomain image.rakuten.co.jp

# ACL: Only allow from Tailscale and K8s pod networks
acl tailscale_net src 100.64.0.0/10
acl k8s_pods src 10.42.0.0/16
acl k8s_services src 10.43.0.0/16
acl local_net src 10.10.0.0/24
acl localhost src 127.0.0.0/8

# ACL: Safe ports (HTTPS only for Rakuten)
acl SSL_ports port 443
acl Safe_ports port 443
acl CONNECT method CONNECT

# Access rules
http_access deny !Safe_ports
http_access deny CONNECT !SSL_ports
http_access allow rakuten_api tailscale_net
http_access allow rakuten_api k8s_pods
http_access allow rakuten_api k8s_services
http_access allow rakuten_api local_net
http_access allow rakuten_api localhost
http_access deny all

# Logging
access_log /var/log/squid/access.log squid
cache_log /var/log/squid/cache.log

# No caching, strip forwarded headers
cache deny all
forwarded_for delete
via off
visible_hostname rakuten-proxy
SQUID_EOF

systemctl enable squid
systemctl restart squid
echo "[startup] Squid proxy installed on port 3128"

# ── Mark provisioned ─────────────────────────────────────────────────────────

touch /var/lib/k3s-provisioned
echo "[startup] Complete at $(date)"
