# Kubernetes Operations Runbook

## Quick Reference

```bash
# Set KUBECONFIG
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

# Cluster status
kubectl get nodes -o wide
kubectl get pods -n shinbee -o wide
kubectl top nodes
kubectl top pods -n shinbee

# FAX stack (still on Pi)
sg docker -c "docker ps --filter name=raspbx"

# Intranet stack
kubectl get pods -n intranet -o wide
```

## Day 1: Provisioning

### 1. Pre-fetch artifacts
```bash
cd /home/pi/SHINBEE/infrastructure/kubernetes/scripts
./download.sh
```

### 2. Configure nodes.yaml
Edit `infrastructure/kubernetes/config/nodes.yaml` — set Tailscale device names for each node.

### 3. Update Vault listener
Update `Vault/docker-compose.yml` to bind Vault to LAN IP:
```yaml
ports:
  - "10.0.2.10:8200:8200"
  - "127.0.0.1:8200:8200"
```
Restart Vault:
```bash
cd /home/pi/SHINBEE/Vault && sg docker -c "docker compose up -d"
```

### 4. Bootstrap K3s cluster
```bash
sudo ./pool.sh
```

### 5. Build disk image and provision workers
```powershell
# Create a generic image (one image, reuse for all nodes):
.\bootable.ps1 -ImageOnly
```
Flash to a USB drive (Rufus DD mode, balenaEtcher, or Win32DiskImager). Then per node:
1. Boot laptop from USB
2. Node auto-joins WiFi → Tailscale → K3s cluster
3. Clone USB to internal drive:
   ```bash
   lsblk                                                        # identify internal drive
   dd if=/dev/sda of=/dev/nvme0n1 bs=4M status=progress conv=fsync  # adjust device names
   ```
4. Reboot, change BIOS boot order to internal drive
5. Remove USB — reuse it for the next node

Root partition auto-expands to fill the internal drive on next boot.

### 6. Build and push x86 images (Cloud Build)
```bash
# Build all 3 images in parallel on GCP (from repo root):
gcloud builds submit --config=cloudbuild.yaml .

# Build with custom tag:
gcloud builds submit --config=cloudbuild.yaml --substitutions=_TAG=stable .
```

Manual build (fallback — requires Docker Desktop with amd64 support):
```powershell
gcloud auth configure-docker asia-northeast1-docker.pkg.dev
$REGISTRY = "asia-northeast1-docker.pkg.dev/your-gcp-project-id/shinbee"
docker buildx build --platform linux/amd64 -f infrastructure/kubernetes/images/selenium-daemon/Dockerfile -t ${REGISTRY}/selenium-daemon:latest --push .
docker buildx build --platform linux/amd64 -f infrastructure/kubernetes/images/rakuten-renewal/Dockerfile -t ${REGISTRY}/rakuten-renewal:latest --push .
```

### 7. Test deployment
```bash
sudo ./test.sh
```

### 8. Migrate
```bash
sudo ./migrate.sh            # Production cutover
sudo ./migrate.sh --dry-run  # Preview only
sudo ./migrate.sh --rollback # Emergency rollback
```

## Common Operations

### Restart a workload
```bash
kubectl -n shinbee rollout restart deployment inventree-server
kubectl -n shinbee rollout restart deployment selenium-daemon
```

### Scale a deployment
```bash
kubectl -n shinbee scale deployment inventree-server --replicas=2
kubectl -n shinbee scale deployment inventree-worker --replicas=2
```

### View logs
```bash
kubectl -n shinbee logs -f deployment/inventree-server
kubectl -n shinbee logs -f deployment/selenium-daemon
kubectl -n shinbee logs deployment/inventree-worker --tail=100
```

### Exec into a pod
```bash
kubectl -n shinbee exec -it deployment/inventree-server -- bash
kubectl -n shinbee exec -it deployment/selenium-daemon -- bash
```

### Update InvenTree
```bash
# Rebuild image with new tag via Cloud Build
gcloud builds submit --config=cloudbuild.yaml \
  --substitutions=_TAG=0.17.0 .

# Update deployment
REGISTRY="asia-northeast1-docker.pkg.dev/your-gcp-project-id/shinbee"
kubectl -n shinbee set image deployment/inventree-server inventree-server=${REGISTRY}/inventree:0.17.0
kubectl -n shinbee set image deployment/inventree-worker inventree-worker=${REGISTRY}/inventree:0.17.0

# Watch rollout
kubectl -n shinbee rollout status deployment/inventree-server
```

