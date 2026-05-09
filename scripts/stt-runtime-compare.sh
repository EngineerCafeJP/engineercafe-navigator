#!/usr/bin/env bash
set -euo pipefail

# Compare two STT runtime log sets, typically PyTorch Qwen CPU vs ONNX Qwen CPU.
#
# Local JSON mode does not require live credentials:
#   scripts/stt-runtime-compare.sh \
#     --baseline-json pytorch-logs.json --candidate-json onnx-logs.json
#
# Cloud Logging mode compares two Cloud Run revisions:
#   scripts/stt-runtime-compare.sh \
#     --since 2026-05-09T00:00:00Z \
#     --baseline-revision engineer-cafe-backend-00100-pytorch \
#     --candidate-revision engineer-cafe-backend-00101-onnx

PROJECT_ID="${STT_RUNTIME_COMPARE_PROJECT:-aipartner-426616}"
SERVICE_NAME="${STT_RUNTIME_COMPARE_SERVICE:-engineer-cafe-backend}"
REGION="${STT_RUNTIME_COMPARE_REGION:-asia-northeast1}"
ENV_LABEL="${STT_RUNTIME_COMPARE_ENV_LABEL:-prod}"
BASELINE_LABEL="${STT_RUNTIME_COMPARE_BASELINE_LABEL:-pytorch-qwen-cpu}"
CANDIDATE_LABEL="${STT_RUNTIME_COMPARE_CANDIDATE_LABEL:-onnx-qwen-cpu}"
BASELINE_REVISION=""
CANDIDATE_REVISION=""
BASELINE_JSON=""
CANDIDATE_JSON=""
SINCE=""
UNTIL=""
LIMIT=1000
OUTPUT=""
DRY_RUN=0

usage() {
  sed -n '3,15p' "$0"
  cat <<'EOF'

Options:
  --baseline-json PATH       Saved gcloud logging JSON for the baseline runtime
  --candidate-json PATH      Saved gcloud logging JSON for the candidate runtime
  --baseline-label LABEL     Baseline label (default: pytorch-qwen-cpu)
  --candidate-label LABEL    Candidate label (default: onnx-qwen-cpu)
  --env-label LABEL          Environment/report label (default: prod)
  --since RFC3339            Required for Cloud Logging mode
  --until RFC3339            Optional end timestamp for Cloud Logging mode
  --baseline-revision NAME   Cloud Run revision for baseline logs
  --candidate-revision NAME  Cloud Run revision for candidate logs
  --project ID               GCP project (default: aipartner-426616)
  --service NAME             Cloud Run service (default: engineer-cafe-backend)
  --region REGION            Cloud Run region (default: asia-northeast1)
  --limit N                  Max log rows per runtime (default: 1000)
  --output PATH              Optional markdown report path
  --dry-run                  Print selected inputs/filters without reading logs
  -h, --help                 Show this usage

Outputs explicit comparison fields for request_total, qwen_runtime,
qwen_model_inference, winner, and hedge/grace timing.
EOF
  exit "${1:-0}"
}

die() {
  echo "Error: $*" >&2
  exit 2
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    die "required command not found: $1"
  fi
}

is_positive_int() {
  [[ "${1:-}" =~ ^[1-9][0-9]*$ ]]
}

validate_filter_value() {
  local name="$1"
  local value="$2"
  if [[ "$value" == *'"'* || "$value" == *$'\n'* || "$value" == *$'\r'* ]]; then
    die "$name must not contain quotes or newlines"
  fi
}

