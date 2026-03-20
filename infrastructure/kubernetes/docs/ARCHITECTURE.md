# Kubernetes Cluster Architecture

## Overview

Hybrid ARM64/x86_64 K3s cluster for Shinbee Japan infrastructure. The Raspberry Pi serves as the K3s client (KUBECONFIG only) and TCP proxy, while two laptop x86_64 workers run all application pods. Control plane is a GCP e2-micro instance.

```
                    Internet
                       |
                  [Router NAT]
                       |
              +-----------------+
              |   Pi (ARM64)    |
              |   nginx stream  |   Public IP (203.0.113.100)
              |   + FAX stack   |   TLS passthrough to workers
              |                 |
              +-----------------+
               Tailscale VPN mesh
                  /       \
   +-------------------+  +-------------------+
   | Laptop-1 (amd64)  |  | Laptop-2 (amd64)  |
   | K3s Agent          |  | K3s Agent          |
   | WiFi + Tailscale   |  | WiFi + Tailscale   |
   | 6-core / 16GB      |  | i3 2-core / 12GB   |
   | hostPort 80/443    |  | hostPort 80/443    |
   | Longhorn replica   |  | Longhorn replica   |
   +-------------------+  +-------------------+

K3s control plane: GCP e2-micro (100.64.0.1, Tailscale)
```

## What Stays on Pi

| Service | Reason |
|---------|--------|
| FAX stack (4 containers) | NTT SIP source IP auth requires host networking on eth1 |
| nginx stream proxy | Pi has the static public IP; proxies to K8s workers |
| vault-render-*.service | Renders fax/inventree secrets from GCP Secret Manager at boot |

## What Runs on K8s Workers

### shinbee namespace

| Pod | Priority Class |
|-----|----------------|
| inventree-db (MySQL StatefulSet) | shinbee-critical (1000) |
| inventree-server (gunicorn) | shinbee-critical (1000) |
| inventree-worker (django-q2) | shinbee-high (500) |
| inventree-proxy (nginx) | shinbee-high (500) |
| selenium-daemon (Chromium+Xvfb) | shinbee-high (500) |
| rakuten-renewal (Chromium) | shinbee-normal (100) |
| omada-controller | shinbee-normal (100) |
| flutter-dashboard (nginx + GCS init) | shinbee-normal (100) |
| ai-assistant (FastAPI + PaddleOCR) | shinbee-normal (100) |
| backup (CronJob, daily 03:00 JST) | — |
| ai-evolution (CronJob, Saturday 09:00 JST) | — |

### intranet namespace

| Pod | Priority Class |
|-----|----------------|
| intranet-db (PostgreSQL 16 StatefulSet) | shinbee-critical (1000) |
| intranet-redis (Redis 7) | shinbee-normal (100) |
| intranet-minio (MinIO) | shinbee-normal (100) |
| intranet-vikunja (tasks) | shinbee-high (500) |
| intranet-outline (wiki) | shinbee-high (500) |

## Infrastructure Components

### K3s
- Version: v1.34.4+k3s1
- Flannel VXLAN CNI
- Disabled: Traefik, ServiceLB (nginx-ingress uses hostPort on workers)
- Pi tainted: `NoSchedule` + `NoExecute`

### nginx-ingress-controller
- DaemonSet with hostPort 80/443 on all workers
- Handles TLS termination for all domains
- cert-manager integration for automatic certificate provisioning

### Longhorn
- Replicated block storage across both workers
- Default StorageClass: `longhorn` (2 replicas, ReclaimPolicy: Retain)
- Single-replica StorageClass: `longhorn-single` (1 replica, for intranet PVCs)
- Data path: `/var/lib/longhorn` on each worker

### cert-manager
- DNS-01 challenge via Cloud DNS (migrated from Route53 in Phase 8)
- SA: `cert-manager-dns` with `roles/dns.admin`
- ClusterIssuers: `letsencrypt-production`, `letsencrypt-staging`
- Certificates: `inventree-tls` (api + portal), `intranet-tls` (tasks + wiki), `flutter-tls` (app)

## Network Architecture

### Traffic Flow (External → K8s)
```
Internet → Router NAT (80/443) → Pi nginx stream (TLS passthrough, SNI)
  → Worker Tailscale IP :443 → nginx-ingress (TLS termination)
  → K8s Service → Pod
```

