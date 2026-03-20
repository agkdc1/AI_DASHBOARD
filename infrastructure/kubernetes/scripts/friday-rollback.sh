#!/usr/bin/env bash
# friday-rollback.sh — Rollback K8s fax migration to Docker on Pi
#
# Run from Pi as root (or with sudo).
# Reverses everything done by friday-migrate.sh.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
KC="KUBECONFIG=/etc/rancher/k3s/k3s.yaml kubectl"

echo "========================================"
echo "  SHINBEE Friday Rollback"
echo "  $(date)"
echo "========================================"

echo ""
echo "Step 1: Scale down K8s fax workloads..."
eval $KC -n fax-system scale deployment/asterisk --replicas=0 2>/dev/null || true
eval $KC -n fax-system scale deployment/mail2fax --replicas=0 2>/dev/null || true
echo "  Waiting for pods to terminate..."
sleep 10
eval $KC -n fax-system get pods 2>/dev/null || true

echo ""
echo "Step 2: Re-add Pi IP 10.0.0.254..."
# Remove any existing VLAN90 address
ip addr del 10.0.7.254/24 dev eth0 2>/dev/null || true
# Add VLAN10 address
ip addr add 10.0.0.254/23 dev eth0 2>/dev/null || true
echo "  Pi IP: $(ip -4 addr show eth0 | grep 'inet ' | awk '{print $2}')"

echo ""
echo "Step 3: Move Pi cable from ether4 → ether2 (VLAN10)."
read -p "Press Enter when cable is moved..."

echo ""
echo "Step 4: Start Docker fax stack..."
cd "${REPO_ROOT}/services/fax"
sg docker -c "docker compose up -d asterisk-headless faxapi mail2fax"
echo "  Waiting for containers..."
sleep 10
sg docker -c "docker compose ps"

echo ""
echo "Step 5: Restart nginx proxy..."
systemctl enable nginx shinbee-proxy-refresh.timer 2>/dev/null || true
systemctl start nginx shinbee-proxy-refresh.timer 2>/dev/null || true
echo "  nginx status: $(systemctl is-active nginx)"

echo ""
echo "Step 6: Apply MikroTik rollback..."
echo "  Apply: ${REPO_ROOT}/system/network/MIKROTIC_ROLLBACK.rsc"
read -p "Press Enter when MikroTik rollback is applied..."

echo ""
echo "Step 7: Revert AI assistant faxapi URL..."
# Restore the original faxapi URL
eval $KC -n shinbee set env deployment/ai-assistant AI_FAXAPI_URL=http://10.0.0.254:8010 2>/dev/null || true

echo ""
echo "Step 8: Verify..."
echo "  Docker containers:"
sg docker -c "docker compose ps"
echo ""
echo "  Asterisk:"
sg docker -c "docker compose exec asterisk-headless asterisk -rx 'core show uptime'" 2>/dev/null || echo "  (not ready yet)"
echo ""
echo "  Faxapi:"
curl -sS http://10.0.0.254:8010/health 2>/dev/null || echo "  (not ready yet)"

echo ""
echo "========================================"
echo "  Rollback complete!"
echo "  Manual verification:"
echo "  [ ] Inbound call"
echo "  [ ] Outbound call"
echo "  [ ] Fax test"
echo "  [ ] HTTPS works"
echo "========================================"
