#!/usr/bin/env bash
# =============================================================================
# Flutter Dashboard Web Deploy
# Restarts the flutter-dashboard deployment to trigger init container
# which fetches the latest web build from GCS.
# Usage: sudo ./flutter-deploy-web.sh
# =============================================================================
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}"
NAMESPACE="shinbee"
DEPLOYMENT="flutter-dashboard"

echo "Restarting ${DEPLOYMENT} in namespace ${NAMESPACE}..."
kubectl --kubeconfig="${KUBECONFIG}" -n "${NAMESPACE}" \
  rollout restart deployment/"${DEPLOYMENT}"

echo "Waiting for rollout to complete..."
kubectl --kubeconfig="${KUBECONFIG}" -n "${NAMESPACE}" \
  rollout status deployment/"${DEPLOYMENT}" --timeout=120s

echo "Done. Dashboard deployment restarted with latest web build."
