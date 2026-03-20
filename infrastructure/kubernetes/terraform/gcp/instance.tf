# K3s GCP control plane — e2-micro, Debian 12, Tailscale + WireGuard ready
resource "google_compute_instance" "k3s_server" {
  name         = "k3s-control-0"
  machine_type = var.machine_type
  zone         = var.zone

  tags = ["k3s-node"]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 20
      type  = "pd-standard"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.k3s.id

    # Static IP for Tailscale DERP/STUN, package installs, and Rakuten API proxy.
    # Access is via Tailscale SSH — no SSH on public IP.
    # Static IP is required for Rakuten RMS API IP allowlisting.
    access_config {
      nat_ip = google_compute_address.rakuten_proxy.address
    }
  }

  service_account {
    email  = google_service_account.k3s_node.email
    scopes = ["cloud-platform"]
  }

  metadata = {
    ts-secret-name = google_secret_manager_secret.tailscale_authkey.secret_id
  }

  metadata_startup_script = file("${path.module}/scripts/startup.sh")

  scheduling {
    automatic_restart   = true
    on_host_maintenance = "MIGRATE"
  }

  shielded_instance_config {
    enable_secure_boot = true
  }

  allow_stopping_for_update = true

  labels = {
    managed_by = "terraform"
    component  = "k3s"
    role       = "server"
  }
}
