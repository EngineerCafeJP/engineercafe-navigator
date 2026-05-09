resource "google_logging_metric" "chat_response_count" {
  name        = "engineer_cafe_chat_response_count"
  description = "Count of Phase 1a /api/chat structured response events."
  filter      = "${local.cloud_run_filter} jsonPayload.event=\"chat_response\""

  label_extractors = {
    language        = "EXTRACT(jsonPayload.language)"
    route           = "EXTRACT(jsonPayload.route)"
    rag_fallback    = "EXTRACT(jsonPayload.rag_fallback)"
    ltm_store_write = "EXTRACT(jsonPayload.ltm_store_write)"
  }

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"

    labels {
      key         = "language"
      value_type  = "STRING"
      description = "Language requested by the client."
    }
    labels {
      key         = "route"
      value_type  = "STRING"
      description = "Resolved route/category/agent from chat metadata."
    }
    labels {
      key         = "rag_fallback"
      value_type  = "STRING"
      description = "Whether the chat response used a fallback source."
    }
    labels {
      key         = "ltm_store_write"
      value_type  = "STRING"
      description = "Long-term memory write result: success, failed, or skipped."
    }
  }
}

resource "google_logging_metric" "chat_response_latency_ms" {
  name        = "engineer_cafe_chat_response_latency_ms"
  description = "Distribution of /api/chat response latency in milliseconds."
  filter      = "${local.cloud_run_filter} jsonPayload.event=\"chat_response\" jsonPayload.latency_ms:*"

  value_extractor = "EXTRACT(jsonPayload.latency_ms)"

  label_extractors = {
    language = "EXTRACT(jsonPayload.language)"
    route    = "EXTRACT(jsonPayload.route)"
  }

  bucket_options {
    explicit_buckets {
      bounds = [250, 500, 1000, 2000, 3000, 5000, 7500, 10000, 15000, 30000]
    }
  }

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "DISTRIBUTION"
    unit        = "ms"

    labels {
      key         = "language"
      value_type  = "STRING"
      description = "Language requested by the client."
    }
    labels {
      key         = "route"
      value_type  = "STRING"
      description = "Resolved route/category/agent from chat metadata."
    }
  }
}

resource "google_logging_metric" "chat_rag_fallback_count" {
  name        = "engineer_cafe_chat_rag_fallback_count"
  description = "Count of chat responses where rag_fallback is true."
  filter      = "${local.cloud_run_filter} jsonPayload.event=\"chat_response\" jsonPayload.rag_fallback=true"

  label_extractors = {
    language = "EXTRACT(jsonPayload.language)"
    route    = "EXTRACT(jsonPayload.route)"
  }

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"

    labels {
      key         = "language"
      value_type  = "STRING"
      description = "Language requested by the client."
    }
    labels {
      key         = "route"
      value_type  = "STRING"
      description = "Resolved route/category/agent from chat metadata."
    }
  }
}

resource "google_logging_metric" "stt_winner_count" {
  name        = "engineer_cafe_stt_winner_count"
  description = "Count of STT winner events by qwen, vosk, or none."
  filter      = "${local.cloud_run_filter} jsonPayload.event=\"stt_winner\""

  label_extractors = {
    stt_winner = "EXTRACT(jsonPayload.stt_winner)"
    language   = "EXTRACT(jsonPayload.language)"
    provider   = "EXTRACT(jsonPayload.provider)"
  }

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"

    labels {
      key         = "stt_winner"
      value_type  = "STRING"
      description = "Winning STT provider: qwen, vosk, or none."
    }
    labels {
      key         = "language"
      value_type  = "STRING"
      description = "Detected/requested STT language."
    }
    labels {
      key         = "provider"
      value_type  = "STRING"
      description = "Provider name emitted by the STT event."
    }
  }
}

resource "google_logging_metric" "stt_none_count" {
  name        = "engineer_cafe_stt_none_count"
  description = "Count of STT requests where neither Qwen nor Vosk succeeded."
  filter      = "${local.cloud_run_filter} jsonPayload.event=\"stt_winner\" jsonPayload.stt_winner=\"none\""

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
  }
}

resource "google_logging_metric" "stt_overall_duration_ms" {
  name        = "engineer_cafe_stt_overall_duration_ms"
  description = "Distribution of end-to-end STT winner latency in milliseconds."
  filter      = "${local.cloud_run_filter} jsonPayload.event=\"stt_winner\" jsonPayload.stt_overall_duration_ms:*"

  value_extractor = "EXTRACT(jsonPayload.stt_overall_duration_ms)"

  label_extractors = {
    stt_winner = "EXTRACT(jsonPayload.stt_winner)"
    language   = "EXTRACT(jsonPayload.language)"
  }

  bucket_options {
    explicit_buckets {
      bounds = [500, 1000, 2000, 3000, 4000, 6000, 8000, 10000, 15000, 30000]
    }
  }

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "DISTRIBUTION"
    unit        = "ms"

    labels {
      key         = "stt_winner"
      value_type  = "STRING"
      description = "Winning STT provider: qwen, vosk, or none."
    }
    labels {
      key         = "language"
      value_type  = "STRING"
      description = "Detected/requested STT language."
    }
  }
}

