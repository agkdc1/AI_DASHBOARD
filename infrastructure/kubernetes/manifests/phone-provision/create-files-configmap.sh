#!/usr/bin/env bash
# Create/update the phone-provision-files ConfigMap from generated XML files.
# Symlinks are resolved (copied as regular files) since ConfigMap doesn't support symlinks.
# Usage: sudo ./create-files-configmap.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../../" && pwd)"
OUTPUT_DIR="${REPO_ROOT}/services/phone-provisioning/output"

export KUBECONFIG="${KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}"

if [ ! -d "${OUTPUT_DIR}" ] || [ -z "$(ls -A "${OUTPUT_DIR}"/*.xml 2>/dev/null)" ]; then
    echo "ERROR: No XML files in ${OUTPUT_DIR}. Run: python3 services/phone-provisioning/generate.py"
    exit 1
fi

# Build --from-file args, resolving symlinks
FROM_ARGS=()
for f in "${OUTPUT_DIR}"/*.xml; do
    fname=$(basename "$f")
    # Resolve symlinks so ConfigMap gets actual content
    real=$(realpath "$f")
    FROM_ARGS+=(--from-file="${fname}=${real}")
done

kubectl -n shinbee create configmap phone-provision-files \
    "${FROM_ARGS[@]}" \
    --dry-run=client -o yaml | kubectl apply -f -

echo "ConfigMap phone-provision-files updated ($(ls "${OUTPUT_DIR}"/*.xml | wc -l) files)."
