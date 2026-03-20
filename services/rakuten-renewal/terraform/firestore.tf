# Firestore database (uses default if it exists, otherwise creates)
resource "google_firestore_database" "default" {
  project     = var.project_id
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"

  # Don't destroy the database if terraform destroy is run
  lifecycle {
    prevent_destroy = true
  }
}
