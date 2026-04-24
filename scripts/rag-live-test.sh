#!/usr/bin/env bash
set -euo pipefail

# Alpha final live RAGAS wrapper.
#
# Usage:
#   scripts/rag-live-test.sh
#   scripts/rag-live-test.sh --languages ja,en --max-cases 127
#   scripts/rag-live-test.sh --dry-run
#
# Env:
#   OPENAI_API_KEY / OPENROUTER_API_KEY  Required by RAGAS live evaluation.
#   SUPABASE_URL / SUPABASE_KEY          Required by live RAG search.
#   RAGAS_THRESHOLD_JA                   Override ja answer_correctness target.
#   RAGAS_THRESHOLD_EN                   Override en answer_correctness target.
#   RAGAS_THRESHOLD_ZH                   Override zh answer_correctness target.
#   RAGAS_THRESHOLD_KO                   Override ko answer_correctness target.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_OUTPUT_DIR="$ROOT_DIR/backend/tests/evaluation/reports"
RUNNER="$ROOT_DIR/backend/tests/evaluation/run_ragas_evaluation.py"
TARGETS_FILE="$ROOT_DIR/backend/evaluation/datasets/multilingual_queries.json"

MAX_CASES=127
LANGUAGES="ja,en,zh,ko"
OUTPUT_DIR="$DEFAULT_OUTPUT_DIR"
PER_LANGUAGE_TIMEOUT=900
TOTAL_TIMEOUT=3600
DRY_RUN=0
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"

usage() {
  sed -n '3,24p' "$0"
  cat <<'EOF'

Options:
  --max-cases N          Cases per language passed to run_ragas_evaluation.py (default: 127)
  --languages LIST       Comma-separated languages (default: ja,en,zh,ko)
  --output-dir DIR       Report directory (default: backend/tests/evaluation/reports)
  --timeout-seconds N    Timeout per language in seconds (default: 900)
  --total-timeout N      Total wall-clock budget in seconds (default: 3600)
  --timestamp VALUE      Stable timestamp for output names
  --dry-run              Validate local prerequisites and print planned commands only
  -h, --help             Show this usage

Outputs:
  backend/tests/evaluation/reports/ragas-live-<timestamp>.json
  backend/tests/evaluation/reports/ragas-live-<timestamp>.md
EOF
  exit "${1:-0}"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --max-cases) MAX_CASES="$2"; shift 2 ;;
    --languages) LANGUAGES="$2"; shift 2 ;;
    --output-dir) OUTPUT_DIR="$2"; shift 2 ;;
    --timeout-seconds) PER_LANGUAGE_TIMEOUT="$2"; shift 2 ;;
    --total-timeout) TOTAL_TIMEOUT="$2"; shift 2 ;;
    --timestamp) TIMESTAMP="$2"; shift 2 ;;
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

split_languages() {
  python3 - "$LANGUAGES" <<'PY'
import sys
langs = [x.strip() for x in sys.argv[1].split(",") if x.strip()]
for lang in langs:
    print(lang)
PY
}

load_threshold() {
  local lang="$1"
  local env_name
  env_name="RAGAS_THRESHOLD_$(printf '%s' "$lang" | tr '[:lower:]' '[:upper:]')"
  if [ -n "${!env_name:-}" ]; then
    printf '%s\n' "${!env_name}"
    return
  fi
  python3 - "$TARGETS_FILE" "$lang" <<'PY'
import json, sys
path, lang = sys.argv[1], sys.argv[2]
try:
    data = json.load(open(path, encoding="utf-8"))
    print(data.get("targets", {}).get(lang, {}).get("answer_correctness", 0.0))
except Exception:
    print("0.0")
PY
}

latest_report_for_language() {
  local before="$1"
  find "$OUTPUT_DIR" -name 'ragas_report_*.json' -type f -newer "$before" -print 2>/dev/null \
    | sort | tail -n 1
}

write_summary() {
  local combined_json="$1"
  local summary_md="$2"
  python3 - "$combined_json" "$summary_md" <<'PY'
import json, sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
lines = [
    "# RAGAS Live Evaluation Summary",
    "",
    f"- Timestamp: {payload['timestamp']}",
    f"- Mode: live",
    f"- Max cases per language: {payload['max_cases']}",
    f"- Overall passed: {'yes' if payload['passed'] else 'no'}",
    "",
    "| Language | Status | Evaluated | Skipped | answer_correctness | Target | Pass | Report |",
    "| --- | --- | ---: | ---: | ---: | ---: | --- | --- |",
]
for item in payload["languages"]:
    metrics = item.get("metrics") or {}
    actual = metrics.get("answer_correctness")
    actual_s = f"{actual:.4f}" if isinstance(actual, (int, float)) else "n/a"
    target = item.get("target")
    target_s = f"{target:.4f}" if isinstance(target, (int, float)) else "n/a"
    lines.append(
        f"| {item['language']} | {item['status']} | {item.get('evaluated_cases', 0)} | "
        f"{item.get('skipped_cases', 0)} | {actual_s} | {target_s} | "
        f"{'yes' if item.get('passed') else 'no'} | {item.get('report_path') or ''} |"
    )
if payload.get("errors"):
    lines.extend(["", "## Errors", ""])
    for err in payload["errors"]:
        lines.append(f"- {err}")
open(sys.argv[2], "w", encoding="utf-8").write("\n".join(lines) + "\n")
PY
}

require_cmd python3
if [ ! -f "$RUNNER" ]; then
  echo "Error: RAGAS runner not found: $RUNNER" >&2
  exit 2
