#!/usr/bin/env bash
# Usage: ./scripts/check-db-schema-drift.sh
# Required env: SUPABASE_ACCESS_TOKEN, SUPABASE_PROJECT_ID, SUPABASE_DB_PASSWORD
# Exit 0: no drift / Exit 1: drift detected / Exit 2: missing config or tooling failure

set -euo pipefail

required_env=(
  "SUPABASE_ACCESS_TOKEN"
  "SUPABASE_PROJECT_ID"
  "SUPABASE_DB_PASSWORD"
)

missing_env=()
for name in "${required_env[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    missing_env+=("${name}")
  fi
done

if (( ${#missing_env[@]} > 0 )); then
  printf 'Missing required environment variables: %s\n' "${missing_env[*]}" >&2
  exit 2
fi

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

diff_output_file="$(mktemp)"
trap 'rm -f "${diff_output_file}"' EXIT

(
  cd "${supabase_dir}"
  supabase link \
    --project-ref "${SUPABASE_PROJECT_ID}" \
    --password "${SUPABASE_DB_PASSWORD}" >/dev/null

  supabase db diff --linked --schema public > "${diff_output_file}"
) || {
  cat "${diff_output_file}" >&2 || true
  printf 'Supabase schema drift check failed before a reliable drift verdict was produced.\n' >&2
  exit 2
}

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
