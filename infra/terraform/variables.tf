variable "project_id" {
  description = "Google Cloud project ID that owns the Cloud Run service and monitoring resources."
  type        = string
  default     = "aipartner-426616"
}

variable "region" {
  description = "Google Cloud region for regional resources and Cloud Run labels."
  type        = string
  default     = "asia-northeast1"
}

variable "alert_email" {
  description = "Email address for Cloud Monitoring alert notifications."
  type        = string
  default     = "terisuke1115@gmail.com"
}

variable "cloud_run_service_name" {
  description = "Cloud Run service name monitored by alert policies."
  type        = string
  default     = "engineer-cafe-backend"
}

