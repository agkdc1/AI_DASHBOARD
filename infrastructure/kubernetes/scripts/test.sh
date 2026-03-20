#!/usr/bin/env bash
# test.sh — Deploy all workloads to a test namespace and verify
#
# Deploys to 'shinbee-test' namespace with staging cert-manager issuer.
# Runs comprehensive checks on all services.
#
# Usage: sudo ./test.sh [--cleanup]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MANIFESTS_DIR="${SCRIPT_DIR}/../manifests"
NAMESPACE="shinbee-test"

export KUBECONFIG="${KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}"

if [ "${1:-}" = "--cleanup" ]; then
    echo "=== Cleaning up test namespace ==="
    kubectl delete namespace "${NAMESPACE}" --ignore-not-found
    echo "Done."
    exit 0
fi

PASS=0
FAIL=0
CHECKS=()

check() {
    local name="$1" result="$2"
    if [ "${result}" = "ok" ]; then
        PASS=$((PASS + 1))
        CHECKS+=("  [PASS] ${name}")
    else
        FAIL=$((FAIL + 1))
        CHECKS+=("  [FAIL] ${name}: ${result}")
    fi
}

echo "=== Deploying to test namespace '${NAMESPACE}' ==="

# Create test namespace
kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

# Render secrets for test namespace
echo "Rendering secrets..."
"${SCRIPT_DIR}/render-k8s-secrets.sh" "${NAMESPACE}"

# Apply priority classes (cluster-scoped, idempotent)
kubectl apply -f "${MANIFESTS_DIR}/priority-classes.yaml"
kubectl apply -f "${MANIFESTS_DIR}/storage-class.yaml"

