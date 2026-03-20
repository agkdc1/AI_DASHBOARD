# K8s backup — SA + key + Secret Manager for CronJob to upload to GCS.
# Same pattern as registry.tf (SA + key + Secret Manager).

resource "google_service_account" "k8s_backup" {
  account_id   = "k8s-backup"
  display_name = "K8s backup uploader"
  description  = "Uploads InvenTree database backups from K8s CronJob to GCS"
}

resource "google_storage_bucket_iam_member" "k8s_backup_writer" {
  bucket = "your-project-vault-backup"
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.k8s_backup.email}"
}

# SA key — stored in Secret Manager, read by render-k8s-secrets.sh
resource "google_service_account_key" "k8s_backup" {
  service_account_id = google_service_account.k8s_backup.name
}

resource "google_secret_manager_secret" "k8s_backup_key" {
  secret_id = "k8s-backup-key"

  replication {
    auto {}
  }

  labels = {
    managed_by = "terraform"
    component  = "k3s"
  }
}

resource "google_secret_manager_secret_version" "k8s_backup_key" {
  secret      = google_secret_manager_secret.k8s_backup_key.id
  secret_data = base64decode(google_service_account_key.k8s_backup.private_key)
}

# Pi's WIF identity needs SM access to read the key during render-k8s-secrets.sh
resource "google_secret_manager_secret_iam_member" "wif_read_backup_key" {
  secret_id = google_secret_manager_secret.k8s_backup_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "principalSet://iam.googleapis.com/projects/${var.project_number}/locations/global/workloadIdentityPools/shinbee-pi-pool/*"
}