### Pi nginx stream proxy
The Pi forwards TCP traffic based on SNI (Server Name Indication):
- `api.your-domain.com` → k8s_https upstream
- `portal.your-domain.com` → k8s_https upstream
- `tasks.your-domain.com` → k8s_https upstream
- `wiki.your-domain.com` → k8s_https upstream
- `app.your-domain.com` → k8s_https upstream (Flutter dashboard)

Worker IPs are refreshed every 5 min by `shinbee-proxy-refresh.timer`.

### Service Discovery
All inter-pod communication uses K8s DNS:
- `inventree-db.shinbee.svc.cluster.local:3306` (MySQL)
- `inventree-server.shinbee.svc.cluster.local:8000` (gunicorn HTTP)
- `inventree-proxy.shinbee.svc.cluster.local:80` (nginx)
- `selenium-daemon.shinbee.svc.cluster.local:8020` (daemon API)
- `ai-assistant.shinbee.svc.cluster.local:8030` (AI assistant API)
- `flutter-dashboard.shinbee.svc.cluster.local:80` (Flutter web app)
- `intranet-db.intranet.svc.cluster.local:5432` (PostgreSQL)
- `intranet-redis.intranet.svc.cluster.local:6379` (Redis)
- `intranet-minio.intranet.svc.cluster.local:9000` (MinIO)

## Secrets Flow

```
GCP Secret Manager (project: your-gcp-project-id)
  → Pi: render-fax-env.sh (WIF mTLS auth) → .env, config files
  → Pi: render-inventree-env.sh (WIF mTLS auth) → secrets/mysql_password
  → Pi: render-k8s-secrets.sh (WIF mTLS auth) → K8s Secrets in shinbee + intranet namespaces
  → K8s pods mount secrets as files or env vars
```

## Storage Architecture

### shinbee namespace

| PVC | Access Mode | Size | Used By |
|-----|-------------|------|---------|
| mysql-data (StatefulSet) | RWO | 10Gi | inventree-db |
| inventree-data | RWX | 10Gi | server, worker, proxy (ro) |
| inventree-plugins | RWX | 1Gi | server, worker |
| inventree-portal | RWX | 256Mi | proxy (ro) |
| selenium-cookies | RWO | 256Mi | selenium-daemon |
| selenium-pdfs | RWO | 1Gi | selenium-daemon |
| selenium-logs | RWO | 2Gi | selenium-daemon |
| selenium-screenshots | RWO | 2Gi | selenium-daemon |
| selenium-state | RWO | 64Mi | selenium-daemon |
| rakuten-logs | RWO | 1Gi | rakuten-renewal |
| rakuten-screenshots | RWO | 1Gi | rakuten-renewal |
| rakuten-state | RWO | 64Mi | rakuten-renewal |
| omada-data | RWO | 5Gi | omada-controller |
| omada-logs | RWO | 1Gi | omada-controller |

### intranet namespace

| PVC | Access Mode | Size | StorageClass | Used By |
|-----|-------------|------|-------------|---------|
| pgdata (StatefulSet) | RWO | 5Gi | longhorn-single | intranet-db |
| redis-data | RWO | 256Mi | longhorn-single | intranet-redis |
| minio-data | RWO | 5Gi | longhorn-single | intranet-minio |

## Resource Budget

Per worker: 8GB RAM total, ~500MB system/K3s/Longhorn overhead, ~7GB for workloads.

**Worker 1 (inventree):** ~1.9GB requests, ~4.5GB limits
**Worker 2 (browser):** ~1.5GB requests, ~4.1GB limits
**Intranet (shared):** ~0.7GB requests, ~1.7GB limits

In single-worker degraded mode, critical pods (DB + server + daemon) total ~5.1GB and fit on one node.

## Key Design Decisions

### Unix Socket → TCP Refactoring
- **MySQL**: `unix_socket: /var/run/mysqld/mysqld.sock` → `HOST: inventree-db, PORT: 3306`
- **WSGI**: uWSGI unix socket → gunicorn HTTP on `0.0.0.0:8000` (official image default)
- nginx uses `proxy_pass http://` to gunicorn (migrated from `uwsgi_pass` binary protocol)

### TLS Termination
- Ingress handles TLS (cert-manager + Let's Encrypt)
- nginx proxy operates HTTP-only internally
- HSTS headers set at Ingress level

### Pi Stream Proxy
- Pi has the static public IP from the router NAT
- Workers connect via WiFi + Tailscale (dynamic IPs)
- nginx stream with `ssl_preread` routes by SNI without decrypting
- Worker IPs refreshed every 5 min from `kubectl get nodes`