# Deploy all workloads (patched for test namespace)
echo ""
echo "Deploying workloads..."
for dir in inventree selenium-daemon rakuten-renewal omada; do
    echo "  Applying ${dir}..."
    for f in "${MANIFESTS_DIR}/${dir}"/*.yaml; do
        # Patch namespace and use staging issuer for test
        sed "s/namespace: shinbee$/namespace: ${NAMESPACE}/g; \
             s/letsencrypt-production/letsencrypt-staging/g" \
            "$f" | kubectl apply -f -
    done
done

# ======================== Wait for pods ========================
echo ""
echo "Waiting for pods to start (timeout: 10 min)..."

TIMEOUT=600
ELAPSED=0
while true; do
    TOTAL=$(kubectl -n "${NAMESPACE}" get pods --no-headers 2>/dev/null | wc -l)
    READY=$(kubectl -n "${NAMESPACE}" get pods --no-headers 2>/dev/null | grep -c "Running" || echo 0)
    if [ "${TOTAL}" -gt 0 ] && [ "${READY}" -ge "${TOTAL}" ]; then
        echo "All ${TOTAL} pods running"
        break
    fi
    if [ "${ELAPSED}" -ge "${TIMEOUT}" ]; then
        echo "WARNING: Timeout — some pods not ready"
        break
    fi
    echo "  ${READY}/${TOTAL} pods running (${ELAPSED}s)..."
    sleep 15
    ELAPSED=$((ELAPSED + 15))
done

echo ""
kubectl -n "${NAMESPACE}" get pods -o wide
echo ""

# ======================== Verification Checks ========================
echo "=== Running verification checks ==="

# Check 1: MySQL TCP connectivity
echo "Checking MySQL..."
MYSQL_POD=$(kubectl -n "${NAMESPACE}" get pod -l app.kubernetes.io/name=inventree-db -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [ -n "${MYSQL_POD}" ]; then
    if kubectl -n "${NAMESPACE}" exec "${MYSQL_POD}" -- mysqladmin ping -h localhost 2>/dev/null | grep -q "alive"; then
        check "MySQL ping" "ok"
    else
        check "MySQL ping" "mysqladmin ping failed"
    fi

    # Verify TCP listening on 3306
    if kubectl -n "${NAMESPACE}" exec "${MYSQL_POD}" -- sh -c "ss -tln | grep 3306" &>/dev/null; then
        check "MySQL TCP port 3306" "ok"
    else
        check "MySQL TCP port 3306" "not listening"
    fi
else
    check "MySQL pod" "not found"
fi

# Check 2: InvenTree server gunicorn HTTP
echo "Checking InvenTree server..."
SERVER_POD=$(kubectl -n "${NAMESPACE}" get pod -l app.kubernetes.io/name=inventree-server -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [ -n "${SERVER_POD}" ]; then
    if kubectl -n "${NAMESPACE}" exec "${SERVER_POD}" -- sh -c "ss -tln | grep 8000" &>/dev/null; then
        check "InvenTree gunicorn HTTP port 8000" "ok"
    else
        check "InvenTree gunicorn HTTP port 8000" "not listening"
    fi
else
    check "InvenTree server pod" "not found"
fi

# Check 3: InvenTree proxy
echo "Checking InvenTree proxy..."
PROXY_POD=$(kubectl -n "${NAMESPACE}" get pod -l app.kubernetes.io/name=inventree-proxy -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [ -n "${PROXY_POD}" ]; then
    HTTP_CODE=$(kubectl -n "${NAMESPACE}" exec "${PROXY_POD}" -- curl -so /dev/null -w '%{http_code}' http://localhost/ 2>/dev/null || echo "000")
    if [ "${HTTP_CODE}" -ge 200 ] && [ "${HTTP_CODE}" -lt 500 ]; then
        check "InvenTree proxy HTTP" "ok (${HTTP_CODE})"
    else
        check "InvenTree proxy HTTP" "got ${HTTP_CODE}"
    fi
else
    check "InvenTree proxy pod" "not found"
fi

# Check 4: Database migrations
echo "Checking migrations..."
if [ -n "${SERVER_POD}" ]; then
    if kubectl -n "${NAMESPACE}" logs "${SERVER_POD}" 2>/dev/null | grep -q "Running migrations"; then
        check "Database migrations ran" "ok"
    else
        check "Database migrations" "no migration log found (may still be running)"
    fi
fi

# Check 5: Static files
echo "Checking static files..."
if [ -n "${SERVER_POD}" ]; then
    if kubectl -n "${NAMESPACE}" exec "${SERVER_POD}" -- ls /home/inventree/data/static/css/ &>/dev/null; then
        check "Static files collected" "ok"
    else
        check "Static files" "not found (may still be collecting)"
    fi
fi

# Check 6: Selenium daemon health
echo "Checking selenium daemon..."
DAEMON_POD=$(kubectl -n "${NAMESPACE}" get pod -l app.kubernetes.io/name=selenium-daemon -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [ -n "${DAEMON_POD}" ]; then
    HEALTH=$(kubectl -n "${NAMESPACE}" exec "${DAEMON_POD}" -- curl -sf http://localhost:8020/health 2>/dev/null || echo "failed")
    if echo "${HEALTH}" | grep -qi "ok\|healthy\|status"; then
        check "Selenium daemon health" "ok"
    else
        check "Selenium daemon health" "${HEALTH}"
    fi
else
    check "Selenium daemon pod" "not found"
fi

# Check 7: Vault access from workers
echo "Checking Vault access..."
if [ -n "${DAEMON_POD}" ]; then
    VAULT_STATUS=$(kubectl -n "${NAMESPACE}" exec "${DAEMON_POD}" -- \
        curl -sf http://10.0.2.10:8200/v1/sys/health 2>/dev/null | jq -r '.sealed' 2>/dev/null || echo "unreachable")
    if [ "${VAULT_STATUS}" = "false" ]; then
        check "Vault access from worker" "ok (unsealed)"
    elif [ "${VAULT_STATUS}" = "true" ]; then
        check "Vault access from worker" "reachable but sealed"
    else
        check "Vault access from worker" "unreachable (check Vault listener binding)"
    fi
fi

# Check 8: Omada controller
echo "Checking Omada controller..."
OMADA_POD=$(kubectl -n "${NAMESPACE}" get pod -l app.kubernetes.io/name=omada-controller -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [ -n "${OMADA_POD}" ]; then
    OMADA_STATUS=$(kubectl -n "${NAMESPACE}" get pod "${OMADA_POD}" -o jsonpath='{.status.phase}' 2>/dev/null)
    if [ "${OMADA_STATUS}" = "Running" ]; then
        check "Omada controller" "ok (Running)"
    else
        check "Omada controller" "status: ${OMADA_STATUS}"
    fi
else
    check "Omada controller pod" "not found"
fi

# Check 9: PVCs bound
echo "Checking PersistentVolumeClaims..."
UNBOUND=$(kubectl -n "${NAMESPACE}" get pvc --no-headers 2>/dev/null | grep -cv "Bound" || echo "0")
TOTAL_PVC=$(kubectl -n "${NAMESPACE}" get pvc --no-headers 2>/dev/null | wc -l)
if [ "${UNBOUND}" -eq 0 ] && [ "${TOTAL_PVC}" -gt 0 ]; then
    check "All PVCs bound (${TOTAL_PVC})" "ok"
else
    check "PVCs" "${UNBOUND} of ${TOTAL_PVC} not bound"
fi

# Check 10: Ingress / cert-manager
echo "Checking Ingress and TLS..."
INGRESS_IP=$(kubectl -n "${NAMESPACE}" get ingress -o jsonpath='{.items[0].status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "")
if [ -n "${INGRESS_IP}" ]; then
    check "Ingress assigned IP" "ok (${INGRESS_IP})"
else
    check "Ingress IP" "not assigned yet"
fi

CERT_READY=$(kubectl -n "${NAMESPACE}" get certificate -o jsonpath='{.items[0].status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || echo "")
if [ "${CERT_READY}" = "True" ]; then
    check "TLS certificate (staging)" "ok"
else
    check "TLS certificate" "not ready (staging issuer may take a few minutes)"
fi

# ======================== Report ========================
echo ""
echo "========================================"
echo "  Test Verification Report"
echo "========================================"
echo ""
for c in "${CHECKS[@]}"; do
    echo "${c}"
done
echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
echo ""

if [ "${FAIL}" -gt 0 ]; then
    echo "Some checks failed. Review pod logs:"
    echo "  kubectl -n ${NAMESPACE} logs <pod-name>"
    echo "  kubectl -n ${NAMESPACE} describe pod <pod-name>"
    echo ""
fi

echo "Cleanup when done:"
echo "  $0 --cleanup"
