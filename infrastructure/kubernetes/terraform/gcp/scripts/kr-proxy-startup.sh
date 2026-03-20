#!/bin/bash
# kr-proxy-startup.sh — GCP Seoul instance for Korean traffic WireGuard proxy
# Installs WireGuard, configures NAT masquerade for tunnel traffic.
# MikroTik connects as client (persistent-keepalive), this side is responder.
set -euo pipefail
exec &> >(tee -a /var/log/kr-proxy-startup.log)

echo "[kr-proxy] Started at $(date)"

# ── Skip if already provisioned ──────────────────────────────────────────────

if [ -f /var/lib/kr-proxy-provisioned ]; then
    echo "[kr-proxy] Already provisioned, skipping."
    # Ensure WireGuard is up on reboot (SPOT instances restart)
    systemctl start wg-quick@wg-kr 2>/dev/null || true
    exit 0
fi

# ── System packages ──────────────────────────────────────────────────────────

apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    wireguard-tools \
    linux-headers-$(uname -r) 2>/dev/null || true

# ── WireGuard kernel module ──────────────────────────────────────────────────

modprobe wireguard 2>/dev/null || true
echo "wireguard" >> /etc/modules-load.d/wireguard.conf

# ── IP forwarding ────────────────────────────────────────────────────────────

cat > /etc/sysctl.d/99-kr-proxy.conf << 'EOF'
net.ipv4.ip_forward = 1
EOF
sysctl -p /etc/sysctl.d/99-kr-proxy.conf

# ── Generate WireGuard keypair ───────────────────────────────────────────────

mkdir -p /etc/wireguard
chmod 700 /etc/wireguard

if [ ! -f /etc/wireguard/private.key ]; then
    wg genkey > /etc/wireguard/private.key
    chmod 600 /etc/wireguard/private.key
    cat /etc/wireguard/private.key | wg pubkey > /etc/wireguard/public.key
    echo "[kr-proxy] WireGuard keypair generated"
fi

PRIVATE_KEY=$(cat /etc/wireguard/private.key)
PUBLIC_KEY=$(cat /etc/wireguard/public.key)

echo "[kr-proxy] ============================================"
echo "[kr-proxy] WireGuard PUBLIC KEY: ${PUBLIC_KEY}"
echo "[kr-proxy] ============================================"
echo "[kr-proxy] Use this key as the peer public-key on MikroTik."

# ── Detect primary network interface ─────────────────────────────────────────

PRIMARY_IF=$(ip -o -4 route show default | awk '{print $5}' | head -1)
echo "[kr-proxy] Primary interface: ${PRIMARY_IF}"

# ── WireGuard config ─────────────────────────────────────────────────────────
# MikroTik is the initiator (persistent-keepalive), so no Endpoint here.
# AllowedIPs: all private ranges that MikroTik LAN clients use.

cat > /etc/wireguard/wg-kr.conf << WGEOF
[Interface]
Address = 10.0.11.2/30
ListenPort = 51822
PrivateKey = ${PRIVATE_KEY}

PostUp = iptables -t nat -A POSTROUTING -s 10.0.0.0/8 -o ${PRIMARY_IF} -j MASQUERADE
PostUp = iptables -t nat -A POSTROUTING -s 192.168.0.0/16 -o ${PRIMARY_IF} -j MASQUERADE
PostUp = iptables -A FORWARD -i wg-kr -j ACCEPT
PostUp = iptables -A FORWARD -o wg-kr -m state --state RELATED,ESTABLISHED -j ACCEPT
PostUp = iptables -t mangle -A FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu
PostDown = iptables -t nat -D POSTROUTING -s 10.0.0.0/8 -o ${PRIMARY_IF} -j MASQUERADE
PostDown = iptables -t nat -D POSTROUTING -s 192.168.0.0/16 -o ${PRIMARY_IF} -j MASQUERADE
PostDown = iptables -D FORWARD -i wg-kr -j ACCEPT
PostDown = iptables -D FORWARD -o wg-kr -m state --state RELATED,ESTABLISHED -j ACCEPT
PostDown = iptables -t mangle -D FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu

# MikroTik peer — add public key after MikroTik wg-kr interface is created.
# Run: gcloud compute ssh kr-proxy --zone=asia-northeast3-a --command="sudo wg set wg-kr peer <MIKROTIK_PUBKEY> allowed-ips 10.0.0.0/8,192.168.0.0/16"
# Then: sudo wg-quick save wg-kr
WGEOF

chmod 600 /etc/wireguard/wg-kr.conf

# ── Enable and start WireGuard ───────────────────────────────────────────────

systemctl enable wg-quick@wg-kr
systemctl start wg-quick@wg-kr

echo "[kr-proxy] WireGuard interface wg-kr is UP"
wg show wg-kr

# ── Mark provisioned ─────────────────────────────────────────────────────────

touch /var/lib/kr-proxy-provisioned
echo "[kr-proxy] Provisioning complete at $(date)"
