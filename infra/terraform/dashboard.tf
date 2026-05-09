resource "google_monitoring_dashboard" "observability_phase1b" {
  dashboard_json = jsonencode({
    displayName = "Engineer Cafe Observability Phase 1b"
    mosaicLayout = {
      columns = 12
      tiles = [
        {
          xPos   = 0
          yPos   = 0
          width  = 6
          height = 4
          widget = {
            title = "STT latency"
            xyChart = {
              dataSets = [
                {
                  plotType   = "LINE"
                  targetAxis = "Y1"
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"${local.metric_type.stt_overall_duration_ms}\" ${local.cloud_run_metric_scope}"
                      aggregation = {
                        alignmentPeriod    = "300s"
                        perSeriesAligner   = "ALIGN_PERCENTILE_95"
                        crossSeriesReducer = "REDUCE_MAX"
                        groupByFields      = ["metric.label.stt_winner"]
                      }
                    }
                  }
                }
              ]
              yAxis = {
                label = "p95 ms"
                scale = "LINEAR"
              }
            }
          }
        },
        {
          xPos   = 6
          yPos   = 0
          width  = 6
          height = 4
          widget = {
            title = "Chat response"
            xyChart = {
              dataSets = [
                {
                  plotType   = "LINE"
                  targetAxis = "Y1"
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"${local.metric_type.chat_response_latency_ms}\" ${local.cloud_run_metric_scope}"
                      aggregation = {
                        alignmentPeriod    = "300s"
                        perSeriesAligner   = "ALIGN_PERCENTILE_95"
                        crossSeriesReducer = "REDUCE_MAX"
                        groupByFields      = ["metric.label.route"]
                      }
                    }
                  }
                }
              ]
              yAxis = {
                label = "p95 ms"
                scale = "LINEAR"
              }
            }
          }
        },
        {
          xPos   = 0
          yPos   = 4
          width  = 6
          height = 4
          widget = {
            title = "Memory errors"
            xyChart = {
              dataSets = [
                {
                  plotType   = "STACKED_BAR"
                  targetAxis = "Y1"
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"${local.metric_type.memory_helper_error_count}\" ${local.cloud_run_metric_scope}"
                      aggregation = {
                        alignmentPeriod    = "900s"
                        perSeriesAligner   = "ALIGN_DELTA"
                        crossSeriesReducer = "REDUCE_SUM"
                      }
                    }
                  }
                }
              ]
              yAxis = {
                label = "errors / 15m"
                scale = "LINEAR"
              }
            }
          }
        },
        {
          xPos   = 6
          yPos   = 4
          width  = 6
          height = 4
          widget = {
            title = "Fallback rate"
            xyChart = {
              dataSets = [
                {
                  plotType   = "LINE"
                  targetAxis = "Y1"
                  timeSeriesQuery = {
                    timeSeriesFilterRatio = {
                      numerator = {
                        filter = "metric.type=\"${local.metric_type.chat_rag_fallback_count}\" ${local.cloud_run_metric_scope}"
                        aggregation = {
                          alignmentPeriod    = "300s"
                          perSeriesAligner   = "ALIGN_DELTA"
                          crossSeriesReducer = "REDUCE_SUM"
                        }
                      }
                      denominator = {
                        filter = "metric.type=\"${local.metric_type.chat_response_count}\" ${local.cloud_run_metric_scope}"
                        aggregation = {
                          alignmentPeriod    = "300s"
                          perSeriesAligner   = "ALIGN_DELTA"
                          crossSeriesReducer = "REDUCE_SUM"
                        }
                      }
                    }
                  }
                }
              ]
              yAxis = {
                label = "ratio"
                scale = "LINEAR"
              }
            }
          }
        },
        {
          xPos   = 0
          yPos   = 8
          width  = 6
          height = 4
          widget = {
            title = "TTS latency"
            xyChart = {
              dataSets = [
                {
                  plotType   = "LINE"
                  targetAxis = "Y1"
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"${local.metric_type.tts_overall_duration_ms}\" ${local.cloud_run_metric_scope}"
                      aggregation = {
                        alignmentPeriod    = "300s"
                        perSeriesAligner   = "ALIGN_PERCENTILE_95"
                        crossSeriesReducer = "REDUCE_MAX"
                        groupByFields      = ["metric.label.provider"]
                      }
                    }
                  }
                }
              ]
              yAxis = {
                label = "p95 ms"
                scale = "LINEAR"
              }
            }
          }
        },
        {
          xPos   = 6
          yPos   = 8
          width  = 6
          height = 4
          widget = {
            title = "TTS failures"
            xyChart = {
              dataSets = [
                {
                  plotType   = "STACKED_BAR"
                  targetAxis = "Y1"
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"${local.metric_type.tts_failure_count}\" ${local.cloud_run_metric_scope}"
                      aggregation = {
                        alignmentPeriod    = "900s"
                        perSeriesAligner   = "ALIGN_DELTA"
                        crossSeriesReducer = "REDUCE_SUM"
                        groupByFields      = ["metric.label.provider", "metric.label.error_type"]
                      }
                    }
                  }
                }
              ]
              yAxis = {
                label = "failures / 15m"
                scale = "LINEAR"
              }
            }
          }
        }
      ]
    }
  })
}
