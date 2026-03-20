# Flutter build artifacts — GCS bucket + IAM for k8s-backup SA.
# Reuses existing k8s-backup SA (already has key in cluster as backup-gcs-secret).

resource "google_storage_bucket" "flutter_artifacts" {
  name                        = "your-project-flutter-artifacts"
  location                    = "ASIA-NORTHEAST1"
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true

  lifecycle_rule {
    condition { age = 90 }
    action { type = "Delete" }
  }

  labels = {
    managed_by = "terraform"
    component  = "flutter"
  }
}

resource "google_storage_bucket_iam_member" "k8s_backup_flutter_writer" {
  bucket = google_storage_bucket.flutter_artifacts.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.k8s_backup.email}"
}
