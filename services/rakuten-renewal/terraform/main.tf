terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "gcs" {
    bucket = "your-project-tfstate"
    prefix = "terraform/rakuten"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "aws" {
  region = "ap-northeast-1"
}

# Enable required APIs
resource "google_project_service" "apis" {
  for_each = toset([
    "cloudfunctions.googleapis.com",
    "firestore.googleapis.com",
    "aiplatform.googleapis.com",
    "cloudbuild.googleapis.com",
    "run.googleapis.com",
  ])

  project = var.project_id
  service = each.value

  disable_on_destroy = false
}

# Service account for the Sentinel Cloud Function
resource "google_service_account" "sentinel" {
  account_id   = "rakuten-sentinel"
  display_name = "Rakuten Email Sentinel"
  project      = var.project_id
}

resource "google_project_iam_member" "sentinel_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.sentinel.email}"
}

resource "google_project_iam_member" "sentinel_aiplatform" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.sentinel.email}"
}

# GCS lifecycle rule for session log cleanup (2 years)
resource "google_storage_bucket_object" "rakuten_logs_marker" {
  name    = "rakuten-logs/.keep"
  content = ""
  bucket  = "your-project-vault-backup"
}
