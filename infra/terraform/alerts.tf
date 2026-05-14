resource "google_monitoring_alert_policy" "chat_fallback_burn_rate" {
  display_name = "Engineer Cafe chat fallback burn rate"
  combiner     = "AND"
  enabled      = var.alert_enabled

  notification_channels = var.notification_channel_ids

  documentation {
    content   = "Chat fallback ratio is consuming the 98% chat quality SLO error budget in both the 1h and 6h windows. See docs/observability-runbook.md."
    mime_type = "text/markdown"
  }

  conditions {
    display_name = "1h fallback burn rate > 14.4x budget"

    condition_threshold {
      filter                  = "metric.type=\"${local.metric_type.chat_rag_fallback_count}\" ${local.cloud_run_metric_scope}"
      denominator_filter      = "metric.type=\"${local.metric_type.chat_response_count}\" ${local.cloud_run_metric_scope}"
      comparison              = "COMPARISON_GT"
      threshold_value         = local.slo.fast_burn_threshold
      duration                = "0s"
      evaluation_missing_data = "EVALUATION_MISSING_DATA_INACTIVE"

      aggregations {
        alignment_period     = "3600s"
        per_series_aligner   = "ALIGN_DELTA"
        cross_series_reducer = "REDUCE_SUM"
      }

      denominator_aggregations {
        alignment_period     = "3600s"
        per_series_aligner   = "ALIGN_DELTA"
        cross_series_reducer = "REDUCE_SUM"
      }

      trigger {
        count = 1
      }
    }
  }

  conditions {
    display_name = "6h fallback burn rate > 6x budget"

    condition_threshold {
      filter                  = "metric.type=\"${local.metric_type.chat_rag_fallback_count}\" ${local.cloud_run_metric_scope}"
      denominator_filter      = "metric.type=\"${local.metric_type.chat_response_count}\" ${local.cloud_run_metric_scope}"
      comparison              = "COMPARISON_GT"
      threshold_value         = local.slo.slow_burn_threshold
      duration                = "0s"
      evaluation_missing_data = "EVALUATION_MISSING_DATA_INACTIVE"

      aggregations {
        alignment_period     = "21600s"
        per_series_aligner   = "ALIGN_DELTA"
        cross_series_reducer = "REDUCE_SUM"
      }

      denominator_aggregations {
        alignment_period     = "21600s"
        per_series_aligner   = "ALIGN_DELTA"
        cross_series_reducer = "REDUCE_SUM"
      }

      trigger {
        count = 1
      }
    }
  }
}

resource "google_monitoring_alert_policy" "stt_failure_burn_rate" {
  display_name = "Engineer Cafe STT failure burn rate"
  combiner     = "AND"
  enabled      = var.alert_enabled

  notification_channels = var.notification_channel_ids

  documentation {
    content   = "STT winner=none ratio is consuming the 98% STT availability SLO error budget in both the 1h and 6h windows. See docs/observability-runbook.md."
    mime_type = "text/markdown"
  }

  conditions {
    display_name = "1h STT none burn rate > 14.4x budget"

    condition_threshold {
      filter                  = "metric.type=\"${local.metric_type.stt_none_count}\" ${local.cloud_run_metric_scope}"
      denominator_filter      = "metric.type=\"${local.metric_type.stt_winner_count}\" ${local.cloud_run_metric_scope}"
      comparison              = "COMPARISON_GT"
      threshold_value         = local.slo.fast_burn_threshold
      duration                = "0s"
      evaluation_missing_data = "EVALUATION_MISSING_DATA_INACTIVE"

      aggregations {
        alignment_period     = "3600s"
        per_series_aligner   = "ALIGN_DELTA"
        cross_series_reducer = "REDUCE_SUM"
      }

      denominator_aggregations {
        alignment_period     = "3600s"
        per_series_aligner   = "ALIGN_DELTA"
        cross_series_reducer = "REDUCE_SUM"
      }

      trigger {
        count = 1
      }
    }
  }

  conditions {
    display_name = "6h STT none burn rate > 6x budget"

    condition_threshold {
      filter                  = "metric.type=\"${local.metric_type.stt_none_count}\" ${local.cloud_run_metric_scope}"
      denominator_filter      = "metric.type=\"${local.metric_type.stt_winner_count}\" ${local.cloud_run_metric_scope}"
      comparison              = "COMPARISON_GT"
      threshold_value         = local.slo.slow_burn_threshold
      duration                = "0s"
      evaluation_missing_data = "EVALUATION_MISSING_DATA_INACTIVE"

      aggregations {
        alignment_period     = "21600s"
        per_series_aligner   = "ALIGN_DELTA"
        cross_series_reducer = "REDUCE_SUM"
      }

      denominator_aggregations {
        alignment_period     = "21600s"
        per_series_aligner   = "ALIGN_DELTA"
        cross_series_reducer = "REDUCE_SUM"
      }

      trigger {
        count = 1
      }
    }
  }
}

