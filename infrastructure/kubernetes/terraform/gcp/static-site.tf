# Static website for your-domain.com — GCS bucket behind GCLB.
# Migrated from AWS S3 static website hosting.

# --- GCS bucket ---

resource "google_storage_bucket" "www" {
  name                        = "your-domain-www"
  location                    = "ASIA-NORTHEAST1"
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true

  website {
    main_page_suffix = "index.html"
  }

  labels = {
    managed_by = "terraform"
    component  = "static-site"
  }
}

# Public read access for static website serving
resource "google_storage_bucket_iam_member" "www_public" {
  bucket = google_storage_bucket.www.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

# --- Global HTTPS Load Balancer ---

resource "google_compute_global_address" "www" {
  name        = "your-domain-www-ip"
  description = "Static IP for your-domain.com GCLB"
}

resource "google_compute_backend_bucket" "www" {
  name        = "your-domain-www-backend"
  bucket_name = google_storage_bucket.www.name
  enable_cdn  = true
}

resource "google_compute_url_map" "www" {
  name            = "your-domain-www-urlmap"
  default_service = google_compute_backend_bucket.www.id
}

resource "google_compute_managed_ssl_certificate" "www" {
  name = "your-domain-www-cert"

  managed {
    domains = [
      "your-domain.com",
      "www.your-domain.com",
    ]
  }
}

resource "google_compute_target_https_proxy" "www" {
  name             = "your-domain-www-https-proxy"
  url_map          = google_compute_url_map.www.id
  ssl_certificates = [google_compute_managed_ssl_certificate.www.id]
}

resource "google_compute_global_forwarding_rule" "www_https" {
  name       = "your-domain-www-https"
  target     = google_compute_target_https_proxy.www.id
  port_range = "443"
  ip_address = google_compute_global_address.www.address
}

# --- HTTP → HTTPS redirect ---

resource "google_compute_url_map" "www_redirect" {
  name = "your-domain-www-redirect"

  default_url_redirect {
    https_redirect = true
    strip_query    = false
  }
}

resource "google_compute_target_http_proxy" "www_redirect" {
  name    = "your-domain-www-http-proxy"
  url_map = google_compute_url_map.www_redirect.id
}

resource "google_compute_global_forwarding_rule" "www_http" {
  name       = "your-domain-www-http"
  target     = google_compute_target_http_proxy.www_redirect.id
  port_range = "80"
  ip_address = google_compute_global_address.www.address
}

# --- Outputs ---

output "www_static_ip" {
  description = "GCLB static IP for your-domain.com"
  value       = google_compute_global_address.www.address
}

output "www_bucket" {
  description = "GCS bucket for static site files"
  value       = google_storage_bucket.www.url
}