### Refresh secrets from GCP Secret Manager
```bash
# Shinbee namespace
sudo /home/pi/SHINBEE/infrastructure/kubernetes/scripts/render-k8s-secrets.sh shinbee
kubectl -n shinbee rollout restart deployment inventree-server
kubectl -n shinbee rollout restart deployment inventree-worker

# Intranet namespace
sudo /home/pi/SHINBEE/infrastructure/kubernetes/scripts/render-k8s-secrets.sh intranet
kubectl -n intranet rollout restart deployment intranet-vikunja
kubectl -n intranet rollout restart deployment intranet-outline
```

### Database operations
```bash
# Connect to MySQL
kubectl -n shinbee exec -it statefulset/inventree-db -- mysql -u root -p inventree

# Manual backup
kubectl -n shinbee exec statefulset/inventree-db -- \
  mysqldump -u root -p'PASSWORD' --single-transaction inventree > backup.sql

# Restore
kubectl -n shinbee exec -i statefulset/inventree-db -- \
  mysql -u root -p'PASSWORD' inventree < backup.sql
```

### K8s Backup (InvenTree)

A daily CronJob (`backup`) runs at 03:00 JST, dumping the InvenTree MySQL database, compressing with xz, encrypting with AES-256-CBC, and uploading to GCS.

```bash
# Check CronJob status
kubectl -n shinbee get cronjob backup
kubectl -n shinbee get jobs --sort-by='.status.startTime'

# View last backup job logs
kubectl -n shinbee logs job/$(kubectl -n shinbee get jobs -l app.kubernetes.io/name=backup \
  --sort-by='.status.startTime' -o jsonpath='{.items[-1].metadata.name}')

# Manual backup trigger
kubectl -n shinbee create job --from=cronjob/backup backup-manual-$(date +%s)

# List backups in GCS
gcloud storage ls gs://your-project-vault-backup/k8s-inventree-*
```

**Restore from K8s backup:**
```bash
# 1. Download encrypted backup
gcloud storage cp gs://your-project-vault-backup/k8s-inventree-YYYYMMDD-HHMMSS.sql.xz.enc /tmp/

# 2. Decrypt and decompress
openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 \
  -pass "pass:ENCRYPTION_PASSWORD" \
  -in /tmp/k8s-inventree-YYYYMMDD-HHMMSS.sql.xz.enc \
  | xz -d > /tmp/inventree-restore.sql

# 3. Restore into MySQL pod
kubectl -n shinbee exec -i statefulset/inventree-db -- \
  mysql -u root -p'PASSWORD' inventree < /tmp/inventree-restore.sql

# 4. Restart InvenTree to pick up restored data
kubectl -n shinbee rollout restart deployment inventree-server
kubectl -n shinbee rollout restart deployment inventree-worker

# 5. Clean up
rm -f /tmp/k8s-inventree-*.sql.xz.enc /tmp/inventree-restore.sql
```

The encryption password is in GCP Secret Manager at `system-backup` (field: `encryption_password`). The Pi's `backup.sh` uses the same password.

### Certificate management
```bash
# Check cert status
kubectl -n shinbee get certificate
kubectl -n shinbee describe certificate inventree-tls

# Force renewal
kubectl -n shinbee delete certificate inventree-tls
# cert-manager will re-issue automatically

# Check ClusterIssuers
kubectl get clusterissuer
kubectl describe clusterissuer letsencrypt-production
```

### Longhorn storage
```bash
# Check volumes
kubectl -n longhorn-system get volumes.longhorn.io

# Longhorn UI (if exposed)
kubectl -n longhorn-system port-forward svc/longhorn-frontend 8080:80
# Then browse to http://localhost:8080
```

## Disaster Recovery

### Single worker down
K8s automatically reschedules pods to the surviving worker. Longhorn serves data from the remaining replica. Critical pods (DB + server + daemon) fit on one 7GB-budget node.

**Monitor:**
```bash
kubectl get nodes
kubectl -n shinbee get pods -o wide
kubectl -n shinbee get events --sort-by='.lastTimestamp'
```

### Both workers down
Full rollback to Docker on Pi:
```bash
sudo /home/pi/SHINBEE/infrastructure/kubernetes/scripts/migrate.sh --rollback
```
This scales down K8s workloads and restarts Docker compose stacks on Pi.

Then:
1. Update router NAT to forward 80/443 to Pi
2. Verify: `curl -k https://api.your-domain.com/api/`

Recovery time: < 5 minutes.

### Pi down
Workers continue running — existing pods keep serving traffic. No new scheduling happens.

**Recovery:**
1. Restore Pi from backup
2. Start K3s server: `sudo systemctl start k3s`
3. Verify: `kubectl get nodes`