resource "google_monitoring_alert_policy" "chat_latency_p95" {
  display_name = "Engineer Cafe chat response p95 latency"
  combiner     = "OR"
  enabled      = var.alert_enabled

  notification_channels = var.notification_channel_ids

  documentation {
    content   = "Chat response p95 latency exceeded 10s for 15 minutes. See docs/observability-runbook.md."
    mime_type = "text/markdown"
  }

  conditions {
    display_name = "chat_response p95 > 10000 ms"

    condition_threshold {
      filter                  = "metric.type=\"${local.metric_type.chat_response_latency_ms}\" ${local.cloud_run_metric_scope}"
      comparison              = "COMPARISON_GT"
      threshold_value         = local.slo.chat_latency_p95_ms
      duration                = "900s"
      evaluation_missing_data = "EVALUATION_MISSING_DATA_INACTIVE"

      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_PERCENTILE_95"
        cross_series_reducer = "REDUCE_MAX"
        group_by_fields = [
          "resource.label.service_name",
        ]
      }

      trigger {
        count = 1
      }
    }
  }
}

resource "google_monitoring_alert_policy" "stt_latency_p95" {
  display_name = "Engineer Cafe STT p95 latency"
  combiner     = "OR"
  enabled      = var.alert_enabled

  notification_channels = var.notification_channel_ids

  documentation {
    content   = "STT p95 latency exceeded 6s for 15 minutes. See docs/observability-runbook.md."
    mime_type = "text/markdown"
  }

  conditions {
    display_name = "stt_overall p95 > 6000 ms"

    condition_threshold {
      filter                  = "metric.type=\"${local.metric_type.stt_overall_duration_ms}\" ${local.cloud_run_metric_scope}"
      comparison              = "COMPARISON_GT"
      threshold_value         = local.slo.stt_latency_p95_ms
      duration                = "900s"
      evaluation_missing_data = "EVALUATION_MISSING_DATA_INACTIVE"

      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_PERCENTILE_95"
        cross_series_reducer = "REDUCE_MAX"
        group_by_fields = [
          "resource.label.service_name",
        ]
      }

      trigger {
        count = 1
      }
    }
  }
}

resource "google_monitoring_alert_policy" "tts_latency_p95" {
  display_name = "Engineer Cafe TTS p95 latency"
  combiner     = "OR"
  enabled      = var.alert_enabled

  notification_channels = var.notification_channel_ids

  documentation {
    content   = "TTS p95 latency exceeded the onsite pass window of 5s for 15 minutes. See docs/observability-runbook.md."
    mime_type = "text/markdown"
  }

  conditions {
    display_name = "tts_complete p95 > 5000 ms"

    condition_threshold {
      filter                  = "metric.type=\"${local.metric_type.tts_overall_duration_ms}\" ${local.cloud_run_metric_scope}"
      comparison              = "COMPARISON_GT"
      threshold_value         = local.slo.tts_latency_p95_ms
      duration                = "900s"
      evaluation_missing_data = "EVALUATION_MISSING_DATA_INACTIVE"

      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_PERCENTILE_95"
        cross_series_reducer = "REDUCE_MAX"
        group_by_fields = [
          "resource.label.service_name",
        ]
      }

      trigger {
        count = 1
      }
    }
  }
}

