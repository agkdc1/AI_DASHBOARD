output "sentinel_service_account" {
  description = "Sentinel Cloud Function service account email"
  value       = google_service_account.sentinel.email
}

output "sentinel_function_url" {
  description = "Sentinel Cloud Function HTTPS endpoint (set as SendGrid webhook URL)"
  value       = google_cloudfunctions2_function.sentinel.service_config[0].uri
}
