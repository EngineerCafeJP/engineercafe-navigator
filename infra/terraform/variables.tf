variable "project_id" {
  description = "GCP project that hosts Cloud Run and Cloud Monitoring."
  type        = string
  default     = "aipartner-426616"
}

variable "region" {
  description = "Default GCP region for provider operations."
  type        = string
  default     = "asia-northeast1"
}

variable "cloud_run_service_name" {
  description = "Cloud Run service name that emits Phase 1a structured logs."
  type        = string
  default     = "engineer-cafe-backend"
}

variable "notification_channel_ids" {
  description = "Monitoring notification channel resource IDs. Leave empty for PR validation; set before manual apply."
  type        = list(string)
  default     = []
}

variable "alert_enabled" {
  description = "Whether Terraform-managed alert policies are enabled."
  type        = bool
  default     = true
}

variable "manage_runtime_secrets" {
  description = "Whether Terraform should manage Secret Manager secret containers for runtime API keys. Keep false unless secrets are imported or created through Terraform."
  type        = bool
  default     = false
}

variable "runtime_secret_ids" {
  description = "Secret Manager secret IDs required by the Cloud Run runtime. Terraform manages only secret containers, never secret versions or values."
  type        = set(string)
  default = [
    "CEREBRAS_API_KEY",
  ]
}
