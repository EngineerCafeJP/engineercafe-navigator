#!/usr/bin/env bash
set -euo pipefail

# Alpha final /api/chat live RAGAS wrapper.
#
# Usage:
#   scripts/rag-api-live-test.sh
#   scripts/rag-api-live-test.sh --languages ja,en --dry-run
#   scripts/rag-api-live-test.sh --case-suite alpha-127
#
# Env:
#   API_SECRET_KEY                 Required unless --key is provided or gcloud can read it.
#   RAG_API_LIVE_BASE_URL          Overrides default Cloud Run URL.
#   RAG_API_LIVE_SECRET_PROJECT    Overrides Secret Manager project.
#   RAG_API_LIVE_METRICS           Comma-separated RAGAS metrics.
#   RAG_API_LIVE_CHAT_INTERVAL_SECONDS
#                                   Minimum seconds between /api/chat starts (default: 2.2).
#   RAG_API_LIVE_TOTAL_TIMEOUT_SECONDS
#                                   Whole runner wall-clock timeout; 0 disables (default: 7200).
#   OPENAI_API_KEY / OPENROUTER_API_KEY are required by the RAGAS evaluator.
#   If neither is set, this script tries Secret Manager. Direct OpenAI is preferred.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNNER="$ROOT_DIR/backend/evaluation/run_live_api_eval.py"
DEFAULT_URL="https://engineer-cafe-backend-639959525777.asia-northeast1.run.app"
BASE_URL="${RAG_API_LIVE_BASE_URL:-$DEFAULT_URL}"
API_KEY="${API_SECRET_KEY:-}"
SECRET_PROJECT="${RAG_API_LIVE_SECRET_PROJECT:-aipartner-426616}"
SECRET_NAME="API_SECRET_KEY"
OPENAI_SECRET_NAMES="${RAG_API_LIVE_OPENAI_SECRET_NAMES:-OPENAI_API_KEY,openai-api-key}"
OPENROUTER_SECRET_NAMES="${RAG_API_LIVE_OPENROUTER_SECRET_NAMES:-OPENROUTER_API_KEY}"
OUTPUT_DIR="$ROOT_DIR/backend/tests/evaluation/reports"
LANGUAGES="ja,en,zh,ko"
METRICS="${RAG_API_LIVE_METRICS:-answer_correctness}"
CASE_SUITE="${RAG_API_LIVE_CASE_SUITE:-diagnostic-29}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
CHAT_INTERVAL_SECONDS="${RAG_API_LIVE_CHAT_INTERVAL_SECONDS:-2.2}"
CHAT_RETRY_ATTEMPTS="${RAG_API_LIVE_CHAT_RETRY_ATTEMPTS:-4}"
CHAT_RETRY_BACKOFF_SECONDS="${RAG_API_LIVE_CHAT_RETRY_BACKOFF_SECONDS:-2.0}"
TOTAL_TIMEOUT_SECONDS="${RAG_API_LIVE_TOTAL_TIMEOUT_SECONDS:-7200}"
DRY_RUN=0
CHECK_TARGETS=1

