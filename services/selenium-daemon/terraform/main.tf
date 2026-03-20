terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }

  backend "gcs" {
    bucket = "your-project-tfstate"
    prefix = "terraform/daemon"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# GCS bucket for waybill PDF archival + daemon logs
resource "google_storage_bucket" "daemon_archive" {
  name     = "${var.project_id}-daemon-archive"
  location = var.region

  uniform_bucket_level_access = true

  lifecycle_rule {
    condition {
      age = 90
    }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }

  lifecycle_rule {
    condition {
      age = 730 # 2 years
    }
    action {
      type = "Delete"
    }
  }
}

# IAM: allow WIF identity to upload to bucket
resource "google_storage_bucket_iam_member" "daemon_writer" {
  bucket = google_storage_bucket.daemon_archive.name
  role   = "roles/storage.objectAdmin"
  member = "principal://iam.googleapis.com/projects/${var.project_number}/locations/global/workloadIdentityPools/${var.wif_pool_id}/subject/CN=${var.client_cn}"
}
