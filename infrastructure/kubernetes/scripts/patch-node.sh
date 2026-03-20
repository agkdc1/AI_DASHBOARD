#!/bin/bash
# Patch a provisioned worker node via Tailscale SSH.
# Fixes: registries.yaml, expand-rootfs, NTP, root password lock.
#
# Usage (from any Tailscale client):
#   bash patch-node.sh node-a5dd21
#   bash patch-node.sh node-a5dd21 node-b3cf42

set -euo pipefail

if [ $# -eq 0 ]; then
    echo "Usage: $0 <node-name> [node-name ...]"
    echo "  e.g. $0 node-a5dd21 node-b3cf42"
    exit 1
fi

for NODE in "$@"; do
    echo ""
    echo "=== Patching ${NODE} ==="
    echo ""

    # Run patch commands on the remote node
    tailscale ssh "root@${NODE}" -- bash -s << 'PATCH_EOF'
set -euo pipefail
export HOME="${HOME:-/root}"

echo "[patch] Starting patch on $(hostname) at $(date)"

# ── 1. Fix registries.yaml ─────────────────────────────────────────────
echo "[patch] Fixing registries.yaml..."
mkdir -p /etc/rancher/k3s
FETCHED=0
for attempt in $(seq 1 10); do
    if tailscale ssh root@k3s-control-0 -- cat /etc/rancher/k3s/registries.yaml < /dev/null > /tmp/registries.yaml 2>/dev/null; then
        if grep -q "^mirrors:" /tmp/registries.yaml 2>/dev/null; then
            mv /tmp/registries.yaml /etc/rancher/k3s/registries.yaml
            chmod 600 /etc/rancher/k3s/registries.yaml
            echo "[patch] registries.yaml OK (attempt ${attempt})"
            FETCHED=1
            break
        fi
    fi
    rm -f /tmp/registries.yaml
    echo "[patch] retrying (${attempt}/10)..."
    sleep 5
done
if [ "${FETCHED}" -ne 1 ]; then
    echo "[patch] ERROR: Could not fetch registries.yaml"
    exit 1
fi

# ── 2. Fix expand-rootfs.sh ────────────────────────────────────────────
echo "[patch] Updating expand-rootfs.sh..."
cat > /usr/local/bin/expand-rootfs.sh << 'EXPAND_EOF'
#!/bin/bash
set -e
ROOT_DEV=$(findmnt -n -o SOURCE /)
DISK_DEV="/dev/$(lsblk -ndo PKNAME "${ROOT_DEV}" | head -1)"
PART_NUM=$(echo "${ROOT_DEV}" | grep -oE '[0-9]+$')

if [ -b "${DISK_DEV}" ] && [ -n "${PART_NUM}" ]; then
    echo ", +" | sfdisk --no-reread -N "${PART_NUM}" "${DISK_DEV}" 2>/dev/null || true
    partprobe "${DISK_DEV}" 2>/dev/null || true
    resize2fs "${ROOT_DEV}" 2>/dev/null || true
fi

# Only disable once partition uses >90% of the disk
DISK_SIZE=$(lsblk -bndo SIZE "${DISK_DEV}")
PART_SIZE=$(lsblk -bndo SIZE "${ROOT_DEV}")
if [ -n "${DISK_SIZE}" ] && [ -n "${PART_SIZE}" ] && [ "${DISK_SIZE}" -gt 0 ]; then
    USAGE=$((PART_SIZE * 100 / DISK_SIZE))
    if [ "${USAGE}" -ge 90 ]; then
        systemctl disable expand-rootfs.service
    fi
fi
EXPAND_EOF
chmod +x /usr/local/bin/expand-rootfs.sh

# Re-enable the service (may have been disabled prematurely on USB)
systemctl enable expand-rootfs.service 2>/dev/null || true

# Run it now
echo "[patch] Running expand-rootfs..."
/usr/local/bin/expand-rootfs.sh || true

# Show result
ROOT_DEV=$(findmnt -n -o SOURCE /)
echo "[patch] Root partition: $(lsblk -no SIZE "${ROOT_DEV}" | tr -d ' ')"

# ── 3. Fix NTP sync ────────────────────────────────────────────────────
# systemd-timesyncd is a separate package on Debian Bookworm (not in systemd-sysv)
if ! dpkg -l systemd-timesyncd 2>/dev/null | grep -q '^ii'; then
    echo "[patch] Installing systemd-timesyncd package..."
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq systemd-timesyncd
fi

echo "[patch] Configuring NTP servers..."
cat > /etc/systemd/timesyncd.conf << 'NTP_CONF'
[Time]
NTP=time.google.com time.cloudflare.com
FallbackNTP=0.debian.pool.ntp.org 1.debian.pool.ntp.org 2.debian.pool.ntp.org
NTP_CONF
systemctl enable systemd-timesyncd 2>/dev/null || true
systemctl restart systemd-timesyncd
timedatectl set-ntp true

# Wait for clock sync (up to 30s)
for attempt in $(seq 1 15); do
    if timedatectl show -p NTPSynchronized --value 2>/dev/null | grep -q yes; then
        echo "[patch] Clock synced via NTP"
        break
    fi
    sleep 2
done
timedatectl status | grep -E 'Local time|NTP|synchronized' || true

# ── 4. Lock root password ──────────────────────────────────────────────
echo "[patch] Locking root password..."
passwd -l root 2>/dev/null || true

# ── 5. Restart k3s-agent to pick up registries.yaml ────────────────────
echo "[patch] Restarting k3s-agent..."
systemctl restart k3s-agent
sleep 10

# Check for node password rejection (happens when node was reflashed)
if journalctl -u k3s-agent --no-pager -n 20 2>/dev/null | grep -q "Node password rejected"; then
    NODE_NAME=$(hostname)
    echo "[patch] Node password rejected — cleaning up stale registration for ${NODE_NAME}..."
    tailscale ssh root@k3s-control-0 -- k3s kubectl delete node "${NODE_NAME}" < /dev/null 2>&1 || true
    rm -f /etc/rancher/node/password
    rm -f /var/lib/rancher/k3s/agent/client-ca.crt
    rm -f /var/lib/rancher/k3s/agent/client-kubelet.crt
    rm -f /var/lib/rancher/k3s/agent/client-kubelet.key
    rm -f /var/lib/rancher/k3s/agent/serving-kubelet.crt
    rm -f /var/lib/rancher/k3s/agent/serving-kubelet.key
    echo "[patch] Restarting k3s-agent with clean state..."
    systemctl restart k3s-agent
    sleep 10
fi

if systemctl is-active --quiet k3s-agent; then
    echo "[patch] k3s-agent running"
else
    echo "[patch] WARNING: k3s-agent not running"
    journalctl -u k3s-agent --no-pager -n 10 || true
fi

echo "[patch] Done at $(date)"
PATCH_EOF

    echo "=== ${NODE} patched ==="
done

echo ""
echo "Verify: tailscale ssh root@k3s-control-0 -- k3s kubectl get nodes"
