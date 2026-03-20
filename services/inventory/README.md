# Shinbee InvenTree

Self-hosted [InvenTree](https://inventree.org/) inventory management system for Shinbee Japan, running on K8s using the official Docker Hub image (`inventree/inventree:stable`). Provides part tracking, purchase order management, multi-marketplace ecommerce integration (Amazon JP, Rakuten, Yahoo, Qoo10), and a portal for invoice/waybill printing via browser automation.

## What This Does

- Runs InvenTree (Django-based inventory system) behind nginx on K8s
- Official Docker Hub image with ConfigMap-mounted init script for runtime patches
- TLS via cert-manager + nginx-ingress (Let's Encrypt, DNS-01 via Cloud DNS)
- Google OAuth2 login restricted to `@your-domain.com` domain
- MySQL 8.0 backend (TCP via K8s ClusterIP Service)
- Custom plugins: ecommerce integration, invoice/waybill printing via selenium daemon
- Portal domain (`portal.your-domain.com`) with CSS/JS overrides for invoice-only view

## Architecture

### Docker (Legacy — Pi, superseded by K8s)

```
Internet
    |
    | HTTPS (port 443)
    v
+-------------------------------+
| inventree-proxy (nginx:1.25)  |
| TLS termination, static files |
| sub_filter for portal domain  |
+-------------------------------+
    | uwsgi socket
    v
+-------------------------------+     +------------------------+
| inventree-server              |     | inventree-worker       |
| Django + uWSGI                |     | django-q2 (4 workers)  |
| InvenTree application         |     | Background tasks       |
+-------------------------------+     +------------------------+
    | unix socket                         |
    v                                     v
+--------------------------------------------+
| inventree-db (mysql:8.0)                   |
| /var/run/mysqld/mysqld.sock                |
+--------------------------------------------+

+-------------------------------+
| inventree-certbot             |
| Let's Encrypt DNS-01          |
| Route53 dynamic DNS (5 min)   |
+-------------------------------+
```

### Kubernetes (Current — Production, official Docker Hub image)

```
Internet -> Ingress (TLS, cert-manager) -> inventree-proxy (HTTP:80)
  -> inventree-server (gunicorn HTTP:8000) -> inventree-db (MySQL TCP:3306)
```

Key differences from Docker:
- **Image**: Official `inventree/inventree:stable` from Docker Hub (no custom build)
- **WSGI**: gunicorn HTTP on port 8000 (nginx uses `proxy_pass http://`)
- **Init**: ConfigMap-mounted `init-shinbee.sh` for runtime patches (OAuth, cookie domain, AppMixin fix)
- **MySQL**: TCP via ClusterIP Service (replaces unix socket)
- **TLS**: cert-manager + nginx-ingress (replaces certbot container)
- **Storage**: Longhorn PVCs (replaces Docker named volumes)
- **Secrets**: K8s Secrets from GCP Secret Manager (replaces Docker secrets)

K8s manifests: `../../infrastructure/kubernetes/manifests/inventree/`

## Container Layout

| Container | Image | Purpose |
|-----------|-------|---------|
| `inventree-db` | `mysql:8.0` | Database (K8s Secret for password) |
| `inventree-server` | `inventree/inventree:stable` (Docker Hub) | Django app via gunicorn |
| `inventree-worker` | `inventree/inventree:stable` (same image) | Background task processor (django-q2) |
| `inventree-proxy` | `nginx:1.25-alpine` | Reverse proxy (HTTP proxy_pass to gunicorn) |
| `inventree-certbot` | Custom (Debian) | Certificate management + dynamic DNS (Docker only) |

## Directory Structure

```
services/inventory/
+-- InvenTree/                  Upstream InvenTree source (git submodule)
+-- plugins/                    Custom InvenTree plugins
|   +-- invoice_plugin/         Invoice/waybill printing (Printer/Tray models, admin UI)
|   |   +-- plugin.py           Main entry (UrlsMixin, SettingsMixin, UserInterfaceMixin)
|   |   +-- models.py           Printer, PrinterTray Django models
|   |   +-- providers/          Per-marketplace adapters (base.py, rakuten.py, etc.)
|   +-- ecommerce_plugin.py     Multi-marketplace order sync
+-- portal/                     Portal override assets (CSS/JS)
+-- shinbee-deploy/             Deployment configuration
|   +-- config.yaml             InvenTree config (DB, plugins, OAuth)
|   +-- docker-compose.yml      5-service Docker stack
|   +-- Dockerfile              InvenTree server image
|   +-- Dockerfile.certbot      Certbot + Route53 + dynamic DNS
|   +-- nginx.conf.template     Nginx config (TLS, uwsgi_pass — legacy Docker only)
|   +-- uwsgi.ini               uWSGI settings (legacy Docker only, K8s uses gunicorn)
|   +-- certbot-entrypoint.sh   Certificate issuance + renewal loop
|   +-- route53-update.py       Dynamic DNS A/AAAA record updater
|   +-- reload-nginx.sh         Signal nginx to reload after cert renewal
|   +-- init-wrapper.sh         InvenTree first-run initialization
|   +-- secrets/                Docker secrets directory
|       +-- mysql_password      MySQL password (rendered from Vault)
|       +-- google_client_id    Google OAuth client ID (rendered from Vault)
|       +-- google_client_secret  Google OAuth client secret (rendered from Vault)
+-- .aws/                       AWS credentials (rendered from Vault)
+-- deploy.sh                   Full deployment script
+-- firewall.sh                 Host firewall rules
```

## Configuration

Configuration comes from two sources:

1. **`shinbee-deploy/config.yaml`** — InvenTree application config (DB, plugins, OAuth)
2. **Root `config.yaml`** — Non-secret values (domain, ports, DB engine, tag)

Secrets are injected by `vault-render-inventree.service` at boot. For K8s, `render-k8s-secrets.sh` creates K8s Secrets.

### Key Settings

| Setting | Value |
|---------|-------|
| API Domain | `api.your-domain.com` |
| Portal Domain | `portal.your-domain.com` |
| InvenTree version | `stable` (tag) |
| Database | MySQL 8.0 (unix socket on Docker, TCP on K8s) |
| Background workers | 4 |
| OAuth | Google (restricted to `@your-domain.com`) |
| TLS | Let's Encrypt (DNS-01 via Route53) |
| Ports | 80 (HTTP redirect), 443 (HTTPS) |
| Cookie domain | `.your-domain.com` (cross-subdomain session sharing) |

## Secrets

Secrets are stored in GCP Secret Manager and rendered to K8s Secrets via `render-k8s-secrets.sh`:

| Secret | Vault Path | Docker | K8s |
|--------|-----------|--------|-----|
| MySQL password | `secret/shinbeeinventree/db` | `secrets/mysql_password` | `inventree-db-secret` |
| AWS credentials | `secret/shinbeeinventree/aws` | `.aws/credentials` | `inventree-aws-secret` |
| Google OAuth ID | `secret/shinbeeinventree/oauth` | `secrets/google_client_id` | `inventree-oauth-secret` |
| Google OAuth secret | `secret/shinbeeinventree/oauth` | `secrets/google_client_secret` | `inventree-oauth-secret` |

## Plugins

Custom plugins are mounted from `plugins/` into the InvenTree containers:

### Invoice Plugin (`invoice_plugin/`)
- **Models**: `Printer`, `PrinterTray` for managing print targets
- **Admin pages**: Self-contained HTML for printer/tray management
- **Dashboard widget**: Print status and quick actions
- **URL endpoints** at `/plugin/invoice-print/<path>`
- **Integration**: Dispatches waybill print jobs to the selenium daemon via API
- Uses mixin-based architecture: `AppMixin`, `UrlsMixin`, `SettingsMixin`, `UserInterfaceMixin`

### Ecommerce Plugin (`ecommerce_plugin.py`)
- Multi-marketplace order sync (Rakuten, Amazon JP, Yahoo, Qoo10)
- Per-marketplace adapters in `providers/` (base.py defines interface)

Plugin development: edit files in `plugins/`, then restart the worker:
```bash
sudo KUBECONFIG=/etc/rancher/k3s/k3s.yaml kubectl -n shinbee rollout restart deployment/inventree-worker
```

## Portal Domain

`portal.your-domain.com` serves the same InvenTree app but with CSS/JS overrides injected via nginx `sub_filter`. This provides an invoice-only view for warehouse staff. Portal assets live in `portal/` and are served at `/portal-assets/`.

## Deployment (K8s — Current)

```bash
# Apply manifests
sudo KUBECONFIG=/etc/rancher/k3s/k3s.yaml kubectl apply -f infrastructure/kubernetes/manifests/inventree/

# Check status
sudo KUBECONFIG=/etc/rancher/k3s/k3s.yaml kubectl -n shinbee get pods -l app.kubernetes.io/part-of=shinbee

# Restart after plugin changes
sudo KUBECONFIG=/etc/rancher/k3s/k3s.yaml kubectl -n shinbee rollout restart deployment/inventree-server deployment/inventree-worker
```

## TLS and DNS

cert-manager handles TLS via Let's Encrypt DNS-01 challenge through Cloud DNS. Certificates are automatically provisioned and renewed. See `infrastructure/kubernetes/manifests/inventree/` for Ingress and cert configuration.

### Legacy Docker Deployment

The `shinbee-deploy/` directory contains the old Docker Compose deployment (Pi-based, uWSGI, certbot, Route53 dynamic DNS). This is no longer active but retained for reference.
