output "instance_name" {
  description = "GCE instance name"
  value       = google_compute_instance.k3s_server.name
}

output "instance_zone" {
  description = "GCE instance zone"
  value       = google_compute_instance.k3s_server.zone
}

output "external_ip" {
  description = "Ephemeral external IP (for Tailscale DERP/STUN)"
  value       = google_compute_instance.k3s_server.network_interface[0].access_config[0].nat_ip
}

output "service_account_email" {
  description = "Service account email for the K3s node"
  value       = google_service_account.k3s_node.email
}

output "tailscale_secret_id" {
  description = "Secret Manager secret ID for the Tailscale auth key"
  value       = google_secret_manager_secret.tailscale_authkey.secret_id
}

output "get_k3s_token" {
  description = "Command to retrieve the K3s join token (run after instance is up)"
  value       = "tailscale ssh root@k3s-control-0 cat /var/lib/rancher/k3s/server/node-token"
}

output "get_k3s_server_url" {
  description = "Command to retrieve the K3s server URL"
  value       = "echo https://$(tailscale ssh root@k3s-control-0 tailscale ip -4):6443"
}

output "get_wireguard_pubkey" {
  description = "Command to retrieve the WireGuard public key"
  value       = "tailscale ssh root@k3s-control-0 cat /etc/wireguard/public.key"
}

output "registry_url" {
  description = "Artifact Registry URL for tagging images"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.shinbee.repository_id}"
}

output "docker_push_setup" {
  description = "One-time command to configure Docker for AR push"
  value       = "gcloud auth configure-docker ${var.region}-docker.pkg.dev"
}