normalize_timestamp() {
  python3 - "$1" <<'PY'
from __future__ import annotations

from datetime import datetime, timezone
import re
import sys

raw = sys.argv[1].strip()
if not raw or '"' in raw or "\n" in raw or "\r" in raw:
    raise SystemExit(2)

value = re.sub(r"\s+JST$", "+09:00", raw, flags=re.IGNORECASE)
value = value.replace(" ", "T")
if value.endswith("Z"):
    value = value[:-1] + "+00:00"

try:
    parsed = datetime.fromisoformat(value)
except ValueError as exc:
    raise SystemExit(f"invalid timestamp {raw!r}: {exc}")

if parsed.tzinfo is None:
    raise SystemExit(f"timestamp must include timezone, Z, offset, or JST suffix: {raw!r}")

print(parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"))
PY
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --baseline-json) [ "$#" -ge 2 ] || die "--baseline-json requires a value"; BASELINE_JSON="$2"; shift 2 ;;
    --candidate-json) [ "$#" -ge 2 ] || die "--candidate-json requires a value"; CANDIDATE_JSON="$2"; shift 2 ;;
    --baseline-label) [ "$#" -ge 2 ] || die "--baseline-label requires a value"; BASELINE_LABEL="$2"; shift 2 ;;
    --candidate-label) [ "$#" -ge 2 ] || die "--candidate-label requires a value"; CANDIDATE_LABEL="$2"; shift 2 ;;
    --env-label) [ "$#" -ge 2 ] || die "--env-label requires a value"; ENV_LABEL="$2"; shift 2 ;;
    --since) [ "$#" -ge 2 ] || die "--since requires a value"; SINCE="$2"; shift 2 ;;
    --until) [ "$#" -ge 2 ] || die "--until requires a value"; UNTIL="$2"; shift 2 ;;
    --baseline-revision) [ "$#" -ge 2 ] || die "--baseline-revision requires a value"; BASELINE_REVISION="$2"; shift 2 ;;
    --candidate-revision) [ "$#" -ge 2 ] || die "--candidate-revision requires a value"; CANDIDATE_REVISION="$2"; shift 2 ;;
    --project) [ "$#" -ge 2 ] || die "--project requires a value"; PROJECT_ID="$2"; shift 2 ;;
    --service) [ "$#" -ge 2 ] || die "--service requires a value"; SERVICE_NAME="$2"; shift 2 ;;
    --region) [ "$#" -ge 2 ] || die "--region requires a value"; REGION="$2"; shift 2 ;;
    --limit) [ "$#" -ge 2 ] || die "--limit requires a value"; LIMIT="$2"; shift 2 ;;
    --output) [ "$#" -ge 2 ] || die "--output requires a value"; OUTPUT="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage 0 ;;
    *) echo "Unknown arg: $1" >&2; usage 1 ;;
  esac
done

[[ -n "$PROJECT_ID" ]] || die "project must not be empty"
[[ -n "$SERVICE_NAME" ]] || die "service must not be empty"
[[ -n "$REGION" ]] || die "region must not be empty"
[[ -n "$ENV_LABEL" ]] || die "env label must not be empty"
[[ -n "$BASELINE_LABEL" ]] || die "baseline label must not be empty"
[[ -n "$CANDIDATE_LABEL" ]] || die "candidate label must not be empty"
is_positive_int "$LIMIT" || die "--limit must be a positive integer"
require_cmd python3
validate_filter_value "--baseline-revision" "$BASELINE_REVISION"
validate_filter_value "--candidate-revision" "$CANDIDATE_REVISION"

LOCAL_JSON_MODE=0
if [ -n "$BASELINE_JSON" ] || [ -n "$CANDIDATE_JSON" ]; then
  [ -n "$BASELINE_JSON" ] || die "--baseline-json is required when --candidate-json is set"
  [ -n "$CANDIDATE_JSON" ] || die "--candidate-json is required when --baseline-json is set"
  if [ "$DRY_RUN" = "0" ]; then
    [ -f "$BASELINE_JSON" ] || die "baseline JSON not found: $BASELINE_JSON"
    [ -f "$CANDIDATE_JSON" ] || die "candidate JSON not found: $CANDIDATE_JSON"
  fi
  LOCAL_JSON_MODE=1
fi

SINCE_UTC=""
UNTIL_UTC=""
if [ "$LOCAL_JSON_MODE" = "0" ]; then
  [[ -n "$SINCE" ]] || die "--since is required in Cloud Logging mode"
  [[ -n "$BASELINE_REVISION" ]] || die "--baseline-revision is required in Cloud Logging mode"
  [[ -n "$CANDIDATE_REVISION" ]] || die "--candidate-revision is required in Cloud Logging mode"
  SINCE_UTC="$(normalize_timestamp "$SINCE")"
  if [ -n "$UNTIL" ]; then
    UNTIL_UTC="$(normalize_timestamp "$UNTIL")"
  fi
fi

build_filter() {
  local revision="$1"
  local filter='resource.type="cloud_run_revision"'
  filter="$filter AND resource.labels.service_name=\"$SERVICE_NAME\""
  filter="$filter AND resource.labels.location=\"$REGION\""
  filter="$filter AND resource.labels.revision_name=\"$revision\""
  filter="$filter AND timestamp >= \"$SINCE_UTC\""
  if [ -n "$UNTIL_UTC" ]; then
    filter="$filter AND timestamp <= \"$UNTIL_UTC\""
  fi
  filter="$filter AND jsonPayload.event=~\"stt_.*\""
  printf '%s\n' "$filter"
}

