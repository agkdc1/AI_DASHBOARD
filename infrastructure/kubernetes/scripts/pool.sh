#!/usr/bin/env bash
# pool.sh — Bootstrap K3s cluster with all infrastructure components
#
# Uses Tailscale IPs for all cluster communication. The control plane
# (shinbee-pi) and workers (laptops) connect over the Tailscale VPN.
#
# Sequence:
# 1. Install K3s server on Pi (control plane only, tainted, Tailscale IP)
# 2. Wait for workers to join
# 3. Label workers
# 4. Install Longhorn (replicated storage)
# 5. Install nginx-ingress-controller (hostPort 80/443 on workers)
# 6. Install cert-manager + ClusterIssuers
# 7. Create shinbee namespace + priority classes
# 8. Run render-k8s-secrets.sh
#
# Traffic flow: Client → Pi (proxy) → Worker Tailscale IP:80/443 → Pod
# GCP control plane handles K3s API only — no data plane traffic.
#
# Usage: sudo ./pool.sh [--skip-k3s] [--workers N]
#
# Prerequisites:
#   - download.sh has been run
#   - Tailscale running on this Pi (tailscale ip -4 must return an IP)
#   - Workers booted from bootable.sh USBs and visible on tailnet

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CACHE_DIR="${SCRIPT_DIR}/../cache"
MANIFESTS_DIR="${SCRIPT_DIR}/../manifests"
CONFIG_DIR="${SCRIPT_DIR}/../config"

SKIP_K3S=false
EXPECTED_WORKERS=2

# Get this Pi's Tailscale IP (used for K3s bind/advertise/tls-san)
if ! command -v tailscale &>/dev/null; then
    echo "ERROR: tailscale not found. Install Tailscale first."
    exit 1
fi
PI_IP=$(tailscale ip -4 2>/dev/null) || true
if [ -z "${PI_IP}" ]; then
    echo "ERROR: Could not get Tailscale IPv4 address."
    echo "  Is Tailscale running? Check: sudo tailscale status"
    exit 1
fi
echo "Using Tailscale IP for control plane: ${PI_IP}"

for arg in "$@"; do
    case "$arg" in
        --skip-k3s) SKIP_K3S=true ;;
        --workers) shift; EXPECTED_WORKERS="$2" ;;
        --workers=*) EXPECTED_WORKERS="${arg#*=}" ;;
        *) ;;
    esac
done

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: Must run as root"
    exit 1
fi

export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

# ======================== STEP 1: K3s Server ========================
if [ "${SKIP_K3S}" != "true" ]; then
    echo "=== Step 1: Installing K3s server on Pi ==="

    # Copy airgap images
    mkdir -p /var/lib/rancher/k3s/agent/images/
    for f in "${CACHE_DIR}"/k3s/k3s-airgap-images-arm64.tar.*; do
        [ -f "$f" ] && cp "$f" /var/lib/rancher/k3s/agent/images/
    done

    # Install K3s binary
    if [ -f "${CACHE_DIR}/k3s/k3s-arm64" ]; then
        cp "${CACHE_DIR}/k3s/k3s-arm64" /usr/local/bin/k3s
        chmod +x /usr/local/bin/k3s
    fi

    # Install K3s server (no traefik, no servicelb — we use nginx-ingress + MetalLB)
    INSTALL_K3S_SKIP_DOWNLOAD=true \
    INSTALL_K3S_EXEC="server" \
    "${CACHE_DIR}/k3s/install.sh" \
        --disable traefik \
        --disable servicelb \
        --node-taint "node-role.kubernetes.io/control-plane:NoSchedule" \
        --node-taint "node-role.kubernetes.io/control-plane:NoExecute" \
        --tls-san "${PI_IP}" \
        --bind-address "${PI_IP}" \
        --advertise-address "${PI_IP}"

    echo "K3s server installed. Waiting for API server..."
    until kubectl get nodes &>/dev/null; do
        sleep 2
    done
    echo "K3s API server is ready"

    # Print join token for reference
    echo ""
    echo "Node join token: $(cat /var/lib/rancher/k3s/server/node-token)"
    echo ""
