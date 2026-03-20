#!/usr/bin/env bash
# worker-to-ethernet.sh — Connect K3s worker to VLAN10 Ethernet
#
# Run on worker via Tailscale SSH:
#   tailscale ssh root@<node> < worker-to-ethernet.sh
#
# This enables Ethernet DHCP alongside existing WiFi+Tailscale.
# K3s node-ip stays as Tailscale IP (GCP control plane needs it).
# MetalLB L2 advertisement works on any interface in the subnet.

set -euo pipefail

echo "=== Worker Ethernet Setup ==="

# Detect first Ethernet interface (not lo, not wlan, not tailscale)
ETH_IF=$(ip -o link show | awk -F': ' '{print $2}' | grep -E '^(eth|en)' | head -1)
if [ -z "$ETH_IF" ]; then
    echo "ERROR: No Ethernet interface found"
    exit 1
fi
echo "Ethernet interface: $ETH_IF"

# Check if cable is connected
CARRIER=$(cat "/sys/class/net/$ETH_IF/carrier" 2>/dev/null || echo "0")
if [ "$CARRIER" != "1" ]; then
    echo "WARNING: No cable detected on $ETH_IF (carrier=0)"
    echo "Plug in the Ethernet cable and re-run."
    exit 1
fi
echo "Cable detected (carrier=1)"

# Check if already has an IP in VLAN10 range
CURRENT_IP=$(ip -4 addr show "$ETH_IF" | grep -oP 'inet \K[0-9.]+' || true)
if [[ "$CURRENT_IP" == 10.0.* ]]; then
    echo "Already has VLAN10 IP: $CURRENT_IP"
    echo "Skipping DHCP setup."
    exit 0
fi

# Enable DHCP on the Ethernet interface via systemd-networkd
echo "Configuring DHCP on $ETH_IF..."
mkdir -p /etc/systemd/network

cat > "/etc/systemd/network/10-${ETH_IF}.network" << EOF
[Match]
Name=$ETH_IF

[Network]
DHCP=ipv4

[DHCPv4]
UseRoutes=false
UseDNS=false
RouteMetric=200
EOF

# Restart networkd to pick up new config
systemctl restart systemd-networkd

# Wait for DHCP lease (max 30s)
echo "Waiting for DHCP lease..."
for i in $(seq 1 30); do
    NEW_IP=$(ip -4 addr show "$ETH_IF" | grep -oP 'inet \K[0-9.]+' || true)
    if [[ "$NEW_IP" == 10.0.* ]]; then
        echo "Got VLAN10 IP: $NEW_IP"
        break
    fi
    sleep 1
done

if [[ ! "$NEW_IP" == 10.0.* ]]; then
    echo "ERROR: Did not get VLAN10 IP within 30s"
    echo "Check cable and MikroTik DHCP server."
    exit 1
fi

# Verify connectivity to gateway
echo "Verifying connectivity..."
if ping -c 2 -W 2 10.0.0.1 &>/dev/null; then
    echo "Gateway 10.0.0.1: reachable"
else
    echo "WARNING: Cannot reach gateway 10.0.0.1"
fi

# Verify Tailscale still works
TS_IP=$(tailscale ip -4 2>/dev/null || true)
echo "Tailscale IP: ${TS_IP:-UNKNOWN}"

echo ""
echo "=== Done ==="
echo "Ethernet: $ETH_IF = $NEW_IP"
echo "Tailscale: $TS_IP"
echo "K3s node-ip remains Tailscale IP (no change needed)"
