output "dashboard_id" {
  description = "Terraform-managed Cloud Monitoring dashboard ID."
  value       = google_monitoring_dashboard.observability_phase1b.id
}

output "alert_policy_ids" {
  description = "Terraform-managed alert policy IDs."
  value = {
    chat_fallback_burn_rate = google_monitoring_alert_policy.chat_fallback_burn_rate.id
    stt_failure_burn_rate   = google_monitoring_alert_policy.stt_failure_burn_rate.id
    chat_latency_p95        = google_monitoring_alert_policy.chat_latency_p95.id
    stt_latency_p95         = google_monitoring_alert_policy.stt_latency_p95.id
    tts_latency_p95         = google_monitoring_alert_policy.tts_latency_p95.id
    tts_failures            = google_monitoring_alert_policy.tts_failures.id
    memory_helper_errors    = google_monitoring_alert_policy.memory_helper_errors.id
  }
}