resource "google_monitoring_alert_policy" "tts_failures" {
  display_name = "Engineer Cafe TTS failures"
  combiner     = "OR"
  enabled      = var.alert_enabled

  notification_channels = var.notification_channel_ids

  documentation {
    content   = "TTS emitted one or more success=false completion events in 15 minutes. See docs/observability-runbook.md."
    mime_type = "text/markdown"
  }

  conditions {
    display_name = "tts_complete success=false count > 0"

    condition_threshold {
      filter                  = "metric.type=\"${local.metric_type.tts_failure_count}\" ${local.cloud_run_metric_scope}"
      comparison              = "COMPARISON_GT"
      threshold_value         = local.slo.tts_failure_count_15
      duration                = "0s"
      evaluation_missing_data = "EVALUATION_MISSING_DATA_INACTIVE"

      aggregations {
        alignment_period     = "900s"
        per_series_aligner   = "ALIGN_DELTA"
        cross_series_reducer = "REDUCE_SUM"
      }

      trigger {
        count = 1
      }
    }
  }
}

resource "google_monitoring_alert_policy" "memory_helper_errors" {
  display_name = "Engineer Cafe memory helper errors"
  combiner     = "OR"
  enabled      = var.alert_enabled

  notification_channels = var.notification_channel_ids

  documentation {
    content   = "backend.utils.memory_helper emitted ERROR logs. See docs/observability-runbook.md."
    mime_type = "text/markdown"
  }

  conditions {
    display_name = "memory_helper ERROR count > 0"

    condition_threshold {
      filter                  = "metric.type=\"${local.metric_type.memory_helper_error_count}\" ${local.cloud_run_metric_scope}"
      comparison              = "COMPARISON_GT"
      threshold_value         = local.slo.memory_error_count_15
      duration                = "0s"
      evaluation_missing_data = "EVALUATION_MISSING_DATA_INACTIVE"

      aggregations {
        alignment_period     = "900s"
        per_series_aligner   = "ALIGN_DELTA"
        cross_series_reducer = "REDUCE_SUM"
      }

      trigger {
        count = 1
      }
    }
  }
}

resource "google_monitoring_alert_policy" "critical_api_errors" {
  display_name = "Engineer Cafe critical API errors"
  combiner     = "OR"
  enabled      = var.alert_enabled

  notification_channels = var.notification_channel_ids

  documentation {
    content   = "/api/voice, /api/chat, /api/slides, or /api/error emitted ERROR/5xx logs. See docs/observability-runbook.md."
    mime_type = "text/markdown"
  }

  conditions {
    display_name = "critical API ERROR/5xx count > 0"

    condition_threshold {
      filter                  = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.api_error_count.name}\" ${local.cloud_run_metric_scope}"
      comparison              = "COMPARISON_GT"
      threshold_value         = 0
      duration                = "0s"
      evaluation_missing_data = "EVALUATION_MISSING_DATA_INACTIVE"

      aggregations {
        alignment_period     = "900s"
        per_series_aligner   = "ALIGN_DELTA"
        cross_series_reducer = "REDUCE_SUM"
      }

      trigger {
        count = 1
      }
    }
  }
}

resource "google_monitoring_alert_policy" "ltm_connection_errors" {
  display_name = "Engineer Cafe LTM connection errors"
  combiner     = "OR"
  enabled      = var.alert_enabled

  notification_channels = var.notification_channel_ids

  documentation {
    content   = "Long-term memory connection or timeout errors were logged. See docs/observability-runbook.md."
    mime_type = "text/markdown"
  }

  conditions {
    display_name = "LTM connection/timeout count > 0"

    condition_threshold {
      filter                  = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.ltm_connection_error_count.name}\" ${local.cloud_run_metric_scope}"
      comparison              = "COMPARISON_GT"
      threshold_value         = 0
      duration                = "0s"
      evaluation_missing_data = "EVALUATION_MISSING_DATA_INACTIVE"

      aggregations {
        alignment_period     = "900s"
        per_series_aligner   = "ALIGN_DELTA"
        cross_series_reducer = "REDUCE_SUM"
      }

      trigger {
        count = 1
      }
    }
  }
}
