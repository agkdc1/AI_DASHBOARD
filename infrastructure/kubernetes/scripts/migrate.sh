#!/usr/bin/env bash
# migrate.sh — Final migration cutover from Docker on Pi to K8s cluster
#
# Sequence:
# 1. Pre-flight checks (K8s healthy, Vault reachable, Docker running)
# 2. mysqldump from Docker → import to K8s MySQL
# 3. rsync InvenTree data (static, media, plugins) → K8s PVC
# 4. Copy selenium state → K8s PVC
# 5. Stop Docker stacks on Pi
# 6. Deploy all K8s workloads
# 7. Update DNS/port forwarding to MetalLB IP
# 8. Monitor and verify
#
# Usage: sudo ./migrate.sh [--dry-run] [--skip-data] [--rollback]
#
# Rollback: sudo ./migrate.sh --rollback

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MANIFESTS_DIR="${SCRIPT_DIR}/../manifests"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
NAMESPACE="shinbee"

export KUBECONFIG="${KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}"

DRY_RUN=false
SKIP_DATA=false
ROLLBACK=false

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        --skip-data) SKIP_DATA=true ;;
        --rollback) ROLLBACK=true ;;
        *) echo "Unknown option: $arg"; exit 1 ;;
    esac
done

log() { echo "[$(date '+%H:%M:%S')] $*"; }

# ======================== ROLLBACK ========================
if [ "${ROLLBACK}" = "true" ]; then
    log "=== ROLLBACK: Restoring Docker services on Pi ==="

    log "Scaling down K8s workloads..."
    for deploy in inventree-server inventree-worker inventree-proxy selenium-daemon rakuten-renewal omada-controller; do
        kubectl -n "${NAMESPACE}" scale deployment "${deploy}" --replicas=0 2>/dev/null || true
    done
    kubectl -n "${NAMESPACE}" scale statefulset inventree-db --replicas=0 2>/dev/null || true

    log "Starting Docker stacks..."
    cd "${REPO_ROOT}/services/inventory/shinbee-deploy"
    sg docker -c "docker compose up -d"

    cd "${REPO_ROOT}/services/selenium-daemon"
    sg docker -c "docker compose up -d"

    log ""
    log "=== ROLLBACK COMPLETE ==="
    log "Docker services restored. Update DNS/port forwarding back to Pi IP."
    log "  1. Update router NAT to forward 80/443 to Pi"
    log "  2. Update Route53 A records if changed"
    log "  3. Verify: curl -k https://api.your-domain.com/api/"
    exit 0
fi

# ======================== PRE-FLIGHT ========================
log "=== Pre-flight checks ==="

# Check K8s cluster
if ! kubectl get nodes &>/dev/null; then
    log "ERROR: Cannot reach K8s API server"
    exit 1
fi
READY_NODES=$(kubectl get nodes --no-headers | grep -c "Ready")
log "  K8s cluster: ${READY_NODES} nodes ready"