### Corrupted PVC
```bash
# Check Longhorn volume health
kubectl -n longhorn-system get volumes.longhorn.io

# Rebuild from backup
kubectl -n shinbee delete pvc <pvc-name>
# Re-apply PVC manifest, then restore data
kubectl apply -f infrastructure/kubernetes/manifests/<service>/pvc.yaml
```

## Monitoring Checklist

Daily:
- [ ] `kubectl get nodes` — all nodes Ready
- [ ] `kubectl -n shinbee get pods` — all pods Running
- [ ] `curl -sf https://api.your-domain.com/api/` — InvenTree responds
- [ ] `curl -sf https://tasks.your-domain.com/api/v1/info` — Vikunja responds
- [ ] `curl -sf -o /dev/null https://wiki.your-domain.com/` — Outline responds
- [ ] `curl -sf -o /dev/null https://app.your-domain.com/` — Flutter dashboard responds
- [ ] `kubectl -n shinbee logs deployment/selenium-daemon --tail=10` — no errors
- [ ] `kubectl -n shinbee logs deployment/ai-assistant --tail=10` — no errors

Weekly:
- [ ] `kubectl top nodes` — resource usage within budget
- [ ] `kubectl -n shinbee get certificate` — TLS cert not expiring soon
- [ ] `kubectl -n intranet get certificate` — intranet TLS cert not expiring soon
- [ ] `kubectl -n intranet get pods` — all intranet pods Running
- [ ] Longhorn dashboard — volumes healthy, replicas in sync
- [ ] `sudo /home/pi/SHINBEE/backup.sh` — fax stack backup succeeds
- [ ] `kubectl -n shinbee get cronjob backup` — K8s backup CronJob last run succeeded
- [ ] `kubectl -n shinbee get cronjob ai-evolution` — AI evolution CronJob last run succeeded

## Omada Controller Post-Migration

After migration, EAPs need to discover the new controller IP:

1. Get Omada MetalLB IP:
   ```bash
   kubectl -n shinbee get svc omada-controller -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
   ```

2. SSH to each EAP and update inform URL:
   ```bash
   # On EAP (if accessible)
   set-inform http://<OMADA_IP>:29811/inform
   ```

3. Or from Omada controller UI: Settings → Cloud → Inform URL

## Future: FAX Stack Migration to K8s

Currently the FAX stack (Asterisk headless, HylaFAX, iaxmodem, faxapi, mail2fax) runs on the Pi in Docker. Workers connect via WiFi + Tailscale, which is unsuitable for real-time SIP/RTP and fax timing.

**Once worker nodes are connected to the MikroTik via Ethernet**, the FAX stack can move to K8s:

1. **`hostNetwork: true`** — Asterisk binds directly to the node's LAN IP
2. **`nodeSelector`** — pin to a specific Ethernet-connected node; MikroTik NATs SIP/RTP to that node's LAN IP
3. **Capabilities** — `SYS_PTRACE` + `NET_ADMIN` for iaxmodem PTY devices
4. **Shared PVCs** — asterisk-spool and asterisk-etc shared between core, faxapi, and mail2fax pods
5. **MikroTik update** — change NAT destination from Pi IP to the pinned worker's LAN IP

Optional: keepalived floating VIP so Asterisk can move between nodes without touching MikroTik config. Not needed initially — pin to one node and update MikroTik manually if it ever moves.

## Intranet Stack (Vikunja + Outline)

The `intranet` namespace runs Vikunja (tasks) and Outline (wiki) with shared PostgreSQL, Redis, and MinIO.

### URLs
- **Tasks**: https://tasks.your-domain.com (Vikunja)
- **Wiki**: https://wiki.your-domain.com (Outline)

### Architecture
```
PostgreSQL 16 (StatefulSet, longhorn-single PVC)
  ├── vikunja DB
  └── outline DB
Redis 7 (Deployment, longhorn-single PVC)
MinIO (Deployment, longhorn-single PVC) → outline-data bucket
Vikunja (Deployment) → Google OIDC auth
Outline (Deployment) → Google OIDC auth, MinIO for file storage
```

### Common Operations
```bash
# Check all intranet pods
kubectl -n intranet get pods -o wide

# View logs
kubectl -n intranet logs -f deployment/intranet-vikunja
kubectl -n intranet logs -f deployment/intranet-outline

# Restart a service
kubectl -n intranet rollout restart deployment intranet-vikunja
kubectl -n intranet rollout restart deployment intranet-outline

# Connect to PostgreSQL
kubectl -n intranet exec -it statefulset/intranet-db -- psql -U postgres

# Check certificate
kubectl -n intranet get certificate
kubectl -n intranet describe certificate intranet-tls
```

### Render Intranet Secrets
```bash
sudo /home/pi/SHINBEE/infrastructure/kubernetes/scripts/render-k8s-secrets.sh intranet
```

