variable "project_id" {
  description = "GCP project ID"
  type        = string
  default     = "your-gcp-project-id"
}

variable "project_number" {
  description = "GCP project number"
  type        = string
  default     = "000000000000"
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "asia-northeast1"
}

variable "zone" {
  description = "GCP zone"
  type        = string
  default     = "asia-northeast1-b"
}

variable "machine_type" {
  description = "GCE machine type"
  type        = string
  default     = "e2-small"
}