# Check Vault
VAULT_HEALTH=$(curl -sf http://127.0.0.1:8200/v1/sys/health 2>/dev/null | jq -r '.sealed' || echo "error")
if [ "${VAULT_HEALTH}" = "false" ]; then
    log "  Vault: unsealed and healthy"
else
    log "  WARNING: Vault may not be healthy (sealed=${VAULT_HEALTH})"
fi

# Check Docker services running
INVENTREE_DB_RUNNING=$(sg docker -c "docker ps --filter name=inventree-db --format '{{.Status}}'" 2>/dev/null || echo "not running")
log "  Docker inventree-db: ${INVENTREE_DB_RUNNING}"

# Check K8s namespace and secrets exist
if ! kubectl get namespace "${NAMESPACE}" &>/dev/null; then
    log "ERROR: Namespace '${NAMESPACE}' not found. Run pool.sh first."
    exit 1
fi

SECRET_COUNT=$(kubectl -n "${NAMESPACE}" get secrets --no-headers 2>/dev/null | wc -l)
log "  K8s secrets: ${SECRET_COUNT} in namespace ${NAMESPACE}"

if [ "${DRY_RUN}" = "true" ]; then
    log ""
    log "=== DRY RUN — no changes will be made ==="
    log ""
fi

# ======================== STEP 1: Database Migration ========================
if [ "${SKIP_DATA}" != "true" ]; then
    log ""
    log "=== Step 1: Database migration (mysqldump → K8s MySQL) ==="

    DUMP_FILE="/tmp/inventree-migration-$(date +%Y%m%d%H%M%S).sql"

    # Dump from Docker MySQL
    log "Dumping database from Docker..."
    MYSQL_PASSWORD=$(sg docker -c "docker exec shinbee-deploy-inventree-db-1 printenv MYSQL_ROOT_PASSWORD" 2>/dev/null || \
        cat "${REPO_ROOT}/services/inventory/shinbee-deploy/secrets/mysql_password")

    if [ "${DRY_RUN}" != "true" ]; then
        sg docker -c "docker exec shinbee-deploy-inventree-db-1 \
            mysqldump -u root -p'${MYSQL_PASSWORD}' \
            --single-transaction --routines --triggers \
            inventree" > "${DUMP_FILE}"
        log "  Dump size: $(du -h "${DUMP_FILE}" | awk '{print $1}')"
    else
        log "  [DRY RUN] Would dump inventree database to ${DUMP_FILE}"
    fi

    # Deploy MySQL to K8s first (if not already running)
    log "Ensuring K8s MySQL is running..."
    if [ "${DRY_RUN}" != "true" ]; then
        kubectl apply -f "${MANIFESTS_DIR}/inventree/service-db.yaml"
        kubectl apply -f "${MANIFESTS_DIR}/inventree/statefulset-db.yaml"
        kubectl -n "${NAMESPACE}" wait --for=condition=ready pod -l app.kubernetes.io/name=inventree-db --timeout=300s
    fi

    # Import to K8s MySQL
    log "Importing database to K8s MySQL..."
    K8S_MYSQL_POD=$(kubectl -n "${NAMESPACE}" get pod -l app.kubernetes.io/name=inventree-db -o jsonpath='{.items[0].metadata.name}')
    K8S_MYSQL_PASS=$(kubectl -n "${NAMESPACE}" get secret inventree-db-secret -o jsonpath='{.data.mysql-root-password}' | base64 -d)

    if [ "${DRY_RUN}" != "true" ]; then
        kubectl -n "${NAMESPACE}" exec -i "${K8S_MYSQL_POD}" -- \
            mysql -u root -p"${K8S_MYSQL_PASS}" inventree < "${DUMP_FILE}"
        log "  Database imported successfully"

        # Verify row count
        DOCKER_ROWS=$(sg docker -c "docker exec shinbee-deploy-inventree-db-1 \
            mysql -u root -p'${MYSQL_PASSWORD}' -N -e 'SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=\"inventree\"'" 2>/dev/null || echo "?")
        K8S_ROWS=$(kubectl -n "${NAMESPACE}" exec "${K8S_MYSQL_POD}" -- \
            mysql -u root -p"${K8S_MYSQL_PASS}" -N -e 'SELECT COUNT(*) FROM information_schema.tables WHERE table_schema="inventree"' 2>/dev/null || echo "?")
        log "  Table count — Docker: ${DOCKER_ROWS}, K8s: ${K8S_ROWS}"
    fi

    # ======================== STEP 2: rsync InvenTree data ========================
    log ""
    log "=== Step 2: Syncing InvenTree data (static, media, plugins, portal) ==="

    # Get a running pod to copy data into
    if [ "${DRY_RUN}" != "true" ]; then
        # Deploy server temporarily to get a pod with the PVC mounted
        kubectl apply -f "${MANIFESTS_DIR}/inventree/pvc.yaml"
        kubectl apply -f "${MANIFESTS_DIR}/inventree/service-server.yaml"
        kubectl apply -f "${MANIFESTS_DIR}/inventree/deployment-server.yaml"

        log "Waiting for InvenTree server pod..."
        kubectl -n "${NAMESPACE}" wait --for=condition=ready pod -l app.kubernetes.io/name=inventree-server --timeout=600s
        SERVER_POD=$(kubectl -n "${NAMESPACE}" get pod -l app.kubernetes.io/name=inventree-server -o jsonpath='{.items[0].metadata.name}')

        # Find Docker volume paths
        INVENTREE_DATA_VOL=$(sg docker -c "docker volume inspect shinbee-deploy_inventree-data --format '{{.Mountpoint}}'" 2>/dev/null || echo "")

        if [ -n "${INVENTREE_DATA_VOL}" ]; then
            log "  Copying media files..."
            # Use tar pipe to copy data into the pod
            tar -cf - -C "${INVENTREE_DATA_VOL}" media/ 2>/dev/null | \
                kubectl -n "${NAMESPACE}" exec -i "${SERVER_POD}" -- tar -xf - -C /home/inventree/data/ || \
                log "  WARNING: media copy had errors"

            log "  Static files will be regenerated by collectstatic"
        fi

        # Copy plugins
        log "  Copying plugins..."
        tar -cf - -C "${REPO_ROOT}/services/inventory" plugins/ 2>/dev/null | \
            kubectl -n "${NAMESPACE}" exec -i "${SERVER_POD}" -- tar -xf - -C /home/inventree/ || \
            log "  WARNING: plugin copy had errors"

        # Copy portal assets
        PORTAL_DIR="${REPO_ROOT}/services/inventory/portal"
        if [ -d "${PORTAL_DIR}" ]; then
            log "  Copying portal assets..."
            # We need a pod with the portal PVC - use the proxy
            kubectl apply -f "${MANIFESTS_DIR}/inventree/service-proxy.yaml"
            kubectl apply -f "${MANIFESTS_DIR}/inventree/deployment-proxy.yaml"
            kubectl -n "${NAMESPACE}" wait --for=condition=ready pod -l app.kubernetes.io/name=inventree-proxy --timeout=120s || true
            PROXY_POD=$(kubectl -n "${NAMESPACE}" get pod -l app.kubernetes.io/name=inventree-proxy -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
            if [ -n "${PROXY_POD}" ]; then
                tar -cf - -C "${PORTAL_DIR}" . 2>/dev/null | \
                    kubectl -n "${NAMESPACE}" exec -i "${PROXY_POD}" -- tar -xf - -C /srv/portal/ || \
                    log "  WARNING: portal copy had errors"
            fi
        fi
    fi

    # ======================== STEP 3: Selenium state ========================
    log ""
    log "=== Step 3: Copying selenium daemon state ==="

    if [ "${DRY_RUN}" != "true" ]; then
        # Deploy selenium daemon
        kubectl apply -f "${MANIFESTS_DIR}/selenium-daemon/"
        log "Waiting for selenium daemon pod..."
        kubectl -n "${NAMESPACE}" wait --for=condition=ready pod -l app.kubernetes.io/name=selenium-daemon --timeout=300s || true
        DAEMON_POD=$(kubectl -n "${NAMESPACE}" get pod -l app.kubernetes.io/name=selenium-daemon -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

        if [ -n "${DAEMON_POD}" ]; then
            # Copy cookies
            if [ -d "${REPO_ROOT}/services/selenium-daemon/cookies" ]; then
                log "  Copying cookies..."
                tar -cf - -C "${REPO_ROOT}/services/selenium-daemon" cookies/ | \
                    kubectl -n "${NAMESPACE}" exec -i "${DAEMON_POD}" -- tar -xf - -C /app/ || true
            fi

            # Copy state.json
            if [ -f "${REPO_ROOT}/services/selenium-daemon/state.json" ]; then
                log "  Copying state.json..."
                kubectl -n "${NAMESPACE}" cp "${REPO_ROOT}/services/selenium-daemon/state.json" "${DAEMON_POD}:/app/state/state.json" || true
            fi
        fi
    fi

    rm -f "${DUMP_FILE}"
else
    log "=== Skipping data migration (--skip-data) ==="
fi

# ======================== STEP 4: Stop Docker services ========================
log ""
log "=== Step 4: Stopping Docker services on Pi ==="

if [ "${DRY_RUN}" != "true" ]; then
    log "Stopping InvenTree Docker stack..."
    cd "${REPO_ROOT}/services/inventory/shinbee-deploy"
    sg docker -c "docker compose down" || true

    log "Stopping selenium daemon Docker..."
    cd "${REPO_ROOT}/services/selenium-daemon"
    sg docker -c "docker compose down" || true

    # Note: Vault and FAX stack stay running on Pi
    log "  (Vault and FAX stack remain running on Pi)"
else
    log "  [DRY RUN] Would stop InvenTree and selenium Docker stacks"
fi

# ======================== STEP 5: Deploy all K8s workloads ========================
log ""
log "=== Step 5: Deploying all K8s workloads ==="

if [ "${DRY_RUN}" != "true" ]; then
    # Apply all manifests
    for dir in inventree selenium-daemon rakuten-renewal omada; do
        log "  Deploying ${dir}..."
        kubectl apply -f "${MANIFESTS_DIR}/${dir}/"
    done

    log "Waiting for all pods to be ready..."
    kubectl -n "${NAMESPACE}" wait --for=condition=ready pod --all --timeout=600s || {
        log "WARNING: Not all pods ready within timeout"
        kubectl -n "${NAMESPACE}" get pods
    }
else
    log "  [DRY RUN] Would deploy all workloads to namespace ${NAMESPACE}"
fi

# ======================== STEP 6: DNS Update ========================
log ""
log "=== Step 6: DNS / Port Forwarding Update ==="

INGRESS_IP=$(kubectl -n ingress-nginx get svc ingress-nginx-controller -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "")
OMADA_IP=$(kubectl -n "${NAMESPACE}" get svc omada-controller -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "")

log "  Ingress LoadBalancer IP: ${INGRESS_IP:-pending}"
log "  Omada LoadBalancer IP: ${OMADA_IP:-pending}"
log ""
log "  ACTION REQUIRED:"
log "  1. Update router NAT to forward ports 80/443 to ${INGRESS_IP:-<ingress-ip>}"
log "  2. Update Route53 A records for api.your-domain.com and portal.your-domain.com"
log "     (cert-manager handles this automatically if DNS-01 is working)"
log "  3. Update EAP 'Inform URL' to http://${OMADA_IP:-<omada-ip>}:29811/inform"

# ======================== STEP 7: Verify ========================
log ""
log "=== Step 7: Post-migration verification ==="

if [ "${DRY_RUN}" != "true" ]; then
    kubectl -n "${NAMESPACE}" get pods -o wide
    echo ""

    # Quick health checks
    SERVER_POD=$(kubectl -n "${NAMESPACE}" get pod -l app.kubernetes.io/name=inventree-server -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    if [ -n "${SERVER_POD}" ]; then
        log "InvenTree API check..."
        kubectl -n "${NAMESPACE}" exec "${SERVER_POD}" -- \
            python -c "import django; print('Django OK')" 2>/dev/null && log "  Django: OK" || log "  Django: FAILED"
    fi

    DAEMON_POD=$(kubectl -n "${NAMESPACE}" get pod -l app.kubernetes.io/name=selenium-daemon -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    if [ -n "${DAEMON_POD}" ]; then
        log "Selenium daemon check..."
        kubectl -n "${NAMESPACE}" exec "${DAEMON_POD}" -- \
            curl -sf http://localhost:8020/health 2>/dev/null && log "  Daemon: OK" || log "  Daemon: NOT READY"
    fi
fi

log ""
log "========================================"
log "  Migration Complete"
log "========================================"
log ""
log "Monitor for 24-48 hours. If issues arise:"
log "  sudo $0 --rollback"
log ""
log "FAX stack and Vault continue running on Pi (unchanged)."