fi

COMBINED_JSON="$OUTPUT_DIR/ragas-live-$TIMESTAMP.json"
SUMMARY_MD="$OUTPUT_DIR/ragas-live-$TIMESTAMP.md"

LANG_LIST="$(split_languages)"
if [ -z "$LANG_LIST" ]; then
  echo "Error: --languages produced an empty list" >&2
  exit 2
fi

if [ "$DRY_RUN" = "1" ]; then
  echo "Dry run: no live RAGAS commands will be executed."
  echo "Runner: $RUNNER"
  echo "Output: $COMBINED_JSON"
  printf '%s\n' "$LANG_LIST" | while IFS= read -r lang; do
    [ -n "$lang" ] || continue
    echo "Would run: python3 $RUNNER --mode live --max-cases $MAX_CASES --language $lang --output-dir $OUTPUT_DIR (timeout ${PER_LANGUAGE_TIMEOUT}s)"
    echo "Threshold[$lang].answer_correctness=$(load_threshold "$lang")"
  done
  exit 0
fi

mkdir -p "$OUTPUT_DIR"
START_EPOCH="$(date +%s)"
TMP_DIR="$(mktemp -d)"
RESULT_LINES="$TMP_DIR/results.jsonl"
ERROR_LINES="$TMP_DIR/errors.txt"
: > "$RESULT_LINES"
: > "$ERROR_LINES"

printf '%s\n' "$LANG_LIST" | while IFS= read -r lang; do
  [ -n "$lang" ] || continue
  now="$(date +%s)"
  elapsed=$((now - START_EPOCH))
  if [ "$elapsed" -ge "$TOTAL_TIMEOUT" ]; then
    echo "Total timeout exceeded before language=$lang" | tee -a "$ERROR_LINES" >&2
    continue
  fi

  marker="$(mktemp)"
  echo "Running live RAGAS language=$lang max_cases=$MAX_CASES timeout=${PER_LANGUAGE_TIMEOUT}s"
  if python3 - "$PER_LANGUAGE_TIMEOUT" "$RUNNER" "$MAX_CASES" "$lang" "$OUTPUT_DIR" <<'PY'; then
import subprocess, sys
timeout_s, runner, max_cases, lang, output_dir = sys.argv[1:6]
cmd = [
    sys.executable,
    runner,
    "--mode",
    "live",
    "--max-cases",
    max_cases,
    "--language",
    lang,
    "--output-dir",
    output_dir,
]
try:
    raise SystemExit(subprocess.run(cmd, timeout=int(timeout_s)).returncode)
except subprocess.TimeoutExpired:
    print(f"Timed out after {timeout_s}s: {' '.join(cmd)}", file=sys.stderr)
    raise SystemExit(124)
PY
    report_path="$(latest_report_for_language "$marker")"
    rm -f "$marker"
    if [ -z "$report_path" ]; then
      echo "No report found for language=$lang" | tee -a "$ERROR_LINES" >&2
      report_path=""
    fi
    python3 - "$lang" "$(load_threshold "$lang")" "$report_path" >> "$RESULT_LINES" <<'PY'
import json, sys
lang, target, report_path = sys.argv[1], float(sys.argv[2]), sys.argv[3]
payload = {
    "language": lang,
    "status": "missing_report",
    "target": target,
    "passed": False,
    "report_path": report_path,
}
if report_path:
    data = json.load(open(report_path, encoding="utf-8"))
    metrics = data.get("metrics") or {}
    actual = metrics.get("answer_correctness")
    payload.update({
        "status": data.get("status", "unknown"),
        "evaluated_cases": data.get("evaluated_cases", 0),
        "skipped_cases": data.get("skipped_cases", 0),
        "metrics": metrics,
        "errors": data.get("errors", []),
        "passed": isinstance(actual, (int, float)) and actual >= target,
    })
print(json.dumps(payload, ensure_ascii=False))
PY
  else
    status=$?
    rm -f "$marker"
    echo "RAGAS run failed language=$lang status=$status" | tee -a "$ERROR_LINES" >&2
    python3 - "$lang" "$(load_threshold "$lang")" "$status" >> "$RESULT_LINES" <<'PY'
import json, sys
print(json.dumps({
    "language": sys.argv[1],
    "status": "command_failed",
    "target": float(sys.argv[2]),
    "passed": False,
    "exit_status": int(sys.argv[3]),
}, ensure_ascii=False))
PY
  fi
done

python3 - "$TIMESTAMP" "$MAX_CASES" "$RESULT_LINES" "$ERROR_LINES" "$COMBINED_JSON" <<'PY'
import json, sys
timestamp, max_cases, result_lines, error_lines, out = sys.argv[1:6]
items = []
for line in open(result_lines, encoding="utf-8"):
    line = line.strip()
    if line:
        items.append(json.loads(line))
errors = [line.strip() for line in open(error_lines, encoding="utf-8") if line.strip()]
payload = {
    "timestamp": timestamp,
    "mode": "live",
    "max_cases": int(max_cases),
    "passed": bool(items) and all(item.get("passed") for item in items) and not errors,
    "languages": items,
    "errors": errors,
}
open(out, "w", encoding="utf-8").write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
PY

write_summary "$COMBINED_JSON" "$SUMMARY_MD"

echo "JSON report: $COMBINED_JSON"
echo "Markdown summary: $SUMMARY_MD"

python3 - "$COMBINED_JSON" <<'PY'
import json, sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
sys.exit(0 if payload.get("passed") else 1)
PY
