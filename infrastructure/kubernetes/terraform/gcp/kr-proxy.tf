# Korean traffic proxy — WireGuard split tunnel via GCP Seoul
# Bypasses NTT OCN PMTUD black hole to Korean servers (kakao, daum, etc.)
# MikroTik routes Korean IP prefixes through this tunnel.
# QoS: 1Mbps limit on MikroTik side to minimize egress costs.

# --- Subnet in Seoul region (reuse existing VPC) ---

resource "google_compute_subnetwork" "kr_proxy" {
  name          = "kr-proxy-subnet"
  ip_cidr_range = "10.10.1.0/24"
  region        = "asia-northeast3"
  network       = google_compute_network.k3s.id
}

# --- Static external IP (stable endpoint for MikroTik WireGuard peer) ---

resource "google_compute_address" "kr_proxy" {
  name         = "kr-proxy-ip"
  region       = "asia-northeast3"
  address_type = "EXTERNAL"
  network_tier = "STANDARD"

  labels = {
    managed_by = "terraform"
    component  = "kr-proxy"
  }
}

# --- Firewall: allow WireGuard from anywhere (MikroTik has dynamic PPPoE IP) ---

resource "google_compute_firewall" "kr_wireguard" {
  name    = "kr-proxy-allow-wireguard"
  network = google_compute_network.k3s.name

  allow {
    protocol = "udp"
    ports    = ["51822"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["kr-proxy"]
}

# --- Firewall: allow IAP SSH for management ---

resource "google_compute_firewall" "kr_iap_ssh" {
  name    = "kr-proxy-allow-iap-ssh"
  network = google_compute_network.k3s.name

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["35.235.240.0/20"]
  target_tags   = ["kr-proxy"]
}

# --- SPOT e2-micro instance in Seoul ---

resource "google_compute_instance" "kr_proxy" {
  name         = "kr-proxy"
  machine_type = "e2-micro"
  zone         = "asia-northeast3-a"

  tags = ["kr-proxy"]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 10
      type  = "pd-standard"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.kr_proxy.id

    access_config {
      nat_ip       = google_compute_address.kr_proxy.address
      network_tier = "STANDARD"
    }
  }

  can_ip_forward = true

  service_account {
    email  = google_service_account.k3s_node.email
    scopes = ["logging-write", "monitoring-write"]
  }

  metadata_startup_script = file("${path.module}/scripts/kr-proxy-startup.sh")

  scheduling {
    preemptible                 = true
    automatic_restart           = false
    provisioning_model          = "SPOT"
    instance_termination_action = "STOP"
  }

  shielded_instance_config {
    enable_secure_boot = true
  }

  allow_stopping_for_update = true

  labels = {
    managed_by = "terraform"
    component  = "kr-proxy"
  }
}

# --- Outputs ---

output "kr_proxy_ip" {
  description = "Static external IP for Korean traffic WireGuard proxy"
  value       = google_compute_address.kr_proxy.address
}