else
    echo "=== Step 1: Skipped (--skip-k3s) ==="
fi

# ======================== STEP 2: Wait for Workers ========================
echo "=== Step 2: Waiting for ${EXPECTED_WORKERS} worker(s) to join ==="

TIMEOUT=600
ELAPSED=0
while true; do
    READY_WORKERS=$(kubectl get nodes --no-headers 2>/dev/null | grep -v "control-plane" | grep -c "Ready" || echo 0)
    if [ "${READY_WORKERS}" -ge "${EXPECTED_WORKERS}" ]; then
        echo "All ${EXPECTED_WORKERS} worker(s) joined and Ready"
        break
    fi
    if [ "${ELAPSED}" -ge "${TIMEOUT}" ]; then
        echo "WARNING: Timeout waiting for workers (${READY_WORKERS}/${EXPECTED_WORKERS} ready)"
        echo "Continuing with available workers..."
        break
    fi
    echo "  Waiting... (${READY_WORKERS}/${EXPECTED_WORKERS} workers ready, ${ELAPSED}s elapsed)"
    sleep 10
    ELAPSED=$((ELAPSED + 10))
done

kubectl get nodes -o wide
echo ""

# ======================== STEP 3: Label Workers ========================
echo "=== Step 3: Labeling worker nodes ==="

# Read labels from nodes.yaml and apply
python3 -c "
import yaml, subprocess, sys
with open('${CONFIG_DIR}/nodes.yaml') as f:
    cfg = yaml.safe_load(f)
for node in cfg['nodes']:
    hostname = node['hostname']
    labels = node.get('labels', {})
    for key, val in labels.items():
        cmd = ['kubectl', 'label', 'node', hostname, f'{key}={val}', '--overwrite']
        print(f'  Labeling {hostname}: {key}={val}')
        subprocess.run(cmd, check=False)
" 2>/dev/null || {
    echo "  python3-yaml not available, labeling manually..."
    for node in $(kubectl get nodes --no-headers | grep -v "control-plane" | awk '{print $1}'); do
        kubectl label node "${node}" kubernetes.io/arch=amd64 --overwrite
        kubectl label node "${node}" node-role.kubernetes.io/worker="" --overwrite
        echo "  Labeled ${node}"
    done
}

echo ""

# ======================== STEP 4: Longhorn ========================
echo "=== Step 4: Installing Longhorn ==="

LONGHORN_CHART=$(ls "${CACHE_DIR}"/helm/longhorn-*.tgz 2>/dev/null | head -1)
if [ -z "${LONGHORN_CHART}" ]; then
    echo "ERROR: Longhorn chart not found in ${CACHE_DIR}/helm/"
    echo "  Run download.sh first"
    exit 1
fi

kubectl create namespace longhorn-system --dry-run=client -o yaml | kubectl apply -f -

helm upgrade --install longhorn "${LONGHORN_CHART}" \
    --namespace longhorn-system \
    --set defaultSettings.defaultDataPath=/var/lib/longhorn \
    --set defaultSettings.defaultReplicaCount=2 \
    --set defaultSettings.systemManagedComponentsNodeSelector="kubernetes\\.io/arch:amd64" \
    --wait --timeout 10m

echo "Longhorn installed. Waiting for pods..."
kubectl -n longhorn-system wait --for=condition=ready pod -l app=longhorn-manager --timeout=300s

# Apply custom StorageClass
kubectl apply -f "${MANIFESTS_DIR}/storage-class.yaml"
echo ""

# ======================== STEP 5: nginx-ingress-controller ========================
echo "=== Step 5: Installing nginx-ingress-controller (hostPort mode) ==="

# No MetalLB — workers bind hostPort 80/443 directly.
# Pi reverse-proxies to worker Tailscale IPs.

