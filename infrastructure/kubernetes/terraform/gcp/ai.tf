# AI Assistant — SA + GCS buckets + API enablement.
# Vertex AI (Gemini) and Speech-to-Text for meeting transcription.

# --- APIs ---

resource "google_project_service" "aiplatform" {
  service            = "aiplatform.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "speech" {
  service            = "speech.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "texttospeech" {
  service            = "texttospeech.googleapis.com"
  disable_on_destroy = false
}

# --- Service Account ---

resource "google_service_account" "ai_assistant" {
  account_id   = "ai-assistant"
  display_name = "AI Assistant"
  description  = "Gemini guidance, PII masking, meeting transcription, task management"
}

resource "google_project_iam_member" "ai_vertex" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.ai_assistant.email}"
}

resource "google_project_iam_member" "ai_speech" {
  project = var.project_id
  role    = "roles/speech.client"
  member  = "serviceAccount:${google_service_account.ai_assistant.email}"
}

# Note: Cloud TTS has no predefined IAM role. Access is granted by enabling the
# API and using the SA key. The SA already has sufficient project-level permissions.

# SA key — stored in Secret Manager, deployed to K8s by render-k8s-secrets.sh
resource "google_service_account_key" "ai_assistant" {
  service_account_id = google_service_account.ai_assistant.name
}

resource "google_secret_manager_secret" "ai_assistant_key" {
  secret_id = "ai-assistant-key"

  replication {
    auto {}
  }

  labels = {
    managed_by = "terraform"
    component  = "ai"
  }
}

resource "google_secret_manager_secret_version" "ai_assistant_key" {
  secret      = google_secret_manager_secret.ai_assistant_key.id
  secret_data = base64decode(google_service_account_key.ai_assistant.private_key)
}

resource "google_secret_manager_secret_iam_member" "wif_read_ai_key" {
  secret_id = google_secret_manager_secret.ai_assistant_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "principalSet://iam.googleapis.com/projects/${var.project_number}/locations/global/workloadIdentityPools/shinbee-pi-pool/*"
}

# --- GCS Buckets ---

# Raw PII data — auto-deleted after 7 days (GDPR/APPI compliance)
resource "google_storage_bucket" "pii_raw" {
  name                        = "your-project-pii-raw"
  location                    = "ASIA-NORTHEAST1"
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true

  lifecycle_rule {
    condition { age = 7 }
    action { type = "Delete" }
  }

  labels = {
    managed_by = "terraform"
    component  = "ai"
    data_class = "pii"
  }
}

# AI interaction logs — for weekly evolution analysis
resource "google_storage_bucket" "ai_logs" {
  name                        = "your-project-ai-logs"
  location                    = "ASIA-NORTHEAST1"
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true

  lifecycle_rule {
    condition { age = 90 }
    action { type = "Delete" }
  }

  labels = {
    managed_by = "terraform"
    component  = "ai"
  }
}

# SOP documents bucket — operational procedure manuals for RAG context
resource "google_storage_bucket" "ai_sops" {
  name                        = "your-project-ai-sops"
  location                    = "ASIA-NORTHEAST1"
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true

  labels = {
    managed_by = "terraform"
    component  = "ai"
  }
}

# SA access to all 3 buckets
resource "google_storage_bucket_iam_member" "ai_pii_raw" {
  bucket = google_storage_bucket.pii_raw.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.ai_assistant.email}"
}

resource "google_storage_bucket_iam_member" "ai_logs" {
  bucket = google_storage_bucket.ai_logs.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.ai_assistant.email}"
}

resource "google_storage_bucket_iam_member" "ai_sops" {
  bucket = google_storage_bucket.ai_sops.name
  role   = "roles/storage.objectUser"
  member = "serviceAccount:${google_service_account.ai_assistant.email}"
}
