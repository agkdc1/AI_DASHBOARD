# Static IP for Rakuten API integration.
# Rakuten RMS requires IP allowlisting for API access.
# k3s-control-0 acts as a forward proxy (Squid) for Rakuten API calls.

# Reserve a static external IP in the same region as the instance
resource "google_compute_address" "rakuten_proxy" {
  name         = "rakuten-proxy-ip"
  region       = var.region
  address_type = "EXTERNAL"
  network_tier = "PREMIUM"

  labels = {
    managed_by = "terraform"
    component  = "rakuten-proxy"
  }
}

# --- Outputs ---

output "rakuten_proxy_ip" {
  description = "Static external IP for Rakuten API allowlisting"
  value       = google_compute_address.rakuten_proxy.address
}
