output "archive_bucket_name" {
  description = "GCS bucket for daemon archive (PDFs + logs)"
  value       = google_storage_bucket.daemon_archive.name
}

output "archive_bucket_url" {
  description = "GCS bucket URL"
  value       = google_storage_bucket.daemon_archive.url
}
