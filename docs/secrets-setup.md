# Secrets Management — GCP Secret Manager

All application secrets for the SHINBEEHUB project are stored in **GCP Secret Manager** (SM).
This replaces the previous HashiCorp Vault setup. Only a single GCP credential is needed to
deploy any service — either a WIF (Workload Identity Federation) X.509 mTLS certificate or
a service account key.

## Architecture

```
GCP Secret Manager
        |
        |  gcloud secrets versions access latest --secret=<name>
        |
        v
  render-secrets.sh     ───>  .env files      (docker-compose services)
        |               ───>  secrets/ files   (Docker secrets for InvenTree)
        |               ───>  config.yaml      (in-place updates via yq)
        |
        v
  render-k8s-secrets.sh ───>  kubectl create secret  (K8s clusters)
```

### How secrets flow to each service

| Service | Deployment | Secret delivery mechanism |
|---------|-----------|--------------------------|
| **fax** (Asterisk, faxapi, mail2fax) | docker-compose on Raspberry Pi | `.env` file + `config.yaml` in-place update |
| **inventory** (InvenTree) | docker-compose on Raspberry Pi | Docker secrets files (`secrets/mysql_password`, etc.) + `config.yaml` |
| **selenium-daemon** | K8s (amd64 node) | K8s Secret `selenium-daemon-secret` via `render-k8s-secrets.sh` |
| **rakuten-renewal** | K8s (amd64 node) | Vault AppRole (transition) / K8s Secret via `render-k8s-secrets.sh` |
| **ai-assistant** | K8s (amd64 node) | K8s Secrets (`ai-assistant-gcs-secret`, `gsps-sa-key`, `samba-ad-secret`) |
| **intranet** (Vikunja, Outline, MinIO) | K8s | K8s Secrets via `render-k8s-secrets.sh` |
| **samba-ad** | K8s | K8s Secret `samba-ad-secret` |
| **backup** | K8s CronJob | K8s Secrets (`backup-gcs-secret`, `backup-encryption-secret`) |
| **cert-manager** | K8s | K8s Secret `clouddns-credentials` |

## Prerequisites

- **gcloud CLI** installed (`apt install google-cloud-cli` or snap)
- **yq** v4+ for config.yaml manipulation (`snap install yq` or `go install github.com/mikefarah/yq/v4@latest`)
- **python3** with PyYAML (fallback if yq unavailable)
- **kubectl** (only for K8s secret rendering)

## Authentication

### Option 1: WIF with X.509 mTLS (recommended for Raspberry Pi)

The Pi authenticates to GCP using Workload Identity Federation with X.509 client certificates.
This avoids storing long-lived service account keys on the device.

**Required files:**

| File | Description |
|------|-------------|
| `Vault/pki/wif-credential-config.json` | WIF credential configuration (references cert/key paths) |
| `Vault/pki/client.crt` | X.509 client certificate |
| `Vault/pki/client.key` | Private key for client certificate |
| `Vault/pki/ca.crt` | CA certificate chain |
| `~/.config/gcloud/certificate_config.json` | Certificate config for the gcloud SDK |

**WIF credential config format** (`Vault/pki/wif-credential-config.json`):
```json
{
  "type": "external_account",
  "audience": "//iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/shinbee-pi-pool/providers/shinbee-pi-provider",
  "subject_token_type": "urn:ietf:params:oauth:token-type:mtls",
  "token_url": "https://sts.googleapis.com/v1/token",
  "credential_source": {
    "certificate": {
      "use_default_certificate_config": "true"
    }
  },
  "service_account_impersonation_url": "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/SA_EMAIL:generateAccessToken"
}
```

**Certificate config** (`~/.config/gcloud/certificate_config.json`):
```json
{
  "cert_configs": {
    "workload": {
      "cert_path": "/home/pi/SHINBEEHUB/Vault/pki/client.crt",
      "key_path": "/home/pi/SHINBEEHUB/Vault/pki/client.key"
    }
  }
}
```

### Option 2: Service account key (CI/CD or quick setup)

