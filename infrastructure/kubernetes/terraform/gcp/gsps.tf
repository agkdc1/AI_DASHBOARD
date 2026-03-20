# GSPS (Google Workspace Password Sync) — SA for password sync between
# Samba AD DC and Google Workspace.  Requires domain-wide delegation +
# Admin SDK User Management scope, configured manually in the Google
# Workspace admin console after `terraform apply`.

# --- API ---

resource "google_project_service" "admin_sdk" {
  service            = "admin.googleapis.com"
  disable_on_destroy = false
}

# --- Service Account ---

resource "google_service_account" "gsps" {
  account_id   = "gsps-sync"
  display_name = "Google Workspace Password Sync"
  description  = "Syncs AD passwords to Google Workspace via Admin SDK"
}

# SA key — stored in Secret Manager, deployed to K8s by render-k8s-secrets.sh
resource "google_service_account_key" "gsps" {
  service_account_id = google_service_account.gsps.name
}

resource "google_secret_manager_secret" "gsps_key" {
  secret_id = "gsps-sa-key"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "gsps_key" {
  secret      = google_secret_manager_secret.gsps_key.id
  secret_data = base64decode(google_service_account_key.gsps.private_key)
}
