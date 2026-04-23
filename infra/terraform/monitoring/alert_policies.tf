locals {
  notification_channels = [google_monitoring_notification_channel.email.name]
  cloud_run_filter      = "resource.type=\"cloud_run_revision\" AND resource.label.service_name=\"${var.cloud_run_service_name}\""
}

resource "google_monitoring_alert_policy" "cloud_run_5xx_rate" {
  project      = var.project_id
  display_name = "Engineer Cafe backend 5xx rate > 5%"
  combiner     = "OR"
  enabled      = true

  notification_channels = local.notification_channels

  conditions {
    display_name = "5xx responses exceed 5% over 5 minutes"

    condition_threshold {
      filter             = "metric.type=\"run.googleapis.com/request_count\" AND ${local.cloud_run_filter} AND metric.label.response_code_class=\"5xx\""
      denominator_filter = "metric.type=\"run.googleapis.com/request_count\" AND ${local.cloud_run_filter}"
      comparison         = "COMPARISON_GT"
      threshold_value    = 0.05
      duration           = "300s"

      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_RATE"
        cross_series_reducer = "REDUCE_SUM"
        group_by_fields      = ["resource.label.service_name"]
      }

      denominator_aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_RATE"
        cross_series_reducer = "REDUCE_SUM"
        group_by_fields      = ["resource.label.service_name"]
      }

      trigger {
        count = 1
      }
    }
  }
}

resource "google_monitoring_alert_policy" "chat_p95_latency" {
  project      = var.project_id
  display_name = "Engineer Cafe /api/chat p95 latency > 10s"
  combiner     = "OR"
  enabled      = true

  notification_channels = local.notification_channels

  conditions {
    display_name = "/api/chat p95 latency exceeds 10s over 10 minutes"

    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/chat_response_latency_ms\" AND ${local.cloud_run_filter}"
      comparison      = "COMPARISON_GT"
      threshold_value = 10000
      duration        = "600s"

      aggregations {
        alignment_period     = "600s"
        per_series_aligner   = "ALIGN_PERCENTILE_95"
        cross_series_reducer = "REDUCE_PERCENTILE_95"
        group_by_fields      = ["resource.label.service_name"]
      }

      trigger {
        count = 1
      }
    }
  }

  depends_on = [google_logging_metric.chat_response_latency_ms]
}

resource "google_monitoring_alert_policy" "ltm_store_success_rate" {
  project      = var.project_id
  display_name = "Engineer Cafe LTM store success rate < 95%"
  combiner     = "OR"
  enabled      = true

  notification_channels = local.notification_channels

  conditions {
    display_name = "LTM store success ratio below 95% over 10 minutes"

    condition_threshold {
      filter             = "metric.type=\"logging.googleapis.com/user/ltm_store_success_rate\" AND ${local.cloud_run_filter} AND metric.label.status=\"success\""
      denominator_filter = "metric.type=\"logging.googleapis.com/user/ltm_store_success_rate\" AND ${local.cloud_run_filter}"
      comparison         = "COMPARISON_LT"
      threshold_value    = 0.95
      duration           = "600s"

      aggregations {
        alignment_period     = "600s"
        per_series_aligner   = "ALIGN_RATE"
        cross_series_reducer = "REDUCE_SUM"
        group_by_fields      = ["resource.label.service_name"]
      }

      denominator_aggregations {
        alignment_period     = "600s"
        per_series_aligner   = "ALIGN_RATE"
        cross_series_reducer = "REDUCE_SUM"
        group_by_fields      = ["resource.label.service_name"]
      }

      trigger {
        count = 1
      }
    }
  }

  depends_on = [google_logging_metric.ltm_store_success_rate]
}

resource "google_monitoring_alert_policy" "hallucination_flag_count" {
  project      = var.project_id
  display_name = "Engineer Cafe hallucination flags > 5 / 10m"
  combiner     = "OR"
  enabled      = true

  notification_channels = local.notification_channels

  conditions {
    display_name = "Hallucination flags exceed 5 over 10 minutes"

    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/hallucination_flag_count\" AND ${local.cloud_run_filter}"
      comparison      = "COMPARISON_GT"
      threshold_value = 5
      duration        = "0s"

      aggregations {
        alignment_period     = "600s"
        per_series_aligner   = "ALIGN_SUM"
        cross_series_reducer = "REDUCE_SUM"
        group_by_fields      = ["resource.label.service_name"]
      }

      trigger {
        count = 1
      }
    }
  }

  depends_on = [google_logging_metric.hallucination_flag_count]
}

