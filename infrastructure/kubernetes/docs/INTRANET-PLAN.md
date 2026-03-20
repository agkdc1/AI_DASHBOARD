# Intranet Dashboard Deployment Plan (Vikunja + Outline on K3s)

> **Status**: COMPLETE — deployed 2026-02-25
> **Last updated**: 2026-02-25
> **Author**: Claude Code
>
> **Note**: This plan was written before Phase 5 (Vault → GCP SM). References to Vault AppRoles and `vault kv put` below are historical. The actual deployment used GCP Secret Manager directly.

---

## Table of Contents

1. [Current State](#current-state)
2. [Target Architecture](#target-architecture)
3. [Pre-requisites Checklist](#pre-requisites-checklist)
4. [Phase 0: K3s Node Provisioning](#phase-0-k3s-node-provisioning)
5. [Phase 1: Vault + Config](#phase-1-vault--config)
6. [Phase 2: Kubernetes Manifests](#phase-2-kubernetes-manifests)
7. [Phase 3: download.sh Update](#phase-3-downloadsh-update)
8. [Deployment Procedure](#deployment-procedure)
9. [Verification](#verification)
10. [Manifest Conventions Reference](#manifest-conventions-reference)
11. [File-by-File Implementation Details](#file-by-file-implementation-details)

---

## Current State

### What exists
- K3s scripts are written: `bootable.sh`, `pool.sh`, `download.sh`, `render-k8s-secrets.sh`
- All existing K8s manifests are in `infrastructure/kubernetes/manifests/` (inventree, selenium-daemon, rakuten-renewal, omada)
- Infrastructure components defined: Longhorn, MetalLB, cert-manager, nginx-ingress
- `nodes.yaml` configured for 2 laptop workers (tailscale_name still empty)
- Vault AppRole system is live with policies for fax, inventree, admin, rakuten, daemon

### What does NOT exist yet
- **K3s cluster is not running** — no nodes provisioned, no K3s installed
- **No intranet manifests** — nothing in `infrastructure/kubernetes/manifests/intranet/`
- **No Vault secrets for intranet** — `secret/intranet/*` paths don't exist
- **No intranet AppRole** — no policy, no role
- **No GCP OAuth clients** for Vikunja/Outline
- **No DNS records** for `tasks.your-domain.com` / `wiki.your-domain.com`
- **No `intranet` section in `config.yaml`**

### Hardware
- **Control plane**: Raspberry Pi (aarch64, Debian Bookworm) — tainted NoSchedule+NoExecute, runs Vault/FAX only
- **Worker 1**: 6-core modern laptop (amd64) — over WiFi + Tailscale
- **Worker 2**: i3 2-core 12GB laptop (amd64) — over WiFi + Tailscale
- **Total worker RAM**: ~14GB+ combined, ~8.8GB headroom after existing workloads

---

## Target Architecture

```
                    Internet
                       |
                 [Router NAT]
                       |
             +-----------------+
             |   Pi (ARM64)    |
             |   K3s Server    |   Tailscale IP
             |   + Vault       |
             |   + FAX stack   |
             +-----------------+
                  /       \
   +-------------------+  +-------------------+
   | Laptop-1 (amd64)  |  | Laptop-2 (amd64)  |
   | K3s Agent          |  | K3s Agent          |
   | Tailscale VPN      |  | Tailscale VPN      |
   +-------------------+  +-------------------+

Namespace: shinbee                    Namespace: intranet
  inventree-db (StatefulSet)            intranet-db (StatefulSet, PG16)
  inventree-server (Deployment)         vikunja (Deployment)
  inventree-worker (Deployment)         outline (Deployment)
  inventree-proxy (Deployment)          redis (Deployment)
  selenium-daemon (Deployment)          minio (Deployment)
  rakuten-renewal (Deployment)
  omada-controller (Deployment)
```

### Resource Budget (new intranet namespace)

| Component | Requests (mem) | Limits (mem) | Requests (cpu) | Limits (cpu) |
|-----------|---------------|-------------|---------------|-------------|
| PostgreSQL 16 | 256Mi | 512Mi | 250m | 1 |
| Redis 7 | 64Mi | 128Mi | 50m | 250m |
| MinIO | 128Mi | 256Mi | 100m | 500m |
| Vikunja | 70Mi | 256Mi | 50m | 500m |
| Outline | 200Mi | 512Mi | 200m | 1 |
| **Total** | **718Mi** | **1664Mi** | **650m** | **3250m** |

---

## Pre-requisites Checklist

Before ANY deployment:

- [ ] **K3s cluster running** (Phase 0 below)
- [ ] **GCP Console**: Create 2 OAuth 2.0 client IDs
  - Vikunja: Authorized redirect URI `https://tasks.your-domain.com/auth/openid/google/callback`
  - Outline: Authorized redirect URI `https://wiki.your-domain.com/auth/google.callback`
  - Both: Authorized JS origins `https://tasks.your-domain.com`, `https://wiki.your-domain.com`
  - Both: Restrict to `your-domain.com` hosted domain
- [ ] **DNS**: A records pointing to MetalLB ingress VIP (same IP as `api.your-domain.com`)
  - `tasks.your-domain.com` → `<MetalLB VIP>`
  - `wiki.your-domain.com` → `<MetalLB VIP>`
- [ ] **Vault secrets created** (see Phase 1 for exact `vault kv put` commands)
- [ ] **Vault AppRole created** for `intranet`

---

## Phase 0: K3s Node Provisioning

> **THIS MUST BE DONE FIRST.** The intranet stack runs on K3s workers.

### Step 0.1: Pre-fetch artifacts
```bash
cd /home/pi/SHINBEE/infrastructure/kubernetes/scripts
./download.sh
```

### Step 0.2: Build bootable images for laptops
```bash
# Interactive — prompts for WiFi SSIDs, Tailscale auth key, device name
sudo ./bootable.sh laptop-1 --image-only    # Or /dev/sdX for direct write
sudo ./bootable.sh laptop-2 --image-only
```

After building:
```bash
# Write to USB/SSD
sudo dd if=../cache/images/laptop-1.img of=/dev/sdX bs=4M status=progress conv=fsync
sudo dd if=../cache/images/laptop-2.img of=/dev/sdY bs=4M status=progress conv=fsync
```

### Step 0.3: Boot laptops, verify Tailscale
```bash
tailscale ping laptop-1
tailscale ping laptop-2
```

### Step 0.4: Bootstrap K3s cluster
```bash
sudo ./pool.sh
```

This installs K3s server on Pi, waits for workers, installs Longhorn/MetalLB/nginx-ingress/cert-manager, creates `shinbee` namespace, renders secrets.

### Step 0.5: Deploy existing workloads (optional, can be done later)
```bash
kubectl apply -f infrastructure/kubernetes/manifests/inventree/
kubectl apply -f infrastructure/kubernetes/manifests/selenium-daemon/
kubectl apply -f infrastructure/kubernetes/manifests/omada/
kubectl apply -f infrastructure/kubernetes/manifests/rakuten-renewal/
```

### Step 0.6: Verify cluster
```bash
kubectl get nodes -o wide
kubectl get pods -A
kubectl -n shinbee get certificate   # TLS certs Ready
curl -sf https://api.your-domain.com/api/  # InvenTree responds
```

---

## Phase 1: Vault + Config

### 1.1: Add `intranet` section to `config.yaml`

Append after the `daemon` section (before or after `backup`):

```yaml
# -----------------------------------------------------------------------------
# Intranet Dashboard (Vikunja + Outline)
# -----------------------------------------------------------------------------
intranet:
  namespace: "intranet"

  vikunja:
    domain: "tasks.your-domain.com"
    image: "vikunja/vikunja:latest"
    port: 3456
    service_frontendurl: "https://tasks.your-domain.com"

  outline:
    domain: "wiki.your-domain.com"
    image: "outlinewiki/outline:latest"
    port: 3000
    url: "https://wiki.your-domain.com"
    file_storage: "s3"

  postgres:
    image: "postgres:16-alpine"
    port: 5432
    vikunja_db: "vikunja"
    vikunja_user: "vikunja"
    outline_db: "outline"
    outline_user: "outline"

  redis:
    image: "redis:7-alpine"
    port: 6379

  minio:
    image: "minio/minio:latest"
    port: 9000
    bucket: "outline-data"
```

### 1.2: Create Vault policy

**File: `Vault/policies/intranet.hcl`**
```hcl
path "secret/data/intranet/*" {
  capabilities = ["read"]
}

path "secret/metadata/intranet/*" {
  capabilities = ["list"]
}
```

### 1.3: Create Vault AppRole + store credentials

```bash
# Authenticate with recovery keys (root token is revoked)
# Use existing admin AppRole to create the intranet role

# Write policy
sg docker -c "docker exec vault vault policy write intranet /vault/policies/intranet.hcl"

# Create AppRole
sg docker -c "docker exec vault vault auth enable approle" 2>/dev/null || true
sg docker -c "docker exec vault vault write auth/approle/role/intranet \
    token_policies=intranet \
    token_ttl=1h \
    token_max_ttl=4h \
    secret_id_ttl=0"

# Get role-id and secret-id
ROLE_ID=$(sg docker -c "docker exec vault vault read -format=json auth/approle/role/intranet/role-id" | jq -r '.data.role_id')
SECRET_ID=$(sg docker -c "docker exec vault vault write -format=json -f auth/approle/role/intranet/secret-id" | jq -r '.data.secret_id')

# Store credentials
sudo tee /root/vault-approle-intranet-role-id <<< "$ROLE_ID"
sudo tee /root/vault-approle-intranet-secret-id <<< "$SECRET_ID"
sudo chmod 0400 /root/vault-approle-intranet-{role-id,secret-id}
```

### 1.4: Create Vault secrets

Generate passwords first:
```bash
PG_VIKUNJA_PW=$(openssl rand -base64 24)
PG_OUTLINE_PW=$(openssl rand -base64 24)
MINIO_ACCESS_KEY=$(openssl rand -hex 16)
MINIO_SECRET_KEY=$(openssl rand -base64 32)
OUTLINE_SECRET_KEY=$(openssl rand -hex 32)
OUTLINE_UTILS_SECRET=$(openssl rand -hex 32)
```

Store in Vault:
```bash
# Note: Vault kv put requires authentication.
# Use admin AppRole or unseal with recovery keys first.

sg docker -c "docker exec vault vault kv put secret/intranet/db \
    vikunja_password='$PG_VIKUNJA_PW' \
    outline_password='$PG_OUTLINE_PW'"

sg docker -c "docker exec vault vault kv put secret/intranet/vikunja_oauth \
    client_id='<FROM_GCP_CONSOLE>' \
    client_secret='<FROM_GCP_CONSOLE>'"

sg docker -c "docker exec vault vault kv put secret/intranet/outline_oauth \
    client_id='<FROM_GCP_CONSOLE>' \
    client_secret='<FROM_GCP_CONSOLE>'"

sg docker -c "docker exec vault vault kv put secret/intranet/outline \
    secret_key='$OUTLINE_SECRET_KEY' \
    utils_secret='$OUTLINE_UTILS_SECRET'"

sg docker -c "docker exec vault vault kv put secret/intranet/minio \
    access_key='$MINIO_ACCESS_KEY' \
    secret_key='$MINIO_SECRET_KEY'"
```

### 1.5: Extend `render-k8s-secrets.sh`

Add a new section at the end (before the cleanup section) to handle the `intranet` namespace. The script already takes a namespace argument (`$1`), so we need to handle the intranet namespace separately.

**Approach**: Add an `intranet` block that runs when `NAMESPACE=intranet` OR always (creating secrets in the `intranet` namespace regardless of the argument).

Recommended: Make the script accept multiple namespaces or add a conditional block:

```bash
# ---------- Intranet namespace secrets ----------
if [ "${NAMESPACE}" = "intranet" ] || [ "${NAMESPACE}" = "all" ]; then
    INTRANET_NS="intranet"
    kubectl get namespace "${INTRANET_NS}" &>/dev/null || kubectl create namespace "${INTRANET_NS}"

    echo "Creating intranet-db-secret..."
    PG_VIKUNJA_PW=$(vault_get "intranet/db" "vikunja_password")
    PG_OUTLINE_PW=$(vault_get "intranet/db" "outline_password")
    kubectl -n "${INTRANET_NS}" create secret generic intranet-db-secret \
        --from-literal=vikunja-password="${PG_VIKUNJA_PW}" \
        --from-literal=outline-password="${PG_OUTLINE_PW}" \
        --dry-run=client -o yaml | kubectl apply -f -

    echo "Creating vikunja-oauth-secret..."
    VIK_CLIENT_ID=$(vault_get "intranet/vikunja_oauth" "client_id")
    VIK_CLIENT_SECRET=$(vault_get "intranet/vikunja_oauth" "client_secret")
    kubectl -n "${INTRANET_NS}" create secret generic vikunja-oauth-secret \
        --from-literal=client-id="${VIK_CLIENT_ID}" \
        --from-literal=client-secret="${VIK_CLIENT_SECRET}" \
        --dry-run=client -o yaml | kubectl apply -f -

    echo "Creating outline-oauth-secret..."
    OUT_CLIENT_ID=$(vault_get "intranet/outline_oauth" "client_id")
    OUT_CLIENT_SECRET=$(vault_get "intranet/outline_oauth" "client_secret")
    kubectl -n "${INTRANET_NS}" create secret generic outline-oauth-secret \
        --from-literal=client-id="${OUT_CLIENT_ID}" \
        --from-literal=client-secret="${OUT_CLIENT_SECRET}" \
        --dry-run=client -o yaml | kubectl apply -f -

    echo "Creating outline-app-secret..."
    OUT_SECRET_KEY=$(vault_get "intranet/outline" "secret_key")
    OUT_UTILS_SECRET=$(vault_get "intranet/outline" "utils_secret")
    kubectl -n "${INTRANET_NS}" create secret generic outline-app-secret \
        --from-literal=secret-key="${OUT_SECRET_KEY}" \
        --from-literal=utils-secret="${OUT_UTILS_SECRET}" \
        --dry-run=client -o yaml | kubectl apply -f -

    echo "Creating outline-db-url secret..."
    # Outline requires a complete DATABASE_URL — K8s can't interpolate secrets into env values
    OUTLINE_DB_URL="postgres://outline:${PG_OUTLINE_PW}@intranet-db.intranet.svc.cluster.local:5432/outline?sslmode=disable"
    kubectl -n "${INTRANET_NS}" create secret generic outline-db-url \
        --from-literal=url="${OUTLINE_DB_URL}" \
        --dry-run=client -o yaml | kubectl apply -f -

    echo "Creating minio-secret..."
    MINIO_ACCESS=$(vault_get "intranet/minio" "access_key")
    MINIO_SECRET=$(vault_get "intranet/minio" "secret_key")
    kubectl -n "${INTRANET_NS}" create secret generic minio-secret \
        --from-literal=access-key="${MINIO_ACCESS}" \
        --from-literal=secret-key="${MINIO_SECRET}" \
        --dry-run=client -o yaml | kubectl apply -f -

    echo ""
    echo "Intranet secrets created:"
    kubectl -n "${INTRANET_NS}" get secrets --no-headers | awk '{print "  - " $1}'
fi
```

---

## Phase 2: Kubernetes Manifests

All files go in `infrastructure/kubernetes/manifests/intranet/`.

### Conventions (from existing manifests — MUST FOLLOW)

| Convention | Value | Source |
|-----------|-------|--------|
| Labels | `app.kubernetes.io/name`, `app.kubernetes.io/component`, `app.kubernetes.io/part-of: shinbee-intranet` | inventree manifests |
| nodeSelector | `kubernetes.io/arch: amd64` | all existing deployments |
| Priority classes | `shinbee-critical` (1000), `shinbee-high` (500), `shinbee-normal` (100) | `priority-classes.yaml` |
| Storage class | `longhorn` (2x replica, default) — use `longhorn-single` (1x) for intranet | `storage-class.yaml` |
| Ingress class | `nginx` | inventree ingress |
| Ingress annotations | `cert-manager.io/cluster-issuer: letsencrypt-production`, HSTS, ssl-redirect, proxy-body-size | inventree ingress |
| TZ env var | `Asia/Tokyo` | inventree-db |
| Probes | startup + readiness + liveness on all containers | inventree patterns |
| Strategy | `RollingUpdate` (maxUnavailable:0, maxSurge:1) for deployments | inventree-server |
| StatefulSet | `serviceName` matching headless service, `volumeClaimTemplates` | inventree-db |
| Service type | `ClusterIP` (default) | all services |
| Secrets | `--dry-run=client -o yaml \| kubectl apply -f -` pattern in render script | render-k8s-secrets.sh |

### File List (16 files)

```
infrastructure/kubernetes/manifests/intranet/
├── namespace.yaml
├── storage-class-single.yaml
├── pvc.yaml
├── configmap-initdb.yaml
├── statefulset-postgres.yaml
├── service-postgres.yaml
├── deployment-redis.yaml
├── service-redis.yaml
├── deployment-minio.yaml
├── service-minio.yaml
├── job-minio-bucket.yaml
├── deployment-vikunja.yaml
├── service-vikunja.yaml
├── deployment-outline.yaml
├── service-outline.yaml
└── ingress.yaml
```

---

## Phase 3: download.sh Update

Add to the `IMAGES` array:
```bash
IMAGES=(
    "mysql:8.0"
    "inventree/inventree:stable"
    "nginx:1.25-alpine"
    "mbentley/omada-controller:5.15"
    "python:3.12-slim"
    # Intranet stack
    "postgres:16-alpine"
    "redis:7-alpine"
    "minio/minio:latest"
    "vikunja/vikunja:latest"
    "outlinewiki/outline:latest"
)
```

---

## Deployment Procedure

After all pre-requisites are met and K3s cluster is running:

```bash
# 1. Render intranet secrets from Vault
sudo ./infrastructure/kubernetes/scripts/render-k8s-secrets.sh intranet

# 2. Apply manifests in dependency order
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
INTRANET=infrastructure/kubernetes/manifests/intranet

# Foundation
kubectl apply -f $INTRANET/namespace.yaml
kubectl apply -f $INTRANET/storage-class-single.yaml

# Database layer
kubectl apply -f $INTRANET/pvc.yaml
kubectl apply -f $INTRANET/configmap-initdb.yaml
kubectl apply -f $INTRANET/statefulset-postgres.yaml
kubectl apply -f $INTRANET/service-postgres.yaml

# Wait for PG ready
kubectl -n intranet wait --for=condition=ready pod -l app.kubernetes.io/name=intranet-db --timeout=300s

# Supporting services
kubectl apply -f $INTRANET/deployment-redis.yaml
kubectl apply -f $INTRANET/service-redis.yaml
kubectl apply -f $INTRANET/deployment-minio.yaml
kubectl apply -f $INTRANET/service-minio.yaml

# Wait for MinIO ready
kubectl -n intranet wait --for=condition=ready pod -l app.kubernetes.io/name=intranet-minio --timeout=120s

# Create MinIO bucket (one-time job)
kubectl apply -f $INTRANET/job-minio-bucket.yaml
kubectl -n intranet wait --for=condition=complete job/minio-create-bucket --timeout=60s

# Application layer
kubectl apply -f $INTRANET/deployment-vikunja.yaml
kubectl apply -f $INTRANET/service-vikunja.yaml
kubectl apply -f $INTRANET/deployment-outline.yaml
kubectl apply -f $INTRANET/service-outline.yaml

# Ingress (triggers cert-manager TLS provisioning)
kubectl apply -f $INTRANET/ingress.yaml
```

---

## Verification

```bash
# All pods running
kubectl -n intranet get pods -o wide

# TLS certificates issued
kubectl -n intranet get certificate

# Health checks
curl -sf https://tasks.your-domain.com/api/v1/info   # Vikunja health
curl -sf https://wiki.your-domain.com/                # Outline responds

# Google SSO login: open browser, verify redirect to accounts.google.com
```

---

## Manifest Conventions Reference

This section documents the exact patterns extracted from existing manifests so a new Claude Code session can produce consistent YAML.

### Labels (from `inventree/deployment-server.yaml`)
```yaml
metadata:
  labels:
    app.kubernetes.io/name: <resource-name>
    app.kubernetes.io/component: <component-type>  # database, server, cache, storage, app
    app.kubernetes.io/part-of: shinbee-intranet     # NOT "shinbee" — separate part-of for intranet
```

### Pod spec pattern (from `inventree/deployment-server.yaml`)
```yaml
spec:
  priorityClassName: shinbee-critical  # or shinbee-high, shinbee-normal
  nodeSelector:
    kubernetes.io/arch: amd64
  containers:
    - name: <container-name>
      image: <image>
      ports:
        - containerPort: <port>
          name: <port-name>
      env:
        - name: TZ
          value: Asia/Tokyo
      resources:
        requests:
          memory: <Mi>
          cpu: <m>
        limits:
          memory: <Mi>
          cpu: "<cores>"
```

### Probes (from `inventree/statefulset-db.yaml`)
```yaml
startupProbe:
  <probe-type>:
    ...
  initialDelaySeconds: 10
  periodSeconds: 5
  failureThreshold: 30
readinessProbe:
  <probe-type>:
    ...
  initialDelaySeconds: 10
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 10
livenessProbe:
  <probe-type>:
    ...
  initialDelaySeconds: 30
  periodSeconds: 10
  timeoutSeconds: 5
```

### Ingress (from `inventree/ingress.yaml`)
```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-production
    nginx.ingress.kubernetes.io/proxy-body-size: 100m
    nginx.ingress.kubernetes.io/proxy-read-timeout: "120"
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/hsts: "true"
    nginx.ingress.kubernetes.io/hsts-max-age: "31536000"
    nginx.ingress.kubernetes.io/hsts-include-subdomains: "true"
spec:
  ingressClassName: nginx
  tls:
    - hosts:
        - <domain>
      secretName: <tls-secret-name>
  rules:
    - host: <domain>
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: <service-name>
                port:
                  name: <port-name>
```

### StatefulSet volumeClaimTemplate (from `inventree/statefulset-db.yaml`)
```yaml
volumeClaimTemplates:
  - metadata:
      name: <data-volume-name>
    spec:
      accessModes:
        - ReadWriteOnce
      storageClassName: longhorn-single   # 1x replica for intranet
      resources:
        requests:
          storage: <size>
```

### Service (from `inventree/service-db.yaml`)
```yaml
apiVersion: v1
kind: Service
metadata:
  name: <service-name>
  namespace: intranet
  labels:
    app.kubernetes.io/name: <service-name>
    app.kubernetes.io/component: <component>
    app.kubernetes.io/part-of: shinbee-intranet
spec:
  type: ClusterIP
  selector:
    app.kubernetes.io/name: <pod-label>
  ports:
    - port: <port>
      targetPort: <container-port-name>
      protocol: TCP
      name: <port-name>
```

---

## File-by-File Implementation Details

### `namespace.yaml`
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: intranet
  labels:
    app.kubernetes.io/part-of: shinbee-intranet
```

### `storage-class-single.yaml`
```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: longhorn-single
provisioner: driver.longhorn.io
allowVolumeExpansion: true
reclaimPolicy: Retain
volumeBindingMode: Immediate
parameters:
  numberOfReplicas: "1"
  staleReplicaTimeout: "2880"
  fromBackup: ""
  fsType: ext4
```

### `pvc.yaml`
```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: redis-data
  namespace: intranet
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: longhorn-single
  resources:
    requests:
      storage: 256Mi
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: minio-data
  namespace: intranet
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: longhorn-single
  resources:
    requests:
      storage: 5Gi
```

### `configmap-initdb.yaml`
PostgreSQL init script that creates both databases and users on first start:
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: intranet-initdb
  namespace: intranet
  labels:
    app.kubernetes.io/part-of: shinbee-intranet
data:
  init.sh: |
    #!/bin/bash
    set -e
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
      CREATE USER vikunja WITH PASSWORD '${VIKUNJA_DB_PASSWORD}';
      CREATE DATABASE vikunja OWNER vikunja;
      CREATE USER outline WITH PASSWORD '${OUTLINE_DB_PASSWORD}';
      CREATE DATABASE outline OWNER outline;
    EOSQL
```

### `statefulset-postgres.yaml`
- Image: `postgres:16-alpine`
- Priority: `shinbee-critical`
- Resources: 256Mi req / 512Mi limit, 250m / 1 cpu
- Environment: `POSTGRES_USER=postgres`, `POSTGRES_PASSWORD` from `intranet-db-secret`
- `VIKUNJA_DB_PASSWORD` and `OUTLINE_DB_PASSWORD` also from `intranet-db-secret` (for init script)
- volumeClaimTemplate: 5Gi `longhorn-single`
- Init script mounted from `configmap-initdb` at `/docker-entrypoint-initdb.d/`
- Probes: `pg_isready -U postgres`

### `service-postgres.yaml`
- ClusterIP, port 5432, name `postgres`

### `deployment-redis.yaml`
- Image: `redis:7-alpine`
- Priority: `shinbee-normal`
- Resources: 64Mi req / 128Mi limit, 50m / 250m cpu
- Command: `redis-server --maxmemory 100mb --maxmemory-policy allkeys-lru`
- Volume: `redis-data` PVC mounted at `/data`
- Probes: `redis-cli ping`

### `service-redis.yaml`
- ClusterIP, port 6379, name `redis`

### `deployment-minio.yaml`
- Image: `minio/minio:latest`
- Priority: `shinbee-normal`
- Strategy: `Recreate` (single-writer for MinIO standalone)
- Resources: 128Mi req / 256Mi limit, 100m / 500m cpu
- Command: `minio server /data --console-address :9001`
- Env: `MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD` from `minio-secret`
- Volume: `minio-data` PVC mounted at `/data`
- Probes: HTTP GET `/minio/health/live` port 9000

### `service-minio.yaml`
- ClusterIP, port 9000, name `api`

### `job-minio-bucket.yaml`
One-time job to create the `outline-data` bucket:
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: minio-create-bucket
  namespace: intranet
spec:
  template:
    spec:
      nodeSelector:
        kubernetes.io/arch: amd64
      containers:
        - name: mc
          image: minio/minio:latest
          command:
            - /bin/sh
            - -c
            - |
              # MinIO client is bundled in the minio image as 'mc'
              # Wait for MinIO to be ready
              until mc alias set myminio http://intranet-minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"; do
                sleep 2
              done
              mc mb --ignore-existing myminio/outline-data
          env:
            - name: MINIO_ROOT_USER
              valueFrom:
                secretKeyRef:
                  name: minio-secret
                  key: access-key
            - name: MINIO_ROOT_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: minio-secret
                  key: secret-key
      restartPolicy: OnFailure
  backoffLimit: 5
```

**Note**: Verify that `minio/minio:latest` includes `mc` binary. If not, use `minio/mc:latest` image instead.

### `deployment-vikunja.yaml`
- Image: `vikunja/vikunja:latest`
- Priority: `shinbee-high`
- Resources: 70Mi req / 256Mi limit, 50m / 500m cpu
- Environment (all from env vars, following Vikunja v0.22+ config):
  ```
  VIKUNJA_DATABASE_TYPE=postgres
  VIKUNJA_DATABASE_HOST=intranet-db.intranet.svc.cluster.local
  VIKUNJA_DATABASE_PORT=5432
  VIKUNJA_DATABASE_DATABASE=vikunja
  VIKUNJA_DATABASE_USER=vikunja
  VIKUNJA_DATABASE_PASSWORD=<from intranet-db-secret, key vikunja-password>
  VIKUNJA_SERVICE_FRONTENDURL=https://tasks.your-domain.com
  VIKUNJA_SERVICE_TIMEZONE=Asia/Tokyo
  VIKUNJA_SERVICE_ENABLEREGISTRATION=false
  VIKUNJA_AUTH_LOCAL_ENABLED=false
  VIKUNJA_AUTH_OPENID_ENABLED=true
  VIKUNJA_AUTH_OPENID_PROVIDERS_0_NAME=Google
  VIKUNJA_AUTH_OPENID_PROVIDERS_0_AUTHURL=https://accounts.google.com
  VIKUNJA_AUTH_OPENID_PROVIDERS_0_CLIENTID=<from vikunja-oauth-secret>
  VIKUNJA_AUTH_OPENID_PROVIDERS_0_CLIENTSECRET=<from vikunja-oauth-secret>
  TZ=Asia/Tokyo
  ```
- Probes: HTTP GET `/api/v1/info` port 3456

### `service-vikunja.yaml`
- ClusterIP, port 3456, name `http`

### `deployment-outline.yaml`
- Image: `outlinewiki/outline:latest`
- Priority: `shinbee-high`
- Resources: 200Mi req / 512Mi limit, 200m / 1 cpu
- Environment:
  ```
  URL=https://wiki.your-domain.com
  DATABASE_URL=<from outline-db-url secret, key url>
  REDIS_URL=redis://intranet-redis.intranet.svc.cluster.local:6379
  SECRET_KEY=<from outline-app-secret>
  UTILS_SECRET=<from outline-app-secret>
  GOOGLE_CLIENT_ID=<from outline-oauth-secret>
  GOOGLE_CLIENT_SECRET=<from outline-oauth-secret>
  GOOGLE_ALLOWED_DOMAINS=your-domain.com
  FILE_STORAGE=s3
  AWS_ACCESS_KEY_ID=<from minio-secret>
  AWS_SECRET_ACCESS_KEY=<from minio-secret>
  AWS_S3_UPLOAD_BUCKET_URL=http://intranet-minio.intranet.svc.cluster.local:9000
  AWS_S3_UPLOAD_BUCKET_NAME=outline-data
  AWS_S3_FORCE_PATH_STYLE=true
  AWS_S3_ACL=private
  AWS_REGION=us-east-1
  FORCE_HTTPS=false
  ENABLE_UPDATES=false
  DEFAULT_LANGUAGE=ja_JP
  TZ=Asia/Tokyo
  ```
- **Key note**: `FORCE_HTTPS=false` because TLS terminates at the ingress, not at Outline. `URL` still uses `https://` for redirect URLs.
- Probes: HTTP GET `/_health` port 3000

### `service-outline.yaml`
- ClusterIP, port 3000, name `http`

### `ingress.yaml`
- Two hosts: `tasks.your-domain.com` → `intranet-vikunja:3456`, `wiki.your-domain.com` → `intranet-outline:3000`
- Single TLS secret: `intranet-tls` covering both hosts
- Same annotations as inventree ingress

---

## Notes for Continuation

### Known Gotchas
1. **Outline requires `DATABASE_URL` as a single string** — can't compose from individual env vars in K8s. The render script must build the full connection string and store it in a secret.
2. **Outline `FORCE_HTTPS=false`** — ingress handles TLS. If set to `true`, Outline forces HTTPS on internal redirects which breaks behind ingress.
3. **MinIO `mc` binary** — verify it exists in `minio/minio:latest`. Alternative: use `minio/mc:latest` for the bucket creation job.
4. **Vikunja OIDC array syntax** — uses `_0_` index in env var names for the first provider. Multiple providers use `_1_`, `_2_`, etc.
5. **Storage class**: Use `longhorn-single` (1x replica) for intranet PVCs. The existing `longhorn` class has 2x replicas which may be near capacity.
6. **cert-manager DNS-01**: Uses Cloud DNS solver (migrated from Route53 in Phase 8). The intranet ingress uses the same `letsencrypt-production` ClusterIssuer.
7. **`pool.sh` only creates `shinbee` namespace** — the intranet namespace must be created separately.
8. **Priority classes are cluster-scoped** — existing `shinbee-critical/high/normal` classes work across all namespaces.

### Architecture decisions log
- **Shared PostgreSQL**: Saves ~256Mi vs two PG instances. Two logical DBs (`vikunja`, `outline`) with separate users.
- **`intranet` namespace**: Isolates from `shinbee` to allow independent lifecycle, RBAC, and resource quotas.
- **No messaging app**: Vikunja task comments sufficient for 2-5 person team. Defer Rocket.Chat/Mattermost.
- **Raw YAML (no Helm)**: Matches existing pattern — all manifests are hand-written YAML.
- **Redis is Outline-only**: Vikunja doesn't need Redis. Redis is required by Outline for caching/sessions.
- **MinIO is Outline-only**: Vikunja stores files in PostgreSQL by default. MinIO is required by Outline for S3-compatible file storage.
