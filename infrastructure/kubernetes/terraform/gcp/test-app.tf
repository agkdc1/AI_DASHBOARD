# Test Flutter dashboard SPA for test-app.your-domain.com — GCS bucket behind GCLB.
# Demo/test environment with SSO bypass for employee training.

# --- GCS bucket ---

resource "google_storage_bucket" "test_flutter_app" {
  name                        = "your-domain-test-app"
  location                    = "ASIA-NORTHEAST1"
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true

  website {
    main_page_suffix = "index.html"
    not_found_page   = "index.html"
  }

  labels = {
    managed_by = "terraform"
    component  = "test-flutter-app"
  }
}

# Public read access for static website serving
resource "google_storage_bucket_iam_member" "test_flutter_app_public" {
  bucket = google_storage_bucket.test_flutter_app.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

# Cloud Build SA needs write access to upload builds
resource "google_storage_bucket_iam_member" "test_flutter_app_cloudbuild" {
  bucket = google_storage_bucket.test_flutter_app.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:000000000000@cloudbuild.gserviceaccount.com"
}

# --- Global HTTPS Load Balancer ---

resource "google_compute_global_address" "test_flutter_app" {
  name        = "your-domain-test-app-ip"
  description = "Static IP for test-app.your-domain.com GCLB"
}

resource "google_compute_backend_bucket" "test_flutter_app" {
  name        = "your-domain-test-app-backend"
  bucket_name = google_storage_bucket.test_flutter_app.name
  enable_cdn  = true
}

resource "google_compute_url_map" "test_flutter_app" {
  name            = "your-domain-test-app-urlmap"
  default_service = google_compute_backend_bucket.test_flutter_app.id
}

resource "google_compute_managed_ssl_certificate" "test_flutter_app" {
  name = "your-domain-test-app-cert"

  managed {
    domains = ["test-app.your-domain.com"]
  }
}

resource "google_compute_target_https_proxy" "test_flutter_app" {
  name             = "your-domain-test-app-https-proxy"
  url_map          = google_compute_url_map.test_flutter_app.id
  ssl_certificates = [google_compute_managed_ssl_certificate.test_flutter_app.id]
}

resource "google_compute_global_forwarding_rule" "test_flutter_app_https" {
  name       = "your-domain-test-app-https"
  target     = google_compute_target_https_proxy.test_flutter_app.id
  port_range = "443"
  ip_address = google_compute_global_address.test_flutter_app.address
}

# --- HTTP -> HTTPS redirect ---

resource "google_compute_url_map" "test_flutter_app_redirect" {
  name = "your-domain-test-app-redirect"

  default_url_redirect {
    https_redirect = true
    strip_query    = false
  }
}

resource "google_compute_target_http_proxy" "test_flutter_app_redirect" {
  name    = "your-domain-test-app-http-proxy"
  url_map = google_compute_url_map.test_flutter_app_redirect.id
}

resource "google_compute_global_forwarding_rule" "test_flutter_app_http" {
  name       = "your-domain-test-app-http"
  target     = google_compute_target_http_proxy.test_flutter_app_redirect.id
  port_range = "80"
  ip_address = google_compute_global_address.test_flutter_app.address
}

# --- DNS A record ---

resource "google_dns_record_set" "test_app_a" {
  managed_zone = google_dns_managed_zone.shinbee_japan.name
  name         = "test-app.your-domain.com."
  type         = "A"
  ttl          = 300
  rrdatas      = [google_compute_global_address.test_flutter_app.address]
}

# --- Outputs ---

output "test_flutter_app_ip" {
  description = "GCLB static IP for test-app.your-domain.com"
  value       = google_compute_global_address.test_flutter_app.address
}

output "test_flutter_app_bucket" {
  description = "GCS bucket for test Flutter app files"
  value       = google_storage_bucket.test_flutter_app.url
}