For CI/CD pipelines or quick setup, use a service account key:

```bash
# Activate the SA key
gcloud auth activate-service-account --key-file=path/to/sa-key.json

# Or set the env var
export GOOGLE_APPLICATION_CREDENTIALS=path/to/sa-key.json
```

### Option 3: User credentials (development)

```bash
gcloud auth login
gcloud auth application-default login
```

## GCP Secret Manager Setup

### 1. Terraform creates the secret resources

All SM secret resources are defined in:
```
infrastructure/kubernetes/terraform/gcp/secrets.tf
```

The Terraform config creates empty secret resources and grants IAM access to:
- The WIF identity pool (for Pi access)
- The ESO service account (for K8s External Secrets Operator)

```bash
cd infrastructure/kubernetes/terraform/gcp
terraform init
terraform apply
```

### 2. Seed secret values

After Terraform creates the resources, seed them with actual values.

**From Vault (one-time migration):**
```bash
sudo ./infrastructure/kubernetes/scripts/seed-secrets.sh
```

**Manually (for new secrets):**
```bash
# JSON payload secret
echo '{"username": "admin", "password": "s3cret"}' | \
  gcloud secrets versions add fax-ami --project=YOUR_PROJECT --data-file=-

# SA key JSON secret
gcloud secrets versions add ai-assistant-key --project=YOUR_PROJECT \
  --data-file=path/to/sa-key.json

# Plain text secret
echo -n "my-auth-key" | \
  gcloud secrets versions add k3s-tailscale-authkey --project=YOUR_PROJECT --data-file=-
```

## Required Secrets — Complete Reference

### Fax system

| Secret ID | Format | Fields | Used by |
|-----------|--------|--------|---------|
| `fax-ami` | JSON | `username`, `secret` | faxapi (Asterisk AMI connection) |
| `fax-api-key` | JSON | `api_key` | faxapi, mail2fax, ai-assistant |
| `fax-db` | JSON | `mysql_root_password`, `mysql_password`, `mysql_user`, `mysql_database` | MariaDB (legacy FreePBX profile) |
| `fax-smtp` | JSON | `username`, `password` | mail2fax (SMTP auth for receiving) |
| `fax-smtp-relay` | JSON | `username`, `password` | mail2fax (Gmail SMTP relay for sending) |
| `fax-aws` | JSON | `access_key_id`, `secret_access_key`, `hosted_zone_id` | mail2fax certbot (Route53 DNS-01) |
| `fax-switch` | JSON | `username`, `password` | MikroTik switch control (OG810Xi VLAN) |
| `og810xi-credentials` | JSON | `username`, `password` | OG810Xi NTT gateway web admin |

### Inventory (InvenTree)

| Secret ID | Format | Fields | Used by |
|-----------|--------|--------|---------|
| `inventree-db` | JSON | `mysql_password` | InvenTree MySQL database |
| `inventree-oauth` | JSON | `client_id`, `client_secret` | Google OAuth2 SSO login |
| `inventree-aws` | JSON | `access_key_id`, `secret_access_key` | InvenTree certbot (Route53) |

### Selenium daemon (carrier portal automation)

| Secret ID | Format | Fields | Used by |
|-----------|--------|--------|---------|
| `daemon-sagawa` | JSON | `user_id`, `password` | Sagawa Express web portal |
| `daemon-yamato` | JSON | `login_id`, `password` | Yamato Transport web portal |

### AI assistant

| Secret ID | Format | Fields | Used by |
|-----------|--------|--------|---------|
| `ai-assistant-key` | SA key JSON | (full SA key) | Gemini API, GCS buckets, Firestore |
| `gsps-sa-key` | SA key JSON | (full SA key) | Google Password Sync (AD + Workspace) |
| `samba-ad` | JSON | `admin_password` | LDAP bind for phone provisioning, IAM |

### Authentik OIDC

| Secret ID | Format | Fields | Used by |
|-----------|--------|--------|---------|
| `authentik-oidc-clients` | JSON | `inventree.{client_id, client_secret}`, `vikunja.{...}`, `outline.{...}` | K8s OAuth secrets for each app |

