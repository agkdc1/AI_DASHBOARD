# cert-manager SA for DNS-01 challenges via Cloud DNS.
# Replaces Route53 credentials after DNS migration to Cloud DNS.

resource "google_service_account" "cert_manager" {
  account_id   = "cert-manager-dns"
  display_name = "cert-manager DNS solver"
  description  = "Manages DNS-01 challenge TXT records in Cloud DNS for Let's Encrypt"
}

resource "google_project_iam_member" "cert_manager_dns_admin" {
  project = var.project_id
  role    = "roles/dns.admin"
  member  = "serviceAccount:${google_service_account.cert_manager.email}"
}

# SA key — stored in Secret Manager, deployed to K8s by render-k8s-secrets.sh
resource "google_service_account_key" "cert_manager" {
  service_account_id = google_service_account.cert_manager.name
}

resource "google_secret_manager_secret" "cert_manager_key" {
  secret_id = "cert-manager-dns-key"

  replication {
    auto {}
  }

  labels = {
    managed_by = "terraform"
    component  = "k3s"
  }
}

resource "google_secret_manager_secret_version" "cert_manager_key" {
  secret      = google_secret_manager_secret.cert_manager_key.id
  secret_data = base64decode(google_service_account_key.cert_manager.private_key)
}

# Pi's WIF identity needs SM access to read the key during render-k8s-secrets.sh
resource "google_secret_manager_secret_iam_member" "wif_read_cert_manager_key" {
  secret_id = google_secret_manager_secret.cert_manager_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "principalSet://iam.googleapis.com/projects/${var.project_number}/locations/global/workloadIdentityPools/shinbee-pi-pool/*"
}