BASELINE_FILTER=""
CANDIDATE_FILTER=""
if [ "$LOCAL_JSON_MODE" = "0" ]; then
  BASELINE_FILTER="$(build_filter "$BASELINE_REVISION")"
  CANDIDATE_FILTER="$(build_filter "$CANDIDATE_REVISION")"
fi

if [ "$DRY_RUN" = "1" ]; then
  echo "Dry run: no gcloud logging read calls will be executed."
  echo "Environment label: $ENV_LABEL"
  echo "Baseline label: $BASELINE_LABEL"
  echo "Candidate label: $CANDIDATE_LABEL"
  if [ "$LOCAL_JSON_MODE" = "1" ]; then
    echo "Mode: local JSON"
    echo "Baseline JSON: $BASELINE_JSON"
    echo "Candidate JSON: $CANDIDATE_JSON"
  else
    echo "Mode: Cloud Logging"
    echo "Project: $PROJECT_ID"
    echo "Service: $SERVICE_NAME"
    echo "Region: $REGION"
    echo "Baseline revision: $BASELINE_REVISION"
    echo "Candidate revision: $CANDIDATE_REVISION"
    echo "Since UTC: $SINCE_UTC"
    echo "Until UTC: ${UNTIL_UTC:-none}"
    echo "Limit: $LIMIT"
    echo "Baseline filter: $BASELINE_FILTER"
    echo "Candidate filter: $CANDIDATE_FILTER"
  fi
  echo "Output: ${OUTPUT:-stdout}"
  exit 0
fi

TMP_FILES=()
cleanup() {
  if [ "${#TMP_FILES[@]}" -gt 0 ]; then
    rm -f "${TMP_FILES[@]}"
  fi
}
trap cleanup EXIT

if [ "$LOCAL_JSON_MODE" = "0" ]; then
  require_cmd gcloud
  BASELINE_JSON="$(mktemp)"
  CANDIDATE_JSON="$(mktemp)"
  TMP_FILES+=("$BASELINE_JSON" "$CANDIDATE_JSON")

  gcloud logging read "$BASELINE_FILTER" \
    --project "$PROJECT_ID" \
    --limit "$LIMIT" \
    --format=json > "$BASELINE_JSON"

  gcloud logging read "$CANDIDATE_FILTER" \
    --project "$PROJECT_ID" \
    --limit "$LIMIT" \
    --format=json > "$CANDIDATE_JSON"
fi

REPORT_TMP="$(mktemp)"
TMP_FILES+=("$REPORT_TMP")

python3 - "$BASELINE_JSON" "$CANDIDATE_JSON" "$ENV_LABEL" "$BASELINE_LABEL" "$CANDIDATE_LABEL" "$BASELINE_REVISION" "$CANDIDATE_REVISION" "$LIMIT" <<'PY' > "$REPORT_TMP"
from __future__ import annotations

from collections import Counter
import json
import math
import sys
from pathlib import Path
from typing import Any

(
    baseline_json,
    candidate_json,
    env_label,
    baseline_label,
    candidate_label,
    baseline_revision,
    candidate_revision,
    limit_raw,
) = sys.argv[1:9]
limit = int(limit_raw)


def percentile(values: list[float], ratio: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * ratio
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def append_float(values: list[float], value: Any) -> None:
    try:
        values.append(float(value))
    except (TypeError, ValueError):
        pass


def truthy(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"1", "true", "yes", "on"}


def fmt_ms(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.0f}"


def fmt_delta(value: float | None) -> str:
    if value is None:
        return "n/a"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.0f}"


def load_entries(path: str) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8") or "[]")
    return data if isinstance(data, list) else []