usage() {
  sed -n '3,19p' "$0"
  cat <<'EOF'

Options:
  --host URL             Backend base URL (default: Cloud Run live URL)
  --key VALUE            API key; skips Secret Manager lookup
  --secret-project ID    GCP project for Secret Manager (default: aipartner-426616)
  --secret-name NAME     Secret Manager secret name (default: API_SECRET_KEY)
  --openai-secret-names  Comma-separated OpenAI judge secret names (default: OPENAI_API_KEY,openai-api-key)
  --openrouter-secret-names
                         Comma-separated OpenRouter fallback secret names (default: OPENROUTER_API_KEY)
  --languages LIST       Comma-separated languages (default: ja,en,zh,ko)
  --metrics LIST         Comma-separated RAGAS metrics (default: answer_correctness)
  --case-suite NAME      diagnostic-29 (fast path) or alpha-127 (release gate)
  --output-dir DIR       Report directory (default: backend/tests/evaluation/reports)
  --timestamp VALUE      Stable timestamp marker for logs and report names
  --chat-interval-seconds VALUE
                         Minimum seconds between live /api/chat request starts (default: 2.2)
  --chat-retry-attempts VALUE
                         Total /api/chat attempts for retryable 429 responses (default: 4)
  --chat-retry-backoff-seconds VALUE
                         Base exponential backoff seconds for retryable 429 responses (default: 2.0)
  RAG_API_LIVE_TOTAL_TIMEOUT_SECONDS
                         Whole runner wall-clock timeout; 0 disables (default: 7200)
  --no-check-targets     Do not fail when configured answer_correctness targets are missed
  --dry-run              Validate local prerequisites and print planned command only
  -h, --help             Show this usage

Outputs:
  backend/tests/evaluation/reports/live_api_eval_<timestamp>.json
  backend/tests/evaluation/reports/live_api_eval_<timestamp>.txt
EOF
  exit "${1:-0}"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --host) BASE_URL="$2"; shift 2 ;;
    --key) API_KEY="$2"; shift 2 ;;
    --secret-project) SECRET_PROJECT="$2"; shift 2 ;;
    --secret-name) SECRET_NAME="$2"; shift 2 ;;
    --openai-secret-names) OPENAI_SECRET_NAMES="$2"; shift 2 ;;
    --openrouter-secret-names) OPENROUTER_SECRET_NAMES="$2"; shift 2 ;;
    --languages) LANGUAGES="$2"; shift 2 ;;
    --metrics) METRICS="$2"; shift 2 ;;
    --case-suite) CASE_SUITE="$2"; shift 2 ;;
    --output-dir) OUTPUT_DIR="$2"; shift 2 ;;
    --timestamp) TIMESTAMP="$2"; shift 2 ;;
    --chat-interval-seconds) CHAT_INTERVAL_SECONDS="$2"; shift 2 ;;
    --chat-retry-attempts) CHAT_RETRY_ATTEMPTS="$2"; shift 2 ;;
    --chat-retry-backoff-seconds) CHAT_RETRY_BACKOFF_SECONDS="$2"; shift 2 ;;
    --no-check-targets) CHECK_TARGETS=0; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage 0 ;;
    *) echo "Unknown arg: $1" >&2; usage 1 ;;
  esac
done

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Error: required command not found: $1" >&2
    exit 2
  fi
}

fetch_api_key_from_gcloud() {
  if command -v gcloud >/dev/null 2>&1; then
    gcloud secrets versions access latest \
      --secret="$SECRET_NAME" --project="$SECRET_PROJECT" 2>/dev/null || true
  fi
}

fetch_secret_from_gcloud() {
  secret_name="$1"
  if command -v gcloud >/dev/null 2>&1; then
    gcloud secrets versions access latest \
      --secret="$secret_name" --project="$SECRET_PROJECT" 2>/dev/null || true
  fi
}

fetch_first_secret_from_gcloud() {
  local names_csv="$1"
  local value
  IFS=',' read -r -a names <<< "$names_csv"
  for secret_name in "${names[@]}"; do
    secret_name="$(printf '%s' "$secret_name" | xargs)"
    if [ -z "$secret_name" ]; then
      continue
    fi
    value="$(fetch_secret_from_gcloud "$secret_name")"
    if [ -n "$value" ]; then
      printf '%s' "$value"
      return 0
    fi
  done
}

