#!/usr/bin/env bash
# H5 — Admission fee for block-capable guards / completion verifiers (required check).
# Spec: aidd-governance design/harness-spec.md H5, design/ops/harness/h5-negative-test-gate.md
#
# Exit 0: not a guard PR, or 3-point set present
# Exit 1: guard PR missing negative-test evidence / ledger wiring / retirement condition
# Exit 0 with warn: fail-open structural smell (does not block)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BASE_REF="${H5_BASE_REF:-origin/develop}"
HEAD_REF="${H5_HEAD_REF:-HEAD}"
PR_BODY="${H5_PR_BODY:-}"
EVENT_NAME="${GITHUB_EVENT_NAME:-}"
LEDGER_PATH="${H5_LEDGER_PATH:-$HOME/.claude/hooks/ledger/guard-ledger.jsonl}"

log() { printf '%s\n' "$*"; }
warn() { printf 'H5-WARN: %s\n' "$*" >&2; }
fail() { printf 'H5-FAIL: %s\n' "$*" >&2; }

# --- Collect PR body (CI or local override) ---
if [[ -z "$PR_BODY" && -n "${GITHUB_EVENT_PATH:-}" && -f "${GITHUB_EVENT_PATH}" ]]; then
  PR_BODY="$(python3 - <<'PY' 2>/dev/null || true
import json, os
path = os.environ["GITHUB_EVENT_PATH"]
with open(path) as f:
    ev = json.load(f)
body = (ev.get("pull_request") or {}).get("body") or ""
print(body)
PY
)"
fi
if [[ -z "$PR_BODY" && -n "${H5_PR_NUMBER:-}" ]]; then
  PR_BODY="$(gh pr view "$H5_PR_NUMBER" --json body -q .body 2>/dev/null || true)"
fi

# --- Diff paths ---
if [[ -n "${H5_DIFF_FILES:-}" ]]; then
  # newline or space separated override (tests)
  DIFF_FILES="$(printf '%s\n' $H5_DIFF_FILES)"
else
  git fetch --no-tags --depth=1 origin "$(echo "$BASE_REF" | sed 's#^origin/##')" 2>/dev/null || true
  if git rev-parse --verify "$BASE_REF" >/dev/null 2>&1; then
    DIFF_FILES="$(git diff --name-only "$BASE_REF"...$HEAD_REF 2>/dev/null || git diff --name-only "$BASE_REF" $HEAD_REF 2>/dev/null || true)"
  else
    DIFF_FILES="$(git diff --name-only HEAD~1...HEAD 2>/dev/null || true)"
  fi
fi

is_guard_pr=0
# Structural triggers: any path that can change guard force projection.
# Keep this set and the H5-guard:no exemption-denylist (below) IDENTICAL.
# Phase 5 T5-2: must cover hooks/lib/** and scripts/** (.+\.sh), not only hooks/[^/]+\.sh
# Checklist S9 expects this form (hooks/.+\.sh includes hooks/lib/*.sh).
_H5_STRUCT_RE='^(hooks/.+\.sh|scripts/.+\.sh|settings\.json|\.github/workflows/)'
if printf '%s\n' "$DIFF_FILES" | grep -qE "$_H5_STRUCT_RE"; then
  is_guard_pr=1
fi
# Self-declaration (PR template)
if printf '%s' "$PR_BODY" | grep -qiE 'H5-guard:\s*yes|ブロック権限|完了判定検証器|block-capable guard'; then
  is_guard_pr=1
fi
# H5-guard: no may only clear the flag when NO structural path is touched.
# Previously the denylist was a subset (hooks/*.sh|hooks/lib|settings) so
# scripts/** and .github/workflows/** could self-exempt — that hole is closed.
if printf '%s' "$PR_BODY" | grep -qiE 'H5-guard:\s*no' \
  && ! printf '%s' "$PR_BODY" | grep -qiE 'H5-guard:\s*yes'; then
  if ! printf '%s\n' "$DIFF_FILES" | grep -qE "$_H5_STRUCT_RE"; then
    is_guard_pr=0
  fi
fi

if [[ "$is_guard_pr" -eq 0 ]]; then
  log "H5-PASS: not a guard/verifier PR (no structural trigger / declared N/A)"
  exit 0
fi

log "H5: guard/verifier PR detected — checking 3-point admission fee"

# Ignore negation/meta lines so "missing 陰性テスト" does not count as evidence
PR_BODY_EVIDENCE="$(printf '%s\n' "$PR_BODY" | grep -viE \
  'intentionally missing|expect red|do not merge|falsification only|未記入|TODO 陰性|TODO 台帳|TODO 廃止' || true)"

missing=()

# Prefer explicit machine markers (H5-NEGATIVE: / H5-LEDGER: / H5-RETIRE:)
# Fall back to Japanese/English section content of sufficient length.
has_marker() {
  local key="$1"
  printf '%s' "$PR_BODY_EVIDENCE" | grep -qiE "(^|[[:space:]])H5-${key}:[[:space:]]*\\S.{8,}"
}

has_section_content() {
  local title_re="$1"
  H5_SECTION_BODY="$PR_BODY_EVIDENCE" python3 -c "
import re, os, sys
title = sys.argv[1]
body = os.environ.get('H5_SECTION_BODY', '')
pat = re.compile(rf'(?im)^#{{1,3}}\\s*(?:{title})\\s*\$([\\s\\S]*?)(?=^#{{1,3}}\\s|\\Z)')
m = pat.search(body)
if not m:
    sys.exit(1)
content = m.group(1).strip()
if len(content) < 20:
    sys.exit(1)
if re.fullmatch(r'[-*\\[\\] xX\\s]*', content):
    sys.exit(1)
sys.exit(0)
" "$title_re" 2>/dev/null
}

