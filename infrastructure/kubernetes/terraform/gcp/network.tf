# Dedicated VPC for K3s nodes — no default network dependencies
resource "google_compute_network" "k3s" {
  name                    = "k3s-network"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "k3s" {
  name          = "k3s-subnet"
  ip_cidr_range = "10.10.0.0/24"
  region        = var.region
  network       = google_compute_network.k3s.id
}

# Allow SSH from IAP (GCP console serial/SSH) — no public SSH needed,
# Tailscale SSH is the primary access method
resource "google_compute_firewall" "iap_ssh" {
  name    = "k3s-allow-iap-ssh"
  network = google_compute_network.k3s.name

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  # IAP forwarding range
  source_ranges = ["35.235.240.0/20"]
  target_tags   = ["k3s-node"]
}

# Allow all internal traffic within the subnet
resource "google_compute_firewall" "internal" {
  name    = "k3s-allow-internal"
  network = google_compute_network.k3s.name

  allow {
    protocol = "tcp"
  }
  allow {
    protocol = "udp"
  }
  allow {
    protocol = "icmp"
  }

  source_ranges = ["10.10.0.0/24"]
  target_tags   = ["k3s-node"]
}

# Allow Squid proxy (TCP 3128) from Tailscale and K8s pod networks
# K8s pods route Rakuten API traffic through this proxy for static IP egress
resource "google_compute_firewall" "squid_proxy" {
  name    = "k3s-allow-squid-proxy"
  network = google_compute_network.k3s.name

  allow {
    protocol = "tcp"
    ports    = ["3128"]
  }

  # Tailscale CGNAT range + K8s pod/service CIDRs
  source_ranges = ["100.64.0.0/10", "10.42.0.0/16", "10.43.0.0/16"]
  target_tags   = ["k3s-node"]
}

# Allow Tailscale DERP/STUN (UDP 41641), WireGuard admin (UDP 51820),
# and WireGuard K3s tunnel (UDP 51821) from MikroTik
resource "google_compute_firewall" "tailscale_wireguard" {
  name    = "k3s-allow-tailscale-wg"
  network = google_compute_network.k3s.name

  allow {
    protocol = "udp"
    ports    = ["41641", "51820", "51821"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["k3s-node"]
}
