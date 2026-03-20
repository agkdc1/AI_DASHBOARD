# Artifact Registry — Docker repository for K3s cluster images.
# Images are pushed from Windows via `gcloud auth configure-docker`.
# Pulled by K3s nodes via containerd registries.yaml (SA key from Secret Manager).

resource "google_artifact_registry_repository" "shinbee" {
  location      = var.region
  repository_id = "shinbee"
  format        = "DOCKER"
  description   = "Container images for K3s cluster workloads"

  labels = {
    managed_by = "terraform"
    component  = "k3s"
  }

  depends_on = [google_project_service.artifact_registry]
}

# Reader service account — used by K3s nodes to pull images
resource "google_service_account" "ar_reader" {
  account_id   = "ar-reader"
  display_name = "Artifact Registry reader"
  description  = "Pulls container images from Artifact Registry for K3s nodes"
}

resource "google_artifact_registry_repository_iam_member" "ar_reader" {
  location   = google_artifact_registry_repository.shinbee.location
  repository = google_artifact_registry_repository.shinbee.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.ar_reader.email}"
}

# SA key — stored in Secret Manager, read by K3s nodes at boot
resource "google_service_account_key" "ar_reader" {
  service_account_id = google_service_account.ar_reader.name
}

resource "google_secret_manager_secret" "ar_reader_key" {
  secret_id = "ar-reader-key"

  replication {
    auto {}
  }

  labels = {
    managed_by = "terraform"
    component  = "k3s"
  }
}

resource "google_secret_manager_secret_version" "ar_reader_key" {
  secret      = google_secret_manager_secret.ar_reader_key.id
  secret_data = base64decode(google_service_account_key.ar_reader.private_key)
}

# Grant K3s node SA access to read the AR reader key
resource "google_secret_manager_secret_iam_member" "k3s_read_ar_key" {
  secret_id = google_secret_manager_secret.ar_reader_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.k3s_node.email}"
}
