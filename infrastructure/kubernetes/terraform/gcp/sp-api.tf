# GCP service account for Amazon SP-API WIF+STS.
#
# The InvenTree plugin uses this SA to get a Google OIDC token,
# then calls AWS STS AssumeRoleWithWebIdentity to get temporary
# AWS credentials for SP-API SigV4 signing (no long-lived AWS keys).

resource "google_service_account" "sp_api" {
  account_id   = "sp-api"
  display_name = "Amazon SP-API (WIF→AWS STS)"
  description  = "Generates OIDC tokens for AWS STS AssumeRoleWithWebIdentity"
}

# Allow the SA to generate OIDC tokens for itself
resource "google_service_account_iam_member" "sp_api_token_creator" {
  service_account_id = google_service_account.sp_api.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:${google_service_account.sp_api.email}"
}

# SA key — mounted into InvenTree pod for OIDC token generation
resource "google_service_account_key" "sp_api" {
  service_account_id = google_service_account.sp_api.name
}

# Store the key in GCP Secret Manager
resource "google_secret_manager_secret" "sp_api_sa_key" {
  secret_id = "sp-api-sa-key"

  replication {
    auto {}
  }

  labels = {
    purpose   = "sp-api-wif"
    managedby = "terraform"
  }
}

resource "google_secret_manager_secret_version" "sp_api_sa_key" {
  secret      = google_secret_manager_secret.sp_api_sa_key.id
  secret_data = base64decode(google_service_account_key.sp_api.private_key)
}

output "sp_api_sa_email" {
  description = "GCP SA email for SP-API WIF"
  value       = google_service_account.sp_api.email
}

output "sp_api_sa_unique_id" {
  description = "GCP SA unique ID (used in AWS OIDC trust policy 'sub' condition)"
  value       = google_service_account.sp_api.unique_id
}
