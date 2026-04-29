#!/usr/bin/env bash
set -euo pipefail

# Alpha final /api/chat live RAGAS wrapper.
#
# Usage:
#   scripts/rag-api-live-test.sh
#   scripts/rag-api-live-test.sh --languages ja,en --dry-run
#
# Env:
#   API_SECRET_KEY                 Required unless --key is provided or gcloud can read it.
#   RAG_API_LIVE_BASE_URL          Overrides default Cloud Run URL.
#   RAG_API_LIVE_SECRET_PROJECT    Overrides Secret Manager project.
#   RAG_API_LIVE_METRICS           Comma-separated RAGAS metrics.
#   OPENAI_API_KEY / OPENROUTER_API_KEY are required by the RAGAS evaluator.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNNER="$ROOT_DIR/backend/evaluation/run_live_api_eval.py"
DEFAULT_URL="https://engineer-cafe-backend-639959525777.asia-northeast1.run.app"
BASE_URL="${RAG_API_LIVE_BASE_URL:-$DEFAULT_URL}"
API_KEY="${API_SECRET_KEY:-}"
SECRET_PROJECT="${RAG_API_LIVE_SECRET_PROJECT:-aipartner-426616}"
SECRET_NAME="API_SECRET_KEY"
OUTPUT_DIR="$ROOT_DIR/backend/tests/evaluation/reports"
LANGUAGES="ja,en,zh,ko"
METRICS="${RAG_API_LIVE_METRICS:-answer_correctness}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
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
  --languages LIST       Comma-separated languages (default: ja,en,zh,ko)
  --metrics LIST         Comma-separated RAGAS metrics (default: answer_correctness)
  --output-dir DIR       Report directory (default: backend/tests/evaluation/reports)
  --timestamp VALUE      Stable timestamp marker printed for operator correlation
  --no-check-targets     Do not fail when configured answer_correctness targets are missed
  --dry-run              Validate local prerequisites and print planned command only
  -h, --help             Show this usage

Outputs:
  backend/tests/evaluation/reports/live_api_ragas_<timestamp>.json
  backend/tests/evaluation/reports/live_api_ragas_<timestamp>.md
EOF
  exit "${1:-0}"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --host) BASE_URL="$2"; shift 2 ;;
    --key) API_KEY="$2"; shift 2 ;;
    --secret-project) SECRET_PROJECT="$2"; shift 2 ;;
    --secret-name) SECRET_NAME="$2"; shift 2 ;;
    --languages) LANGUAGES="$2"; shift 2 ;;
    --metrics) METRICS="$2"; shift 2 ;;
    --output-dir) OUTPUT_DIR="$2"; shift 2 ;;
    --timestamp) TIMESTAMP="$2"; shift 2 ;;
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

require_ragas_judge_key() {
  if [ -n "${OPENAI_API_KEY:-}" ] || [ -n "${OPENROUTER_API_KEY:-}" ]; then
    return
  fi

  echo "Error: C live RAGAS requires OPENAI_API_KEY or OPENROUTER_API_KEY." >&2
  echo "This gate judges live /api/chat answers against the golden dataset; without a judge key the score is not meaningful." >&2
  exit 2
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
    echo "Languages: ${LANG_ARGS[*]}"
    echo "Metrics: ${METRIC_ARGS[*]}"
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
  echo "Languages: ${LANG_ARGS[*]}"
  echo "Metrics: ${METRIC_ARGS[*]}"

  cmd=(python evaluation/run_live_api_eval.py --base-url "$BASE_URL" --languages "${LANG_ARGS[@]}" --metrics "${METRIC_ARGS[@]}" --output-dir "$OUTPUT_DIR")
  if [ "$CHECK_TARGETS" = "1" ]; then
    cmd+=(--check-targets)
  fi
  (
    cd "$ROOT_DIR/backend"
    if command -v uv >/dev/null 2>&1; then
      API_SECRET_KEY="$API_KEY" \
        RAGAS_BATCH_STRATEGY="${RAGAS_BATCH_STRATEGY:-single}" \
        RAGAS_OUTER_SINGLE_TIMEOUT="${RAGAS_OUTER_SINGLE_TIMEOUT:-300}" \
        PYTHONPATH="$ROOT_DIR:$ROOT_DIR/backend:${PYTHONPATH:-}" \
        uv run --extra evaluation "${cmd[@]}"
    else
      API_SECRET_KEY="$API_KEY" \
        RAGAS_BATCH_STRATEGY="${RAGAS_BATCH_STRATEGY:-single}" \
        RAGAS_OUTER_SINGLE_TIMEOUT="${RAGAS_OUTER_SINGLE_TIMEOUT:-300}" \
        PYTHONPATH="$ROOT_DIR:$ROOT_DIR/backend:${PYTHONPATH:-}" \
        "${cmd[@]}"
    fi
  )
}

main "$@"
