# Archive the Cloud Function source code
data "archive_file" "sentinel_source" {
  type        = "zip"
  source_dir  = "${path.module}/sentinel"
  output_path = "${path.module}/.build/sentinel.zip"
}

# Upload source to GCS
resource "google_storage_bucket_object" "sentinel_source" {
  name   = "cloudfunctions/sentinel-${data.archive_file.sentinel_source.output_md5}.zip"
  bucket = "your-project-tfstate"
  source = data.archive_file.sentinel_source.output_path
}

# Cloud Function (2nd gen)
resource "google_cloudfunctions2_function" "sentinel" {
  name     = "rakuten-email-sentinel"
  location = var.region
  project  = var.project_id

  build_config {
    runtime     = "python312"
    entry_point = "handle_inbound_email"
    source {
      storage_source {
        bucket = google_storage_bucket_object.sentinel_source.bucket
        object = google_storage_bucket_object.sentinel_source.name
      }
    }
  }

  service_config {
    max_instance_count    = 1
    min_instance_count    = 0
    available_memory      = "256Mi"
    timeout_seconds       = 60
    service_account_email = google_service_account.sentinel.email

    environment_variables = {
      GCP_PROJECT          = var.project_id
      ADMIN_EMAIL          = var.admin_email
      WEBHOOK_SECRET       = var.sendgrid_webhook_secret
    }
  }

  depends_on = [
    google_project_service.apis,
  ]
}

# Allow unauthenticated access (SendGrid webhook)
resource "google_cloud_run_service_iam_member" "sentinel_invoker" {
  project  = var.project_id
  location = var.region
  service  = google_cloudfunctions2_function.sentinel.service_config[0].service

  role   = "roles/run.invoker"
  member = "allUsers"
}

output "sentinel_url" {
  description = "SendGrid webhook URL"
  value       = google_cloudfunctions2_function.sentinel.service_config[0].uri
}