def summarize(path: str, label: str, revision_hint: str) -> dict[str, Any]:
    entries = load_entries(path)
    events: list[dict[str, Any]] = []
    revisions: Counter[str] = Counter()
    for entry in entries:
        payload = entry.get("jsonPayload")
        if not isinstance(payload, dict):
            continue
        event = payload.get("event")
        if not isinstance(event, str) or not event.startswith("stt_"):
            continue
        labels = (entry.get("resource") or {}).get("labels") or {}
        revision = labels.get("revision_name") or revision_hint or "unknown"
        revisions[str(revision)] += 1
        event_row = dict(payload)
        event_row["revision_name"] = revision
        events.append(event_row)

    winners: Counter[str] = Counter()
    event_counts: Counter[str] = Counter()
    qwen_model_names: Counter[str] = Counter()
    qwen_model_variants: Counter[str] = Counter()
    qwen_devices: Counter[str] = Counter()
    request_total: list[float] = []
    stt_overall: list[float] = []
    qwen_runtime: list[float] = []
    qwen_model_inference: list[float] = []
    hedge_wait: list[float] = []
    qwen_grace_wait_from_winner: list[float] = []
    qwen_grace_wait_from_complete: list[float] = []
    qwen_postprocess_signals: Counter[str] = Counter()

    for payload in events:
        event = payload.get("event")
        event_counts[str(event)] += 1
        if event == "stt_request_complete":
            append_float(request_total, payload.get("stt_request_duration_ms"))
        elif event == "stt_qwen_runtime_complete":
            append_float(qwen_runtime, payload.get("stt_qwen_runtime_duration_ms"))
            append_float(qwen_model_inference, payload.get("stt_qwen_model_inference_duration_ms"))
            if payload.get("model_name"):
                qwen_model_names[str(payload.get("model_name"))] += 1
            if payload.get("model_variant"):
                qwen_model_variants[str(payload.get("model_variant"))] += 1
            if payload.get("device"):
                qwen_devices[str(payload.get("device"))] += 1
        elif event == "stt_qwen_postprocess_complete":
            qwen_postprocess_signals["complete"] += 1
            if truthy(payload.get("changed")):
                qwen_postprocess_signals["changed"] += 1
            if truthy(payload.get("deterministic_changed")):
                qwen_postprocess_signals["deterministic_changed"] += 1
            if truthy(payload.get("llm_changed")):
                qwen_postprocess_signals["llm_changed"] += 1
        elif event == "stt_qwen_hedge_start":
            append_float(hedge_wait, payload.get("stt_hedge_wait_duration_ms"))
        elif event == "stt_qwen_hedge_grace_complete":
            append_float(
                qwen_grace_wait_from_complete,
                payload.get("stt_qwen_grace_wait_duration_ms"),
            )
        elif event == "stt_winner":
            winner = payload.get("stt_winner") or payload.get("provider") or "unknown"
            winners[str(winner)] += 1
            append_float(stt_overall, payload.get("stt_overall_duration_ms"))
            append_float(qwen_grace_wait_from_winner, payload.get("stt_qwen_grace_wait_duration_ms"))

    def metric(values: list[float]) -> dict[str, float | int | None]:
        return {
            "count": len(values),
            "p50": percentile(values, 0.50),
            "p90": percentile(values, 0.90),
            "p95": percentile(values, 0.95),
            "max": max(values) if values else None,
        }

    return {
        "label": label,
        "rows": len(entries),
        "events": len(events),
        "revisions": revisions,
        "event_counts": event_counts,
        "winners": winners,
        "qwen_model_names": qwen_model_names,
        "qwen_model_variants": qwen_model_variants,
        "qwen_devices": qwen_devices,
        "qwen_postprocess_signals": qwen_postprocess_signals,
        "request_total": metric(request_total),
        "stt_overall": metric(stt_overall),
        "qwen_runtime": metric(qwen_runtime),
        "qwen_model_inference": metric(qwen_model_inference),
        "hedge_wait": metric(hedge_wait),
        "qwen_grace_wait": metric(
            qwen_grace_wait_from_winner or qwen_grace_wait_from_complete
        ),
    }


baseline = summarize(baseline_json, baseline_label, baseline_revision)
candidate = summarize(candidate_json, candidate_label, candidate_revision)


def winner_for(metric_name: str, stat_name: str) -> str:
    base = baseline[metric_name][stat_name]
    cand = candidate[metric_name][stat_name]
    if base is None and cand is None:
        return "n/a"
    if base is None:
        return candidate_label
    if cand is None:
        return baseline_label
    if cand < base:
        return candidate_label
    if base < cand:
        return baseline_label
    return "tie"


def row(metric_name: str, stat_name: str, label: str) -> str:
    base = baseline[metric_name][stat_name]
    cand = candidate[metric_name][stat_name]
    delta = None if base is None or cand is None else cand - base
    return (
        f"| {label} | {fmt_ms(base)} | {fmt_ms(cand)} | "
        f"{fmt_delta(delta)} | {winner_for(metric_name, stat_name)} |"
    )