### Intranet (Vikunja, Outline, MinIO)

| Secret ID | Format | Fields | Used by |
|-----------|--------|--------|---------|
| `intranet-db` | JSON | `vikunja_password`, `outline_password` | PostgreSQL databases |
| `intranet-outline` | JSON | `secret_key`, `utils_secret` | Outline application secrets |
| `intranet-minio` | JSON | `access_key`, `secret_key` | MinIO S3-compatible storage |

### System / infrastructure

| Secret ID | Format | Fields | Used by |
|-----------|--------|--------|---------|
| `system-backup` | JSON | `encryption_password` | Backup encryption (restic/borg) |
| `cert-manager-dns-key` | SA key JSON | (full SA key) | cert-manager Cloud DNS solver |
| `k8s-backup-key` | SA key JSON | (full SA key) | K8s backup CronJob (GCS uploads) |
| `google-admin-sdk` | SA key JSON | (full SA key) | Google Workspace directory sync |
| `admin-aws` | JSON | `access_key_id`, `secret_access_key` | Infrastructure management (AWS) |
| `system-gcp-terraform` | SA key JSON | (full SA key) | Terraform deployer SA |
| `k3s-tailscale-authkey` | Plain text | (auth key) | K3s node Tailscale VPN enrollment |

## Running the Render Script

### Render all services
```bash
./scripts/render-secrets.sh
```

### Render specific services
```bash
./scripts/render-secrets.sh fax inventory
```

### Dry run (preview without writing)
```bash
./scripts/render-secrets.sh --dry-run
```

### Override GCP project
```bash
./scripts/render-secrets.sh --project my-gcp-project-id fax
```

### Render K8s secrets only
```bash
./scripts/render-secrets.sh kubernetes

# Or directly:
sudo ./infrastructure/kubernetes/scripts/render-k8s-secrets.sh all
```

## Output Files

The script creates the following files (all `chmod 600`, all gitignored):

```
services/fax/.env                          # docker-compose env vars
services/fax/.aws/credentials              # AWS creds for Route53
services/fax/config.yaml                   # Updated switch credentials (in-place)
services/fax/mail2fax/config.yaml          # Updated SMTP/API keys (in-place)
services/inventory/shinbee-deploy/secrets/  # Docker secret files:
  mysql_password                           #   MySQL password
  google_client_id                         #   OAuth client ID
  google_client_secret                     #   OAuth client secret
services/inventory/.aws/credentials        # AWS creds for Route53
services/selenium-daemon/.env              # Carrier portal credentials
services/rakuten-renewal/.env              # Vault AppRole config (transition)
services/ai-assistant/.env                 # Gemini, LDAP, faxapi config
services/ai-assistant/secrets/             # SA key files:
  ai-assistant-key.json                    #   GCS/Gemini SA key
  gsps-sa-key.json                         #   Password sync SA key
```

## Rotating Secrets

To rotate a secret:

1. Create a new version in GCP SM:
   ```bash
   echo '{"username": "admin", "password": "new-password"}' | \
     gcloud secrets versions add fax-ami --project=YOUR_PROJECT --data-file=-
   ```

2. Re-run the render script for the affected service:
   ```bash
   ./scripts/render-secrets.sh fax
   ```

3. Restart the affected service:
   ```bash
   cd services/fax && docker compose restart faxapi
   ```

4. (Optional) Disable the old version:
   ```bash
   gcloud secrets versions disable OLD_VERSION --secret=fax-ami --project=YOUR_PROJECT
   ```

## Security Notes

- All rendered files are `chmod 600` (owner read/write only).
- `.env` files and `secrets/` directories should be in `.gitignore`.
- WIF X.509 certificates should be rotated periodically (see `Vault/pki/`).
- SA keys stored in SM can be rotated via Terraform (`terraform taint` + `apply`).
- The render script never logs secret values — only success/failure status.
- Temporary files (e.g., SA key JSON for K8s) are cleaned up immediately after use.