NGINX_CHART=$(ls "${CACHE_DIR}"/helm/ingress-nginx-*.tgz 2>/dev/null | head -1)
if [ -z "${NGINX_CHART}" ]; then
    echo "ERROR: ingress-nginx chart not found"
    exit 1
fi

kubectl create namespace ingress-nginx --dry-run=client -o yaml | kubectl apply -f -

helm upgrade --install ingress-nginx "${NGINX_CHART}" \
    --namespace ingress-nginx \
    -f "${MANIFESTS_DIR}/nginx-ingress-values.yaml" \
    --wait --timeout 5m

echo "nginx-ingress installed (hostPort 80/443 on workers)"
echo "Worker nodes with ingress pods:"
kubectl -n ingress-nginx get pods -o wide --no-headers 2>/dev/null | awk '{print "  " $7 " (" $1 ")"}'
echo ""

# ======================== STEP 6: cert-manager ========================
echo "=== Step 6: Installing cert-manager ==="

CERT_CHART=$(ls "${CACHE_DIR}"/helm/cert-manager-*.tgz 2>/dev/null | head -1)
if [ -z "${CERT_CHART}" ]; then
    echo "ERROR: cert-manager chart not found"
    exit 1
fi

kubectl create namespace cert-manager --dry-run=client -o yaml | kubectl apply -f -

helm upgrade --install cert-manager "${CERT_CHART}" \
    --namespace cert-manager \
    --set crds.enabled=true \
    --set nodeSelector."kubernetes\.io/arch"=amd64 \
    --wait --timeout 5m

echo "cert-manager installed. Waiting for webhook..."
kubectl -n cert-manager wait --for=condition=ready pod -l app.kubernetes.io/component=webhook --timeout=120s

# ClusterIssuers are applied after secrets are created (step 8)
echo ""

# ======================== STEP 7: Namespace + Priority Classes ========================
echo "=== Step 7: Creating shinbee namespace and priority classes ==="

kubectl apply -f "${MANIFESTS_DIR}/namespace.yaml"
kubectl apply -f "${MANIFESTS_DIR}/priority-classes.yaml"
echo ""

# ======================== STEP 8: Secrets ========================
echo "=== Step 8: Rendering K8s secrets from Vault ==="

"${SCRIPT_DIR}/render-k8s-secrets.sh" shinbee

# Now apply cert-manager ClusterIssuers (they reference the route53-credentials secret)
echo ""
echo "Applying cert-manager ClusterIssuers..."
kubectl apply -f "${MANIFESTS_DIR}/cert-manager/"
echo ""

# ======================== Summary ========================
echo ""
echo "========================================"
echo "  K3s Cluster Bootstrap Complete"
echo "========================================"
echo ""
echo "Nodes:"
kubectl get nodes -o wide
echo ""
echo "Namespaces:"
kubectl get namespaces
echo ""
echo "Storage Classes:"
kubectl get storageclass
echo ""
echo "Ingress Controller (hostPort):"
kubectl -n ingress-nginx get pods -o wide 2>/dev/null || echo "(not ready)"
echo ""
echo "cert-manager Issuers:"
kubectl get clusterissuer 2>/dev/null || echo "(not ready)"
echo ""
echo "Secrets in shinbee namespace:"
kubectl -n shinbee get secrets --no-headers | awk '{print "  - " $1}'
echo ""
echo "Traffic flow:"
echo "  Client → Pi (proxy) → Worker Tailscale IP:80/443 (hostPort) → Pod"
echo ""
echo "Worker Tailscale IPs for Pi proxy config:"
kubectl get nodes -l 'node.kubernetes.io/role!=entrypoint' -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.addresses[?(@.type=="InternalIP")].address}{"\n"}{end}' 2>/dev/null
echo ""
echo "Next steps:"
echo "  1. Verify all components: kubectl get pods -A"
echo "  2. Configure Pi reverse proxy → worker Tailscale IPs:80/443"
echo "  3. Deploy workloads: kubectl apply -f infrastructure/kubernetes/manifests/"