require_ragas_judge_key() {
  if [ -z "${OPENAI_API_KEY:-}" ]; then
    OPENAI_API_KEY="$(fetch_first_secret_from_gcloud "$OPENAI_SECRET_NAMES")"
    export OPENAI_API_KEY
  fi
  if [ -z "${OPENAI_API_KEY:-}" ] && [ -z "${OPENROUTER_API_KEY:-}" ]; then
    OPENROUTER_API_KEY="$(fetch_first_secret_from_gcloud "$OPENROUTER_SECRET_NAMES")"
    export OPENROUTER_API_KEY
  fi
  if [ -n "${OPENAI_API_KEY:-}" ]; then
    echo "RAGAS judge provider: direct OpenAI"
    echo "RAGAS judge model: ${RAGAS_EVAL_MODEL:-gpt-5.2-2025-12-11}"
    return
  fi
  if [ -n "${OPENROUTER_API_KEY:-}" ]; then
    echo "RAGAS judge provider: OpenRouter fallback"
    echo "RAGAS judge model: ${RAGAS_OPENROUTER_MODEL:-openai/gpt-5-mini}"
    return
  fi

  echo "Error: C live RAGAS requires OPENAI_API_KEY or OPENROUTER_API_KEY." >&2
  echo "This gate judges live /api/chat answers against the golden dataset; without a judge key the score is not meaningful." >&2
  exit 2
}

validate_case_suite() {
  case "$CASE_SUITE" in
    diagnostic-29|alpha-127) ;;
    *)
      echo "Error: --case-suite must be diagnostic-29 or alpha-127, got: $CASE_SUITE" >&2
      exit 2
      ;;
  esac
}

expected_suite_cases() {
  case "$CASE_SUITE" in
    diagnostic-29) printf '29' ;;
    alpha-127) printf '127' ;;
  esac
}

language_args() {
  python3 - "$LANGUAGES" <<'PY'
import sys
langs = [x.strip() for x in sys.argv[1].split(",") if x.strip()]
for lang in langs:
    print(lang)
PY
}

metric_args() {
  python3 - "$METRICS" <<'PY'
import sys
metrics = [x.strip() for x in sys.argv[1].split(",") if x.strip()]
for metric in metrics:
    print(metric)
PY
}

