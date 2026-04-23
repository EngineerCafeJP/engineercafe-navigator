variable "project_id" {
  description = "Google Cloud project ID."
  type        = string
}

variable "region" {
  description = "Google Cloud region."
  type        = string
}

variable "alert_email" {
  description = "Email address for Cloud Monitoring alert notifications."
  type        = string
}

variable "cloud_run_service_name" {
  description = "Cloud Run service name monitored by alert policies."
  type        = string
}

resource "google_monitoring_notification_channel" "email" {
  project      = var.project_id
  display_name = "Engineer Cafe observability alerts"
  type         = "email"

  labels = {
    email_address = var.alert_email
  }
}