resource "google_logging_metric" "tts_complete_count" {
  name        = "engineer_cafe_tts_complete_count"
  description = "Count of TTS completion events by provider, language, success, cache, and fallback state."
  filter      = "${local.cloud_run_filter} jsonPayload.event=\"tts_complete\""

  label_extractors = {
    provider        = "EXTRACT(jsonPayload.provider)"
    language        = "EXTRACT(jsonPayload.language)"
    success         = "EXTRACT(jsonPayload.success)"
    tts_cache_hit   = "EXTRACT(jsonPayload.tts_cache_hit)"
    fallback_used   = "EXTRACT(jsonPayload.fallback_used)"
    fallback_source = "EXTRACT(jsonPayload.fallback_provider)"
  }

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"

    labels {
      key         = "provider"
      value_type  = "STRING"
      description = "Requested TTS provider."
    }
    labels {
      key         = "language"
      value_type  = "STRING"
      description = "TTS language."
    }
    labels {
      key         = "success"
      value_type  = "STRING"
      description = "Whether the TTS request completed successfully."
    }
    labels {
      key         = "tts_cache_hit"
      value_type  = "STRING"
      description = "Whether TTS returned from cache."
    }
    labels {
      key         = "fallback_used"
      value_type  = "STRING"
      description = "Whether TTS used a fallback provider."
    }
    labels {
      key         = "fallback_source"
      value_type  = "STRING"
      description = "Fallback provider when one was used."
    }
  }
}

resource "google_logging_metric" "tts_failure_count" {
  name        = "engineer_cafe_tts_failure_count"
  description = "Count of TTS completion events where success=false."
  filter      = "${local.cloud_run_filter} jsonPayload.event=\"tts_complete\" jsonPayload.success=false"

  label_extractors = {
    provider      = "EXTRACT(jsonPayload.provider)"
    language      = "EXTRACT(jsonPayload.language)"
    fallback_used = "EXTRACT(jsonPayload.fallback_used)"
    error_type    = "EXTRACT(jsonPayload.error_type)"
  }

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"

    labels {
      key         = "provider"
      value_type  = "STRING"
      description = "Requested TTS provider."
    }
    labels {
      key         = "language"
      value_type  = "STRING"
      description = "TTS language."
    }
    labels {
      key         = "fallback_used"
      value_type  = "STRING"
      description = "Whether TTS attempted fallback before failure."
    }
    labels {
      key         = "error_type"
      value_type  = "STRING"
      description = "TTS exception class when available."
    }
  }
}

resource "google_logging_metric" "tts_overall_duration_ms" {
  name        = "engineer_cafe_tts_overall_duration_ms"
  description = "Distribution of TTS synthesis latency in milliseconds."
  filter      = "${local.cloud_run_filter} jsonPayload.event=\"tts_complete\" jsonPayload.tts_overall_duration_ms:*"

  value_extractor = "EXTRACT(jsonPayload.tts_overall_duration_ms)"

  label_extractors = {
    provider      = "EXTRACT(jsonPayload.provider)"
    language      = "EXTRACT(jsonPayload.language)"
    success       = "EXTRACT(jsonPayload.success)"
    fallback_used = "EXTRACT(jsonPayload.fallback_used)"
  }

  bucket_options {
    explicit_buckets {
      bounds = [250, 500, 1000, 2000, 3000, 5000, 8000, 10000, 15000, 30000]
    }
  }

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "DISTRIBUTION"
    unit        = "ms"

    labels {
      key         = "provider"
      value_type  = "STRING"
      description = "Requested TTS provider."
    }
    labels {
      key         = "language"
      value_type  = "STRING"
      description = "TTS language."
    }
    labels {
      key         = "success"
      value_type  = "STRING"
      description = "Whether the TTS request completed successfully."
    }
    labels {
      key         = "fallback_used"
      value_type  = "STRING"
      description = "Whether TTS used a fallback provider."
    }
  }
}

resource "google_logging_metric" "memory_helper_error_count" {
  name        = "engineer_cafe_memory_helper_error_count"
  description = "Count of existing structured root logs from backend.utils.memory_helper at ERROR level."
  filter      = "${local.cloud_run_filter} jsonPayload.logger=\"backend.utils.memory_helper\" jsonPayload.level=\"ERROR\""

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
  }
}
