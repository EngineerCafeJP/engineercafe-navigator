#!/usr/bin/env bash
# Usage: ./scripts/check-db-schema-drift.sh
#
# Preferred env:
#   SUPABASE_DB_URI or SUPABASE_DB_URL
#
# Legacy env, kept for existing local/operator workflows:
#   SUPABASE_ACCESS_TOKEN, SUPABASE_PROJECT_ID, SUPABASE_DB_PASSWORD
#
# Exit 0: no drift
# Exit 1: drift detected
# Exit 2: missing config or tooling failure

set -euo pipefail

if ! command -v supabase >/dev/null 2>&1; then
  printf 'Supabase CLI is required. Install it before running this check.\n' >&2
  exit 2
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
supabase_dir="${repo_root}/backend/supabase"

if [[ ! -f "${supabase_dir}/config.toml" ]]; then
  printf 'Supabase config not found at %s\n' "${supabase_dir}/config.toml" >&2
  exit 2
fi

normalize_db_url() {
  python3 - "$1" <<'PY'
import sys
from urllib.parse import quote, urlsplit, urlunsplit

raw = sys.argv[1]
parts = urlsplit(raw)
if not parts.scheme or not parts.hostname:
    raise SystemExit("invalid database URL")

username = quote(parts.username or "", safe="%")
password = quote(parts.password or "", safe="%")
auth = username
if password:
    auth = f"{auth}:{password}" if auth else f":{password}"

host = parts.hostname
if ":" in host and not host.startswith("["):
    host = f"[{host}]"
if parts.port:
    host = f"{host}:{parts.port}"

netloc = f"{auth}@{host}" if auth else host
print(urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment)))
PY
}

run_supabase() {
  if command -v timeout >/dev/null 2>&1; then
    timeout "${SUPABASE_DIFF_TIMEOUT_SECONDS:-540}" supabase "$@"
  else
    supabase "$@"
  fi
}

mask_secret() {
  if [[ "${GITHUB_ACTIONS:-}" == "true" && -n "${1:-}" ]]; then
    printf '::add-mask::%s\n' "$1"
  fi
}

redact_stderr_file() {
  python3 - "$@" <<'PY'
import sys

path = sys.argv[1]
secrets = [value for value in sys.argv[2:] if value]
with open(path, encoding="utf-8", errors="replace") as f:
    text = f.read()
for secret in secrets:
    text = text.replace(secret, "<redacted>")
sys.stderr.write(text)
PY
}

db_url="${SUPABASE_DB_URI:-${SUPABASE_DB_URL:-}}"
legacy_env_ready=false
if [[ -n "${SUPABASE_ACCESS_TOKEN:-}" && -n "${SUPABASE_PROJECT_ID:-}" && -n "${SUPABASE_DB_PASSWORD:-}" ]]; then
  legacy_env_ready=true
fi

if [[ -z "${db_url}" && "${legacy_env_ready}" != "true" ]]; then
  printf 'Missing Supabase drift credentials. Set SUPABASE_DB_URI (preferred) or all of: SUPABASE_ACCESS_TOKEN SUPABASE_PROJECT_ID SUPABASE_DB_PASSWORD\n' >&2
  exit 2
fi

diff_output_file="$(mktemp)"
diff_error_file="$(mktemp)"
trap 'rm -f "${diff_output_file}" "${diff_error_file}"' EXIT

original_pwd="${PWD}"
diff_status=0
normalized_db_url=""

cd "${supabase_dir}"
if [[ -n "${db_url}" ]]; then
  normalized_db_url="$(normalize_db_url "${db_url}")"
  mask_secret "${db_url}"
  mask_secret "${normalized_db_url}"
  set +e
  run_supabase db diff --from migrations --to "${normalized_db_url}" --schema public >"${diff_output_file}" 2>"${diff_error_file}"
  diff_status=$?
  set -e
else
  mask_secret "${SUPABASE_DB_PASSWORD}"
  set +e
  run_supabase link \
    --project-ref "${SUPABASE_PROJECT_ID}" \
    --password "${SUPABASE_DB_PASSWORD}" >/dev/null 2>"${diff_error_file}"
  diff_status=$?
  if [[ "${diff_status}" -eq 0 ]]; then
    run_supabase db diff --linked --schema public >"${diff_output_file}" 2>>"${diff_error_file}"
    diff_status=$?
  fi
  set -e
fi
cd "${original_pwd}"

if [[ -s "${diff_error_file}" ]]; then
  redact_stderr_file "${diff_error_file}" "${db_url}" "${normalized_db_url}" "${SUPABASE_DB_PASSWORD:-}"
fi

if [[ "${diff_status}" -ne 0 ]]; then
  cat "${diff_output_file}" >&2 || true
  printf 'Supabase schema drift check failed before a reliable drift verdict was produced.\n' >&2
  exit 2
fi

cat "${diff_output_file}"

if grep -Eq 'No schema changes found' "${diff_output_file}"; then
  printf 'No Supabase schema drift detected.\n'
  exit 0
fi

if [[ ! -s "${diff_output_file}" ]]; then
  printf 'No Supabase schema drift detected.\n'
  exit 0
fi

printf 'Supabase schema drift detected. Capture this diff in a reviewed migration before deploy.\n' >&2
exit 1