# (1) Negative test evidence (known-bad → red measured)
neg_ok=0
has_marker "NEGATIVE" && neg_ok=1
has_section_content '陰性テスト|negative[[:space:]-]?test' && neg_ok=1
if [[ "$neg_ok" -eq 0 ]]; then
  if printf '%s' "$PR_BODY_EVIDENCE" | grep -qiE '(陰性テスト|negative[[:space:]-]?test)' \
    && printf '%s' "$PR_BODY_EVIDENCE" | grep -qiE '(red 実測|exit[[:space:]]*[12]|FAILED|known-bad|inject)'; then
    neg_ok=1
  fi
fi
[[ "$neg_ok" -eq 0 ]] && missing+=("negative-test-evidence")

# (2) H6 ledger wiring — body marker/section or changed hook sources
has_ledger_body=0
has_marker "LEDGER" && has_ledger_body=1
has_section_content '台帳|ledger|防御台帳' && has_ledger_body=1
printf '%s' "$PR_BODY_EVIDENCE" | grep -qiE 'aidd_ledger_append|guard-ledger\.jsonl' && has_ledger_body=1
has_ledger_code=0
while IFS= read -r f; do
  [[ -z "$f" || ! -f "$f" ]] && continue
  if grep -qE 'aidd_ledger_append|guard-ledger\.jsonl|aidd-ledger' "$f" 2>/dev/null; then
    has_ledger_code=1
    break
  fi
done <<<"$(printf '%s\n' "$DIFF_FILES" | grep -E '^hooks/|^scripts/h5' || true)"
if [[ "$has_ledger_body" -eq 0 && "$has_ledger_code" -eq 0 ]]; then
  if printf '%s\n' "$DIFF_FILES" | grep -q 'h5-admission' && printf '%s' "$PR_BODY_EVIDENCE" | grep -qiE '台帳|ledger'; then
    has_ledger_body=1
  fi
fi
if [[ "$has_ledger_body" -eq 0 && "$has_ledger_code" -eq 0 ]]; then
  missing+=("ledger-wiring")
fi

# (3) Retirement condition declared
ret_ok=0
has_marker "RETIRE" && ret_ok=1
has_section_content '廃止条件|retirement' && ret_ok=1
if printf '%s' "$PR_BODY_EVIDENCE" | grep -qiE '(廃止条件|retirement).{0,80}(90|発火ゼロ|FP|false.?positive|退役)'; then
  ret_ok=1
fi
[[ "$ret_ok" -eq 0 ]] && missing+=("retirement-condition")

# ADR-002 subtraction gate: require retire PR MERGED (state, not string-only) OR explicit N/A
sub_ok=0
if printf '%s' "$PR_BODY_EVIDENCE" | grep -qiE 'H5-SUBTRACTION:\s*N/?A'; then
  sub_ok=1
fi
retire_pr="$(printf '%s' "$PR_BODY" | grep -oiE 'H5-RETIRE-PR:[[:space:]]*[0-9]+' | head -1 | grep -oE '[0-9]+' || true)"
if [[ -n "$retire_pr" ]]; then
  if command -v gh >/dev/null 2>&1; then
    st="$(gh pr view "$retire_pr" --json state -q .state 2>/dev/null || echo UNKNOWN)"
    if [[ "$st" == "MERGED" ]]; then
      sub_ok=1
      log "H5: subtraction PR #$retire_pr state=MERGED"
    else
      fail "subtraction PR #$retire_pr state=$st (need MERGED)"
      missing+=("subtraction-pr-not-merged")
    fi
  else
    warn "gh unavailable; cannot verify H5-RETIRE-PR:$retire_pr state"
    missing+=("subtraction-pr-unverified")
  fi
fi
if [[ "$sub_ok" -eq 0 ]] && ! printf '%s' "${missing[*]}" | grep -q subtraction; then
  missing+=("subtraction-gate")
fi

# Fail-open structural smell (warn only) on changed shell hooks
while IFS= read -r f; do
  [[ -z "$f" || ! -f "$f" ]] && continue
  [[ "$f" != hooks/* ]] && continue
  # crude: catch "|| true" / "|| :" after critical decision paths + "exit 0" in error handlers
  if grep -nE '\|\|\s*(true|:)\s*$' "$f" | grep -qiE 'jq|curl|gh |git ' ; then
    warn "possible fail-open (command || true) in $f — review manually"
  fi
done <<<"$(printf '%s\n' "$DIFF_FILES")"

if ((${#missing[@]} > 0)); then
  fail "admission fee incomplete: ${missing[*]}"
  fail "Required: (1) 陰性テスト red 実測記録 (2) H6 台帳配線 (3) 廃止条件宣言 — in PR body and/or code"
  fail "See design/ops/harness/h5-negative-test-gate.md"
  # Optional local ledger (does not affect CI if path missing)
  if [[ -n "$LEDGER_PATH" ]]; then
    mkdir -p "$(dirname "$LEDGER_PATH")" 2>/dev/null || true
    ts="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown)"
    printf '{"ts":"%s","component":"H5","event":"block","rule":"negative-test-missing","detail":"%s","agent":"ci"}\n' \
      "$ts" "${missing[*]}" >>"$LEDGER_PATH" 2>/dev/null || true
  fi
  exit 1
fi

log "H5-PASS: 3-point admission fee present (negative-test + ledger + retirement)"
exit 0
