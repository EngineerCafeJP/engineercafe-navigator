resource "google_logging_metric" "rag_fallback_rate" {
  project = var.project_id
  name    = "rag_fallback_rate"
  filter  = <<-EOT
    resource.type="cloud_run_revision"
    resource.labels.service_name="${var.cloud_run_service_name}"
    jsonPayload.event="chat_response"
    jsonPayload.rag_fallback=true
  EOT

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"

    labels {
      key         = "language"
      value_type  = "STRING"
      description = "Response language."
    }
  }

  label_extractors = {
    language = "EXTRACT(jsonPayload.language)"
  }
}

resource "google_logging_metric" "ltm_store_success_rate" {
  project = var.project_id
  name    = "ltm_store_success_rate"
  filter  = <<-EOT
    resource.type="cloud_run_revision"
    resource.labels.service_name="${var.cloud_run_service_name}"
    jsonPayload.event="chat_response"
    jsonPayload.ltm_store_write!="skipped"
  EOT

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"

    labels {
      key         = "status"
      value_type  = "STRING"
      description = "Long-term memory write result."
    }
  }

  label_extractors = {
    status = "EXTRACT(jsonPayload.ltm_store_write)"
  }
}

resource "google_logging_metric" "ltm_cross_session_recall_rate" {
  project = var.project_id
  name    = "ltm_cross_session_recall_rate"
  filter  = <<-EOT
    resource.type="cloud_run_revision"
    resource.labels.service_name="${var.cloud_run_service_name}"
    jsonPayload.event="chat_response"
    (jsonPayload.sources:"ltm" OR jsonPayload.sources:"long_term_memory")
  EOT

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"

    labels {
      key         = "language"
      value_type  = "STRING"
      description = "Response language."
    }
  }

  label_extractors = {
    language = "EXTRACT(jsonPayload.language)"
  }
}

resource "google_logging_metric" "event_agent_calendar_hit_rate" {
  project = var.project_id
  name    = "event_agent_calendar_hit_rate"
  filter  = <<-EOT
    resource.type="cloud_run_revision"
    resource.labels.service_name="${var.cloud_run_service_name}"
    jsonPayload.event="chat_response"
    jsonPayload.route="EventAgent"
    jsonPayload.sources:"google_calendar"
  EOT

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"

    labels {
      key         = "language"
      value_type  = "STRING"
      description = "Response language."
    }
  }

  label_extractors = {
    language = "EXTRACT(jsonPayload.language)"
  }
}

resource "google_logging_metric" "hallucination_flag_count" {
  project = var.project_id
  name    = "hallucination_flag_count"
  filter  = <<-EOT
    resource.type="cloud_run_revision"
    resource.labels.service_name="${var.cloud_run_service_name}"
    jsonPayload.event="chat_response"
    jsonPayload.hallucination_flag=true
  EOT

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"

    labels {
      key         = "route"
      value_type  = "STRING"
      description = "Final response route."
    }
  }

  label_extractors = {
    route = "EXTRACT(jsonPayload.route)"
  }
}

resource "google_logging_metric" "chat_response_latency_ms" {
  project = var.project_id
  name    = "chat_response_latency_ms"
  filter  = <<-EOT
    resource.type="cloud_run_revision"
    resource.labels.service_name="${var.cloud_run_service_name}"
    jsonPayload.event="chat_response"
  EOT

  value_extractor = "EXTRACT(jsonPayload.latency_ms)"

  bucket_options {
    exponential_buckets {
      num_finite_buckets = 20
      growth_factor      = 2
      scale              = 100
    }
  }

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "DISTRIBUTION"
    unit        = "ms"

    labels {
      key         = "language"
      value_type  = "STRING"
      description = "Response language."
    }

    labels {
      key         = "route"
      value_type  = "STRING"
      description = "Final response route."
    }
  }

  label_extractors = {
    language = "EXTRACT(jsonPayload.language)"
    route    = "EXTRACT(jsonPayload.route)"
  }
}
