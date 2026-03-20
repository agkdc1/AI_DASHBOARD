# Tailscale auth key stored in Secret Manager.
# Populated out-of-band by scripts/save-authkey.sh — not by Terraform.
# Terraform only creates the secret resource and grants access.

resource "google_secret_manager_secret" "tailscale_authkey" {
  secret_id = "k3s-tailscale-authkey"

  replication {
    auto {}
  }

  labels = {
    managed_by = "terraform"
    component  = "k3s"
  }
}

# Grant the instance service account access to read the secret
resource "google_secret_manager_secret_iam_member" "instance_read_authkey" {
  secret_id = google_secret_manager_secret.tailscale_authkey.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.k3s_node.email}"
}

# =============================================================================
# Application secrets — migrated from Vault to GCP Secret Manager
# =============================================================================
# Each Vault KV path becomes a GCP SM secret containing JSON with all fields.
# ESO (External Secrets Operator) on K8s reads from these, and Pi reads
# via WIF-authenticated gcloud SDK.
#
# Naming: Vault path "shinbee_japan_fax/db" (legacy name) -> SM secret "fax-db"

locals {
  app_secrets = {
    "admin-aws"            = "Admin AWS credentials (infrastructure management)"
    "daemon-sagawa"        = "Sagawa web session credentials"
    "daemon-yamato"        = "Yamato web session credentials"
    "fax-ami"              = "Asterisk AMI credentials"
    "fax-aws"              = "Fax stack AWS credentials (Route53, SES)"
    "fax-db"               = "Fax MariaDB credentials"
    "fax-api-key"          = "Fax API key"
    "fax-smtp"             = "Fax SMTP credentials"
    "fax-smtp-relay"       = "Fax SMTP relay credentials"
    "fax-switch"           = "MikroTik switch credentials"
    "fax-terraform"        = "Fax Terraform email password"
    "inventree-aws"        = "InvenTree AWS credentials"
    "inventree-db"         = "InvenTree MySQL password"
    "inventree-oauth"      = "InvenTree Google OAuth credentials"
    "system-backup"        = "Backup encryption password"
    "system-gcp-terraform" = "GCP Terraform deployer SA key (JSON)"
    "intranet-db"          = "Intranet PostgreSQL passwords (Vikunja + Outline)"
    # Vikunja and Outline share the inventree-oauth client (no separate secrets needed)
    "intranet-outline"     = "Outline application secrets"
    "intranet-minio"       = "Intranet MinIO credentials"
    "samba-ad"             = "Samba AD DC admin password"
    "google-admin-sdk"     = "Google Admin SDK SA key (JSON) for Workspace sync"
  }
}

resource "google_secret_manager_secret" "app" {
  for_each  = local.app_secrets
  secret_id = each.key

  replication {
    auto {}
  }

  labels = {
    managed_by = "terraform"
    component  = "vault-migration"
  }
}

# Pi reads all secrets via WIF (X.509 mTLS)
resource "google_secret_manager_secret_iam_member" "wif_read_app" {
  for_each  = local.app_secrets
  secret_id = google_secret_manager_secret.app[each.key].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "principalSet://iam.googleapis.com/projects/${var.project_number}/locations/global/workloadIdentityPools/shinbee-pi-pool/*"
}

# ---------- ESO (External Secrets Operator) SA ----------

resource "google_service_account" "eso" {
  account_id   = "k8s-eso"
  display_name = "K8s External Secrets Operator"
  description  = "Reads secrets from GCP SM for K8s workloads via ESO"
}

resource "google_service_account_key" "eso" {
  service_account_id = google_service_account.eso.name
}

# ESO SA can read all app secrets
resource "google_secret_manager_secret_iam_member" "eso_read" {
  for_each  = local.app_secrets
  secret_id = google_secret_manager_secret.app[each.key].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.eso.email}"
}

# ESO SA also reads the existing k8s-backup-key
resource "google_secret_manager_secret_iam_member" "eso_read_backup_key" {
  secret_id = google_secret_manager_secret.k8s_backup_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.eso.email}"
}

# Store ESO SA key in SM so render-k8s-secrets.sh can deploy it
resource "google_secret_manager_secret" "eso_key" {
  secret_id = "k8s-eso-key"

  replication {
    auto {}
  }

  labels = {
    managed_by = "terraform"
    component  = "k3s"
  }
}

resource "google_secret_manager_secret_version" "eso_key" {
  secret      = google_secret_manager_secret.eso_key.id
  secret_data = base64decode(google_service_account_key.eso.private_key)
}

resource "google_secret_manager_secret_iam_member" "wif_read_eso_key" {
  secret_id = google_secret_manager_secret.eso_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "principalSet://iam.googleapis.com/projects/${var.project_number}/locations/global/workloadIdentityPools/shinbee-pi-pool/*"
}
