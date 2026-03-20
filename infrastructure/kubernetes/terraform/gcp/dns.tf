# Cloud DNS zone for your-domain.com — migrated from AWS Route53.
# Phase 8: nameservers will be updated at the Amazon registrar after verification.

resource "google_dns_managed_zone" "shinbee_japan" {
  name        = "your-domain-com"
  dns_name    = "your-domain.com."
  description = "Primary domain — migrated from Route53"

  labels = {
    managed_by = "terraform"
    component  = "dns"
  }

  depends_on = [google_project_service.dns]
}

# --- Apex ---

# Apex A record: points to GCLB static IP (static site served from GCS)
resource "google_dns_record_set" "apex_a" {
  managed_zone = google_dns_managed_zone.shinbee_japan.name
  name         = "your-domain.com."
  type         = "A"
  ttl          = 300
  rrdatas      = [google_compute_global_address.www.address]
}

# MX — Google Workspace
resource "google_dns_record_set" "apex_mx" {
  managed_zone = google_dns_managed_zone.shinbee_japan.name
  name         = "your-domain.com."
  type         = "MX"
  ttl          = 300
  rrdatas = [
    "10 ASPMX.L.GOOGLE.com.",
    "20 ALT1.ASPMX.L.GOOGLE.com.",
    "21 ALT2.ASPMX.L.GOOGLE.com.",
    "30 ASPMX2.GOOGLEMAIL.com.",
    "31 ASPMX3.GOOGLEMAIL.com.",
    "32 ASPMX4.GOOGLEMAIL.com.",
    "33 ASPMX5.GOOGLEMAIL.com.",
  ]
}

# --- Subdomains via MikroTik DDNS (PPPoE dynamic IP, dst-nat to K8s MetalLB) ---

locals {
  mikrotik_ddns = "your-ddns-hostname.sn.mynetname.net."
  # CNAME subdomains — all resolve via MikroTik DDNS → dst-nat → MetalLB 10.0.0.251
  # Note: fax excluded here because it has an MX record (CNAME+MX is invalid per RFC)
  cname_subdomains = ["ai", "api", "auth", "portal", "tasks", "wiki"]
  test_subdomains  = ["test-api", "test-portal"]
}

resource "google_dns_record_set" "subdomain_cname" {
  for_each     = toset(local.cname_subdomains)
  managed_zone = google_dns_managed_zone.shinbee_japan.name
  name         = "${each.key}.your-domain.com."
  type         = "CNAME"
  ttl          = 60
  rrdatas      = [local.mikrotik_ddns]
}

resource "google_dns_record_set" "test_cname" {
  for_each     = toset(local.test_subdomains)
  managed_zone = google_dns_managed_zone.shinbee_japan.name
  name         = "${each.key}.your-domain.com."
  type         = "CNAME"
  ttl          = 60
  rrdatas      = [local.mikrotik_ddns]
}

# fax subdomain uses A record (updated by script) because it has an MX record
# CNAME + MX on the same name violates RFC 1034. Use DDNS update script instead.
resource "google_dns_record_set" "fax_a" {
  managed_zone = google_dns_managed_zone.shinbee_japan.name
  name         = "fax.your-domain.com."
  type         = "A"
  ttl          = 60
  rrdatas      = ["203.0.113.62"]
  lifecycle {
    ignore_changes = [rrdatas]
  }
}

# www → apex CNAME
resource "google_dns_record_set" "www_cname" {
  managed_zone = google_dns_managed_zone.shinbee_japan.name
  name         = "www.your-domain.com."
  type         = "CNAME"
  ttl          = 300
  rrdatas      = ["your-domain.com."]
}

# Fax inbound MX
resource "google_dns_record_set" "fax_mx" {
  managed_zone = google_dns_managed_zone.shinbee_japan.name
  name         = "fax.your-domain.com."
  type         = "MX"
  ttl          = 300
  rrdatas      = ["10 fax.your-domain.com."]
}

# --- Outputs ---

output "cloud_dns_nameservers" {
  description = "Set these as nameservers at the Amazon registrar"
  value       = google_dns_managed_zone.shinbee_japan.name_servers
}
