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

variable "wif_pool_id" {
  description = "Workload Identity Pool ID"
  type        = string
  default     = "shinbee-pi-pool"
}

variable "client_cn" {
  description = "Client certificate CN for WIF"
  type        = string
  default     = "shinbee-pi"
}