### OAuth Setup
All three apps (InvenTree, Vikunja, Outline) share a single Google OAuth client stored in GCP Secret Manager as `inventree-oauth`. The `render-k8s-secrets.sh` script reads it once and populates secrets in both `shinbee` and `intranet` namespaces.

The OAuth client in GCP Console (APIs & Services > Credentials) must have all origins and redirect URIs:

**Authorized JavaScript origins:**
- `https://portal.your-domain.com`
- `https://tasks.your-domain.com`
- `https://wiki.your-domain.com`
- `https://app.your-domain.com` (Flutter dashboard)

**Authorized redirect URIs:**
- `https://portal.your-domain.com/accounts/google/login/callback/` (InvenTree)
- `https://tasks.your-domain.com/auth/openid/google/callback` (Vikunja)
- `https://wiki.your-domain.com/auth/google.callback` (Outline)
- `https://app.your-domain.com` (Flutter web — uses popup, no callback path)

### Database Backup/Restore
```bash
# Dump all databases
kubectl -n intranet exec statefulset/intranet-db -- \
  pg_dumpall -U postgres > intranet-backup.sql

# Restore
kubectl -n intranet exec -i statefulset/intranet-db -- \
  psql -U postgres < intranet-backup.sql
```

## Flutter Dashboard

### Build and Deploy
```bash
# Build Flutter web app (K8s Job on amd64 worker)
sudo ./infrastructure/kubernetes/scripts/flutter-build.sh /home/pi/SHINBEE master web

# Deploy latest build (rollout restart → init container fetches from GCS)
sudo ./infrastructure/kubernetes/scripts/flutter-deploy-web.sh

# Check deployment status
kubectl -n shinbee get pods -l app.kubernetes.io/name=flutter-dashboard
kubectl -n shinbee logs deployment/flutter-dashboard -c fetch-build
```

### URL
- **Dashboard**: https://app.your-domain.com

### Build Artifacts
```bash
# List builds in GCS
gsutil ls gs://your-project-flutter-artifacts/flutter-dashboard/

# Check latest build
gsutil ls gs://your-project-flutter-artifacts/flutter-dashboard/ | sort | tail -5
```

## AI Assistant

### Operations
```bash
# Check AI assistant pod
kubectl -n shinbee get pods -l app.kubernetes.io/name=ai-assistant
kubectl -n shinbee logs -f deployment/ai-assistant

# Test health endpoint
kubectl -n shinbee exec deployment/ai-assistant -- curl -s http://localhost:8030/health

# Check evolution CronJob
kubectl -n shinbee get cronjob ai-evolution
kubectl -n shinbee get jobs -l app.kubernetes.io/name=ai-evolution --sort-by='.status.startTime'

# Manually trigger evolution analysis
kubectl -n shinbee exec deployment/ai-assistant -- \
  curl -s -X POST http://localhost:8030/evolution/trigger
```

### GCS Buckets
```bash
# PII raw data (auto-deleted after 7 days)
gsutil ls gs://your-project-pii-raw/

# AI interaction logs (auto-deleted after 90 days)
gsutil ls gs://your-project-ai-logs/

# SOP documents
gsutil ls gs://your-project-ai-sops/
```

## Cloud DNS Operations

DNS is managed by Cloud DNS (migrated from Route53 in Phase 8).

```bash
# List DNS records
gcloud dns record-sets list --zone=your-domain-com

# Check DNS propagation
dig +short app.your-domain.com
dig +short portal.your-domain.com

# Terraform changes (from Pi with SA key)
cd infrastructure/kubernetes/terraform/gcp
GOOGLE_APPLICATION_CREDENTIALS=/home/pi/keys/fax-terraform-deploy.json \
  terraform plan
```

## Troubleshooting

### Pod stuck in Pending
```bash
kubectl -n shinbee describe pod <pod-name>
# Check Events section for: insufficient resources, unbound PVC, node affinity
```

### Pod in CrashLoopBackOff
```bash
kubectl -n shinbee logs <pod-name> --previous
# Check init-wrapper.sh output, database connectivity, secret mounts
```

### Ingress not working
```bash
kubectl -n ingress-nginx get pods
kubectl -n ingress-nginx logs deployment/ingress-nginx-controller
kubectl -n shinbee describe ingress inventree-ingress
# Check: backend services exist, correct port names, TLS secret exists
```

### Database connection refused
```bash
kubectl -n shinbee exec deployment/inventree-server -- \
  python -c "import MySQLdb; c=MySQLdb.connect(host='inventree-db',port=3306,user='inventree',passwd='test'); print('OK')"
# Check: MySQL pod running, service exists, secret has correct password
```
