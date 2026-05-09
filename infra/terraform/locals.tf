locals {
  cloud_run_filter       = "resource.type=\"cloud_run_revision\" resource.labels.service_name=\"${var.cloud_run_service_name}\" resource.labels.location=\"${var.region}\""
  cloud_run_metric_scope = "resource.type=\"cloud_run_revision\" resource.label.service_name=\"${var.cloud_run_service_name}\" resource.label.location=\"${var.region}\""

  metric_type = {
    chat_response_count       = "logging.googleapis.com/user/${google_logging_metric.chat_response_count.name}"
    chat_rag_fallback_count   = "logging.googleapis.com/user/${google_logging_metric.chat_rag_fallback_count.name}"
    chat_response_latency_ms  = "logging.googleapis.com/user/${google_logging_metric.chat_response_latency_ms.name}"
    stt_winner_count          = "logging.googleapis.com/user/${google_logging_metric.stt_winner_count.name}"
    stt_none_count            = "logging.googleapis.com/user/${google_logging_metric.stt_none_count.name}"
    stt_overall_duration_ms   = "logging.googleapis.com/user/${google_logging_metric.stt_overall_duration_ms.name}"
    tts_complete_count        = "logging.googleapis.com/user/${google_logging_metric.tts_complete_count.name}"
    tts_failure_count         = "logging.googleapis.com/user/${google_logging_metric.tts_failure_count.name}"
    tts_overall_duration_ms   = "logging.googleapis.com/user/${google_logging_metric.tts_overall_duration_ms.name}"
    memory_helper_error_count = "logging.googleapis.com/user/${google_logging_metric.memory_helper_error_count.name}"
  }

  slo = {
    objective             = 0.98
    error_budget          = 0.02
    fast_burn_rate        = 14.4
    slow_burn_rate        = 6
    fast_burn_threshold   = 0.288
    slow_burn_threshold   = 0.12
    chat_latency_p95_ms   = 10000
    stt_latency_p95_ms    = 6000
    tts_latency_p95_ms    = 5000
    tts_failure_count_15  = 0
    memory_error_count_15 = 0
  }
}
