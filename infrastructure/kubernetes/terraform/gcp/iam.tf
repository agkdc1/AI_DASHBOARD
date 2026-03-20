# Service account for the K3s GCP node
resource "google_service_account" "k3s_node" {
  account_id   = "k3s-node"
  display_name = "K3s cluster node"
  description  = "Service account for K3s GCP node — reads Tailscale auth key from Secret Manager"
}

# Minimal permissions: only Secret Manager read + logging
resource "google_project_iam_member" "k3s_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.k3s_node.email}"
}

resource "google_project_iam_member" "k3s_metric_writer" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.k3s_node.email}"
}
