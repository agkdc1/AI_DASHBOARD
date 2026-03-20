#!/usr/bin/env bash
# Create/update the openldap-seed ConfigMap from the generated LDIF file.
# Usage: sudo ./create-seed-configmap.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../../" && pwd)"
LDIF="${REPO_ROOT}/services/phone-provisioning/ldap-seed.ldif"

export KUBECONFIG="${KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}"

if [ ! -f "${LDIF}" ]; then
    echo "ERROR: ${LDIF} not found. Run: python3 services/phone-provisioning/generate.py"
    exit 1
fi

kubectl -n shinbee create configmap openldap-seed \
    --from-file=seed.ldif="${LDIF}" \
    --dry-run=client -o yaml | kubectl apply -f -

echo "ConfigMap openldap-seed updated."
