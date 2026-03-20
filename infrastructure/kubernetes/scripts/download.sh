#!/usr/bin/env bash
# download.sh — Pre-fetch all artifacts for air-gapped K3s cluster deployment
#
# Downloads K3s binaries, Helm charts, and container images
# into infrastructure/kubernetes/cache/ for offline provisioning.
#
# Usage: ./download.sh [--skip-images]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CACHE_DIR="${SCRIPT_DIR}/../cache"

K3S_VERSION="v1.31.4+k3s1"
LONGHORN_VERSION="1.7.2"
METALLB_VERSION="0.14.9"
CERT_MANAGER_VERSION="v1.16.3"
NGINX_INGRESS_VERSION="4.12.1"

SKIP_IMAGES=false

for arg in "$@"; do
    case "$arg" in
        --skip-images) SKIP_IMAGES=true ;;
        *) echo "Unknown option: $arg"; exit 1 ;;
    esac
done

mkdir -p "${CACHE_DIR}"/{k3s,helm,images}

echo "=== Downloading K3s artifacts ==="

# K3s server binary (ARM64 for Pi control plane)
echo "Downloading K3s server (arm64)..."
curl -sfL -o "${CACHE_DIR}/k3s/k3s-arm64" \
    "https://github.com/k3s-io/k3s/releases/download/${K3S_VERSION}/k3s-arm64"
chmod +x "${CACHE_DIR}/k3s/k3s-arm64"

# K3s agent binary (amd64 for ThinkCentre workers)
echo "Downloading K3s agent (amd64)..."
curl -sfL -o "${CACHE_DIR}/k3s/k3s-amd64" \
    "https://github.com/k3s-io/k3s/releases/download/${K3S_VERSION}/k3s"
chmod +x "${CACHE_DIR}/k3s/k3s-amd64"

# K3s install script
echo "Downloading K3s install script..."
curl -sfL -o "${CACHE_DIR}/k3s/install.sh" \
    "https://get.k3s.io"
chmod +x "${CACHE_DIR}/k3s/install.sh"

# K3s airgap images
echo "Downloading K3s airgap images (arm64)..."
curl -sfL -o "${CACHE_DIR}/k3s/k3s-airgap-images-arm64.tar.zst" \
    "https://github.com/k3s-io/k3s/releases/download/${K3S_VERSION}/k3s-airgap-images-arm64.tar.zst" || \
curl -sfL -o "${CACHE_DIR}/k3s/k3s-airgap-images-arm64.tar.gz" \
    "https://github.com/k3s-io/k3s/releases/download/${K3S_VERSION}/k3s-airgap-images-arm64.tar.gz"

echo "Downloading K3s airgap images (amd64)..."
curl -sfL -o "${CACHE_DIR}/k3s/k3s-airgap-images-amd64.tar.zst" \
    "https://github.com/k3s-io/k3s/releases/download/${K3S_VERSION}/k3s-airgap-images-amd64.tar.zst" || \
curl -sfL -o "${CACHE_DIR}/k3s/k3s-airgap-images-amd64.tar.gz" \
    "https://github.com/k3s-io/k3s/releases/download/${K3S_VERSION}/k3s-airgap-images-amd64.tar.gz"

echo ""
echo "=== Downloading Helm charts ==="

# Longhorn
echo "Downloading Longhorn chart v${LONGHORN_VERSION}..."
helm repo add longhorn https://charts.longhorn.io 2>/dev/null || true
helm repo update longhorn
helm pull longhorn/longhorn --version "${LONGHORN_VERSION}" -d "${CACHE_DIR}/helm/"

# MetalLB
echo "Downloading MetalLB chart v${METALLB_VERSION}..."
helm repo add metallb https://metallb.github.io/metallb 2>/dev/null || true
helm repo update metallb
helm pull metallb/metallb --version "${METALLB_VERSION}" -d "${CACHE_DIR}/helm/"

# cert-manager
echo "Downloading cert-manager chart ${CERT_MANAGER_VERSION}..."
helm repo add jetstack https://charts.jetstack.io 2>/dev/null || true
helm repo update jetstack
helm pull jetstack/cert-manager --version "${CERT_MANAGER_VERSION}" -d "${CACHE_DIR}/helm/"

# nginx-ingress-controller
echo "Downloading nginx-ingress chart v${NGINX_INGRESS_VERSION}..."
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx 2>/dev/null || true
helm repo update ingress-nginx
helm pull ingress-nginx/ingress-nginx --version "${NGINX_INGRESS_VERSION}" -d "${CACHE_DIR}/helm/"

if [ "${SKIP_IMAGES}" != "true" ]; then
    echo ""
    echo "=== Pulling application container images (amd64) ==="

    IMAGES=(
        "mysql:8.0"
        "inventree/inventree:stable"
        "nginx:1.25-alpine"
        "mbentley/omada-controller:5.15"
        "python:3.12-slim"
    )

    for img in "${IMAGES[@]}"; do
        echo "Pulling ${img}..."
        docker pull --platform linux/amd64 "${img}" 2>/dev/null || \
            echo "WARNING: Could not pull ${img} (may need x86 Docker or --skip-images)"
    done

    echo "Saving images to tarball..."
    docker save "${IMAGES[@]}" -o "${CACHE_DIR}/images/app-images-amd64.tar" 2>/dev/null || \
        echo "WARNING: Could not save images (docker save requires all images to be present)"
fi

echo ""
echo "=== Download complete ==="
echo ""
echo "Cache contents:"
du -sh "${CACHE_DIR}"/*/ 2>/dev/null || true
echo ""
echo "Total cache size: $(du -sh "${CACHE_DIR}" | awk '{print $1}')"
