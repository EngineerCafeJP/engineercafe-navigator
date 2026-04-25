# Codex Completion: Alpha Final Live Verification Scripts

Date: 2026-04-25
Branch: `test/alpha-final-live-verification-scripts`
Base: `origin/develop` at `3b7d76e`
Route: C

## Summary

Implemented the alpha final live verification preparation bundle for the 2026-04-26 live run:

- `scripts/alpha-smoke-comprehensive.sh`
  - Covers A voice round-trip, B LangGraph routing/fast-path/reception/farewell/slides, and D memory/state/adversarial checks.
  - Fetches `API_SECRET_KEY` from Secret Manager when not provided.
  - Writes `backend/tests/reports/alpha-final-<timestamp>.md` and `.csv`.
  - Supports `--help` and network-free `--dry-run`.
- `scripts/rag-live-test.sh`
  - Wraps `backend/tests/evaluation/run_ragas_evaluation.py --mode live --max-cases 127` for direct `EnhancedRAGSearch` evaluation.
  - Runs per-language checks with Python-enforced per-language timeout and answer_correctness targets from `backend/evaluation/datasets/multilingual_queries.json`.
  - Writes `backend/tests/evaluation/reports/ragas-direct-live-<timestamp>.json` and `.md`.
  - Supports `--help` and network-free `--dry-run`.
- `scripts/rag-api-live-test.sh`
  - Wraps `backend/evaluation/run_live_api_eval.py` for `/api/chat` live API evaluation.
  - Fetches `API_SECRET_KEY` from Secret Manager when not provided.
  - Keeps the API-level RAGAS report separate from the direct RAG report.
- `scripts/cloud-logging-verify.sh`
  - Uses `gcloud logging read` to verify STT structured events, `chat_response` required fields, and memory helper error samples.
  - Enforces 99% default STT event generation threshold.
  - Writes `backend/tests/reports/cloud-logging-check-<timestamp>.md`.
  - Supports `--help` and network-free `--dry-run`.
- `scripts/stt-live-preflight.sh`
  - Uses `gcloud logging read` to summarize recent `stt_winner` latency, Qwen timeout samples, and Vosk fallback distribution before A-series voice execution.
  - Writes `backend/tests/reports/stt-live-preflight-<timestamp>.md`.
  - Supports `--help` and network-free `--dry-run`.
- `docs/testing/alpha-final-scenarios.md`
  - Documents 40 A-series utterances, 40 B-series routing cases, 5 adversarial prompts, and long utterance samples.

## Verification

Passed:

- `bash -n scripts/alpha-smoke-comprehensive.sh scripts/rag-live-test.sh scripts/rag-api-live-test.sh scripts/cloud-logging-verify.sh scripts/stt-live-preflight.sh`
- `shellcheck scripts/alpha-smoke-comprehensive.sh scripts/rag-live-test.sh scripts/rag-api-live-test.sh scripts/cloud-logging-verify.sh scripts/stt-live-preflight.sh`
- `git diff --check`
- `scripts/alpha-smoke-comprehensive.sh --help`
- `scripts/rag-live-test.sh --help`
- `scripts/cloud-logging-verify.sh --help`
- `scripts/alpha-smoke-comprehensive.sh --dry-run --timestamp DRYRUN`
- `scripts/rag-live-test.sh --dry-run --timestamp DRYRUN --languages ja,en`
- `scripts/rag-api-live-test.sh --dry-run --timestamp DRYRUN --languages ja,en`
- `scripts/cloud-logging-verify.sh --dry-run --timestamp DRYRUN --minutes 5`
- `scripts/stt-live-preflight.sh --dry-run --timestamp DRYRUN --minutes 5`

Not run:

- Live Cloud Run/API execution, live RAGAS, and Cloud Logging reads. These require production credentials, live API budget, and tomorrow's planned verification window.

## Operational Readiness

- Env/secrets: `alpha-smoke-comprehensive.sh` can read `API_SECRET_KEY` from Secret Manager; live execution requires `gcloud` auth or `--key`.
- Permissions/IAM: Cloud Logging script requires `logging.logEntries.list`; Secret Manager lookup requires secret access on `API_SECRET_KEY`.
- Runtime tools: scripts require `bash`, `python3`, and `curl`; Cloud Logging script additionally requires `gcloud`.
- CORS/MIME/assets: not affected.
- Schedulers/workflows: not affected.
- Migrations/infra/Terraform/Docker: not changed.
- Rollback: remove the three new scripts, scenario doc, and this analysis file.
