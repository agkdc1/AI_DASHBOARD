#!/usr/bin/env bash
# setup-rakuten-proxy.sh — Install and configure Squid forward proxy on k3s-control-0
# for routing Rakuten API traffic through a static IP.
#
# Usage: Run via Tailscale SSH on k3s-control-0:
#   tailscale ssh root@k3s-control-0 < setup-rakuten-proxy.sh
#
# Or copy and run:
#   scp setup-rakuten-proxy.sh root@k3s-control-0:/tmp/
#   tailscale ssh root@k3s-control-0 bash /tmp/setup-rakuten-proxy.sh

set -euo pipefail

echo "=== Installing Squid forward proxy ==="
apt-get update -qq
apt-get install -y -qq squid

echo "=== Configuring Squid ==="
cat > /etc/squid/squid.conf <<'EOF'
# Squid forward proxy for Rakuten API traffic
# Listens on Tailscale interface for K8s pod access

# Listen on all interfaces port 3128
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

# Allow Rakuten API from trusted networks
http_access allow rakuten_api tailscale_net
http_access allow rakuten_api k8s_pods
http_access allow rakuten_api k8s_services
http_access allow rakuten_api local_net
http_access allow rakuten_api localhost

# Deny everything else
http_access deny all

# Logging
access_log /var/log/squid/access.log squid
cache_log /var/log/squid/cache.log

# Performance
cache deny all
forwarded_for delete
via off

# Visible hostname
visible_hostname rakuten-proxy
EOF

echo "=== Restarting Squid ==="
systemctl enable squid
systemctl restart squid

echo "=== Verifying ==="
systemctl is-active squid
echo "Squid proxy running on port 3128"
echo "Static IP: $(curl -s ifconfig.me)"
echo
echo "=== Test connectivity ==="
echo "From a K8s pod, test with:"
echo '  curl -x http://$(tailscale ip -4 k3s-control-0):3128 https://api.rms.rakuten.co.jp/'
echo
echo "=== Done ==="
