# Codex Completion: Issue #559 STT Phase B-1

Date: 2026-04-24
Branch: `perf/qwen-only-fastpath-529-b1`
Route: C

## Summary

- Implemented the Qwen-only fast path in `backend/agents/stt_agent.py`.
- Qwen success now cancels the Vosk fallback task and returns immediately.
- Qwen failure or timeout now releases the fallback gate and starts Vosk sequentially.
- Preserved structured STT timing events using existing `log_stt_event()`.
- Updated ADR 016 with the Phase B-1 adoption rationale from the Phase A profile.

## Tests and Checks

- `pytest backend/tests/agents/test_stt_agent.py -q`: passed, 97 tests.
- `ruff check backend/`: passed.
- `black --check backend/`: passed.
- `git diff --check`: passed.
- `mypy agents/stt_agent.py tests/agents/test_stt_agent.py` from `backend/`: failed on pre-existing backend typing/import issues, including missing stubs/imports and unrelated errors in `utils/context_priority.py`, `tools/enhanced_rag.py`, `utils/memory_helper.py`, and existing `agents/stt_agent.py` lines.

## Coverage Added

- Qwen success path verifies:
  - Vosk fallback inference is not called.
  - Vosk fallback task cancellation is emitted in caplog.
  - `stt_overall_duration_ms - stt_qwen_duration_ms < 100`.
- Qwen failure path verifies:
  - Vosk starts after Qwen completion.
  - Vosk transcript is returned as `vosk-fallback`.

## Operational Readiness

- Env vars/secrets: no changes.
- CORS/domains: no changes.
- MIME/assets: no changes.
- Permissions/IAM/token scope: no changes.
- Schedulers/cron: no changes.
- Migrations/rollback: no migrations.
- Terraform/infra/workflows: no changes.
- Docker/runtime assumptions: no new dependency or runtime env change.
- Post-merge validation: deploy and rerun `scripts/profile_stt.sh --iterations 20 --sleep 4`, then append Phase B-1 production measurements to ADR 016.

## Scope Note

This worktree already had a pre-existing commit on top of `origin/develop`:

- `581e3f5 feat(backend): add content_en to general-what-is-ec and general-airport-hakata-access entries (#512)`
- File: `backend/knowledge/data/general.yaml`

I did not modify or revert that commit. It should be handled before opening the #559 PR if the PR must contain only the Phase B-1 STT change.