print("# STT Runtime Compare")
print()
print(f"- Environment label: `{env_label}`")
print(f"- Baseline: `{baseline_label}`")
print(f"- Candidate: `{candidate_label}`")
print(f"- Baseline revision(s): `{dict(baseline['revisions']) or baseline_revision or 'n/a'}`")
print(f"- Candidate revision(s): `{dict(candidate['revisions']) or candidate_revision or 'n/a'}`")
print(f"- Baseline rows/events: `{baseline['rows']}` / `{baseline['events']}`")
print(f"- Candidate rows/events: `{candidate['rows']}` / `{candidate['events']}`")
if baseline["rows"] >= limit or candidate["rows"] >= limit:
    print(f"- Limit warning: at least one log set hit `{limit}` rows; rerun with a larger --limit if needed.")
print()
print("## Explicit Fields")
print()
print("| Output field | Source log field |")
print("| --- | --- |")
print("| request_total | `stt_request_duration_ms` on `stt_request_complete` |")
print("| qwen_runtime | `stt_qwen_runtime_duration_ms` on `stt_qwen_runtime_complete` |")
print("| qwen_model_inference | `stt_qwen_model_inference_duration_ms` on `stt_qwen_runtime_complete` |")
print("| qwen_postprocess_changed | `changed` / `deterministic_changed` on `stt_qwen_postprocess_complete` |")
print("| winner | `stt_winner` on `stt_winner` |")
print("| hedge_wait | `stt_hedge_wait_duration_ms` on `stt_qwen_hedge_start` |")
print("| qwen_grace_wait | `stt_qwen_grace_wait_duration_ms` on winner/grace events |")
print()
print("## Latency")
print()
print("| Metric | Baseline ms | Candidate ms | Candidate delta ms | Lower latency winner |")
print("| --- | ---: | ---: | ---: | --- |")
for metric_name, stat_name, label in (
    ("request_total", "p50", "request_total p50"),
    ("request_total", "p90", "request_total p90"),
    ("stt_overall", "p50", "stt_overall p50"),
    ("stt_overall", "p90", "stt_overall p90"),
    ("qwen_runtime", "p50", "qwen_runtime p50"),
    ("qwen_runtime", "p90", "qwen_runtime p90"),
    ("qwen_model_inference", "p50", "qwen_model_inference p50"),
    ("qwen_model_inference", "p90", "qwen_model_inference p90"),
    ("hedge_wait", "p50", "hedge_wait p50"),
    ("qwen_grace_wait", "p50", "qwen_grace_wait p50"),
):
    print(row(metric_name, stat_name, label))
print()
print("## Winner Counts")
print()
print("| winner | Baseline count | Candidate count |")
print("| --- | ---: | ---: |")
for winner in sorted(set(baseline["winners"]) | set(candidate["winners"]) | {"qwen", "vosk", "none"}):
    print(f"| {winner} | {baseline['winners'].get(winner, 0)} | {candidate['winners'].get(winner, 0)} |")
print()
print("## Transcript Quality Signals")
print()
print("| Signal | Baseline count | Candidate count |")
print("| --- | ---: | ---: |")
for signal in ("complete", "changed", "deterministic_changed", "llm_changed"):
    print(
        f"| qwen_postprocess_{signal} | "
        f"{baseline['qwen_postprocess_signals'].get(signal, 0)} | "
        f"{candidate['qwen_postprocess_signals'].get(signal, 0)} |"
    )
print()
print("## Hedge And Grace Counts")
print()
print("| Event | Baseline count | Candidate count |")
print("| --- | ---: | ---: |")
for event in (
    "stt_qwen_hedge_start",
    "stt_qwen_hedge_grace_start",
    "stt_qwen_hedge_grace_complete",
    "stt_qwen_hedge_grace_skipped",
    "stt_qwen_rejected",
):
    print(
        f"| {event} | {baseline['event_counts'].get(event, 0)} | "
        f"{candidate['event_counts'].get(event, 0)} |"
    )
print()
print("## Qwen Runtime Metadata")
print()
print("| Metadata | Baseline | Candidate |")
print("| --- | --- | --- |")
for label, key in (
    ("model_name", "qwen_model_names"),
    ("model_variant", "qwen_model_variants"),
    ("device", "qwen_devices"),
):
    print(f"| {label} | `{dict(baseline[key]) or 'n/a'}` | `{dict(candidate[key]) or 'n/a'}` |")
PY

if [ -n "$OUTPUT" ]; then
  mkdir -p "$(dirname "$OUTPUT")"
  cp "$REPORT_TMP" "$OUTPUT"
  echo "Wrote $OUTPUT"
else
  cat "$REPORT_TMP"
fi