main() {
  require_cmd python3
  validate_case_suite
  if [ ! -f "$RUNNER" ]; then
    echo "Error: live API RAGAS runner not found: $RUNNER" >&2
    exit 2
  fi

  LANG_ARGS=()
  while IFS= read -r lang; do
    LANG_ARGS+=("$lang")
  done < <(language_args)
  if [ "${#LANG_ARGS[@]}" -eq 0 ]; then
    echo "Error: --languages produced an empty list" >&2
    exit 2
  fi
  METRIC_ARGS=()
  while IFS= read -r metric; do
    METRIC_ARGS+=("$metric")
  done < <(metric_args)
  if [ "${#METRIC_ARGS[@]}" -eq 0 ]; then
    echo "Error: --metrics produced an empty list" >&2
    exit 2
  fi

  if [ "$DRY_RUN" = "1" ]; then
    echo "Dry run: no /api/chat live RAGAS commands will be executed."
    echo "Timestamp: $TIMESTAMP"
    echo "Runner: $RUNNER"
    echo "Base URL: $BASE_URL"
    echo "Output dir: $OUTPUT_DIR"
    echo "Case suite: $CASE_SUITE"
    echo "Expected suite cases: $(expected_suite_cases)"
    echo "Languages: ${LANG_ARGS[*]}"
    echo "Metrics: ${METRIC_ARGS[*]}"
    echo "Chat interval seconds: $CHAT_INTERVAL_SECONDS"
    echo "Chat retry attempts: $CHAT_RETRY_ATTEMPTS"
    echo "Chat retry backoff seconds: $CHAT_RETRY_BACKOFF_SECONDS"
    echo "Runner total timeout seconds: $TOTAL_TIMEOUT_SECONDS"
    echo "RAGAS max workers: ${RAGAS_MAX_WORKERS:-1}"
    if [ "$CHECK_TARGETS" = "1" ]; then
      echo "Target check: enabled"
      echo "Live source metadata gate: enabled"
    else
      echo "Target check: disabled"
    fi
    exit 0
  fi

  require_ragas_judge_key

  if [ -z "$API_KEY" ]; then
    API_KEY="$(fetch_api_key_from_gcloud)"
  fi
  if [ -z "$API_KEY" ]; then
    echo "Error: API_SECRET_KEY is required (pass --key, set env, or allow gcloud Secret Manager access)" >&2
    exit 2
  fi

  mkdir -p "$OUTPUT_DIR"
  echo "Running /api/chat live RAGAS"
  echo "Timestamp: $TIMESTAMP"
  echo "Base URL: $BASE_URL"
  echo "Case suite: $CASE_SUITE"
  echo "Expected suite cases: $(expected_suite_cases)"
  echo "Languages: ${LANG_ARGS[*]}"
  echo "Metrics: ${METRIC_ARGS[*]}"
  echo "Chat interval seconds: $CHAT_INTERVAL_SECONDS"
  echo "Chat retry attempts: $CHAT_RETRY_ATTEMPTS"
  echo "Chat retry backoff seconds: $CHAT_RETRY_BACKOFF_SECONDS"
  echo "RAGAS batch strategy: ${RAGAS_BATCH_STRATEGY:-single}"
  echo "RAGAS per-case timeout: ${RAGAS_OUTER_SINGLE_TIMEOUT:-300}s"
  echo "RAGAS max workers: ${RAGAS_MAX_WORKERS:-1}"
  echo "Runner total timeout: ${TOTAL_TIMEOUT_SECONDS}s"

  cmd=(python evaluation/run_live_api_eval.py --base-url "$BASE_URL" --case-suite "$CASE_SUITE" --languages "${LANG_ARGS[@]}" --metrics "${METRIC_ARGS[@]}" --output-dir "$OUTPUT_DIR" --report-timestamp "$TIMESTAMP" --chat-interval-seconds "$CHAT_INTERVAL_SECONDS" --chat-retry-attempts "$CHAT_RETRY_ATTEMPTS" --chat-retry-backoff-seconds "$CHAT_RETRY_BACKOFF_SECONDS")
  if [ "$CHECK_TARGETS" = "1" ]; then
    cmd+=(--check-targets)
  fi
  (
    cd "$ROOT_DIR/backend"
    if command -v uv >/dev/null 2>&1; then
      runner_cmd=(uv run --extra evaluation "${cmd[@]}")
    else
      runner_cmd=("${cmd[@]}")
    fi

    # asyncio.wait_for cannot stop a provider call already running in a worker thread.
    # The outer process timeout keeps C/RAGAS from consuming the entire workflow.
    if [ "$TOTAL_TIMEOUT_SECONDS" != "0" ] && command -v timeout >/dev/null 2>&1; then
      API_SECRET_KEY="$API_KEY" \
        RAGAS_BATCH_STRATEGY="${RAGAS_BATCH_STRATEGY:-single}" \
        RAGAS_OUTER_SINGLE_TIMEOUT="${RAGAS_OUTER_SINGLE_TIMEOUT:-300}" \
        RAGAS_MAX_WORKERS="${RAGAS_MAX_WORKERS:-1}" \
        PYTHONPATH="$ROOT_DIR:$ROOT_DIR/backend:${PYTHONPATH:-}" \
        timeout --kill-after=30s "${TOTAL_TIMEOUT_SECONDS}s" "${runner_cmd[@]}"
    else
      if [ "$TOTAL_TIMEOUT_SECONDS" != "0" ]; then
        echo "Warning: timeout command not found; running without whole-runner timeout" >&2
      fi
      API_SECRET_KEY="$API_KEY" \
        RAGAS_BATCH_STRATEGY="${RAGAS_BATCH_STRATEGY:-single}" \
        RAGAS_OUTER_SINGLE_TIMEOUT="${RAGAS_OUTER_SINGLE_TIMEOUT:-300}" \
        RAGAS_MAX_WORKERS="${RAGAS_MAX_WORKERS:-1}" \
        PYTHONPATH="$ROOT_DIR:$ROOT_DIR/backend:${PYTHONPATH:-}" \
        "${runner_cmd[@]}"
    fi
  )
}

main "$@"
