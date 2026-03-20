variable "project_id" {
  description = "GCP project ID"
  type        = string
  default     = "your-gcp-project-id"
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "asia-northeast1"
}

variable "sendgrid_webhook_secret" {
  description = "Shared secret for SendGrid webhook validation"
  type        = string
  sensitive   = true
}

variable "sentinel_domain" {
  description = "Domain for inbound email (MX record)"
  type        = string
  default     = "sentinel.your-domain.com"
}

variable "admin_email" {
  description = "Admin email for forwarding"
  type        = string
  default     = "admin@your-domain.com"
}

variable "route53_zone_id" {
  description = "AWS Route53 hosted zone ID"
  type        = string
  default     = "YOUR_ZONE_ID"
}
