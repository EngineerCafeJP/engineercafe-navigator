# ADR-028: OSS-Portable Observability & Infrastructure

## Status

Proposed (2026-05-18) — OSS Portability Audit (`docs/plans/oss-portability-audit-2026-05-18.md`) を受けて、ADR-027 の Theme A (D4/D5) を OSS-friendly に置き換える追加 ADR。

## Context

### Engineer Cafe Navigator は OSS (ISC license) として公開されている
- ルート `LICENSE` = ISC License、`README.md` で明示
- `docs/OSS-LICENSE-POSTURE.md` で third-party dependency posture を整理

### しかし infra/CI は GCP-locked
2026-05-18 OSS Portability Audit で判明:
- `infra/terraform/` 全 11 ファイル: provider = GCP only (`google_monitoring_*`, `google_logging_metric`, `google_secret_manager_secret`)
- `.github/workflows/ci.yml`: gcloud 関連 26 hits (Cloud Run deploy, Secret Manager, Cloud Scheduler, Artifact Registry)
- `scripts/*.sh` 13 本: `gcloud logging read`, `gcloud secrets versions access` 多用
- `docs/DEPLOYMENT.md`: Cloud Run + Vercel + Supabase 前提のみ

### Application code は実は portable
- Backend Python: GCP SDK 直接 import は **2 ファイルのみ** (legacy `GoogleSTTClient`, `GoogleTTSClient`)
- 現行 primary path (Qwen STT + Piper TTS + Cerebras LLM via OpenRouter) は完全 vendor-neutral
- Frontend Next.js: GCP SDK 使用 **ゼロ**
- 既存 `backend/observability/structured_logger.py` は stdout JSON 出力で **既に vendor-neutral**

### OSS contributor が deploy できない問題
- 「ISC license で OSS」と謳いながら `git clone` した OSS contributor は GCP project + Secret Manager + Cloud Run + Cloud Monitoring の設定無しでは Production Ready な observability/alert が組めない
- これは OSS の趣旨に反する

## Decision

**Application layer は完全 vendor-neutral 化、Infrastructure layer は deployer choice にする**「ハイブリッド戦略」を採用。

### D1: OpenTelemetry SDK を application 層の標準にする
- Backend Python:
  - 既存 `structured_logger.py` の API 互換性は保持
  - 内部実装で `opentelemetry-sdk` + `opentelemetry-exporter-otlp` に置き換え
  - 各 event を OpenTelemetry semantic convention (logs/metrics/traces) として emit
- Frontend Next.js:
  - `navigator.sendBeacon('/api/telemetry/voice', ...)` で Backend に委譲 (現行 Wave 3 FU-23 設計のまま)
  - Backend が受信して OTel SDK に転送

### D2: OpenTelemetry Collector が中継 hub
- Cloud Run / Docker Compose の sidecar として OTel Collector を deploy
- Exporter は config 駆動で選択:
  - **GCP exporter** (`googlecloud`): Cloud Logging / Cloud Monitoring に送信 (terisuke 本番運用)
  - **OTLP exporter**: OSS deployer の Grafana stack (Loki + Prometheus + Tempo) に送信
  - **Prometheus exporter** (pull): OSS deployer が Prometheus 直接 scrape
  - **stdout exporter**: ローカル開発・CI

### D3: Alert rule は Prometheus rule YAML 形式で portable に定義
- 単一 source `infra/observability/alerts.rules.yml` で全 alert 定義
- GCP 運用時: 既存 `infra/terraform/alerts.tf` の Phase 1b 資産を保持 + 本 YAML から派生生成する converter を追加
- OSS deployer: Alertmanager に直接 mount して使う
- 通知 target = `company@cor-jp.com` (両環境で共通)

### D4: Secret backend を抽象化
- 新規 `backend/utils/secrets.py` で provider-agnostic SecretProvider interface 定義
- Provider 実装 (env config で切替):
  - `EnvSecretProvider` (default): `os.getenv(...)` (OSS deployer の最小構成)
  - `SopsSecretProvider`: sops-encrypted YAML を起動時に decrypt (OSS deployer 推奨)
  - `GcpSecretProvider`: 既存 `gcloud secrets versions access` 経路 (terisuke 本番運用)
  - `VaultSecretProvider`: HashiCorp Vault (enterprise OSS deployer)
- Application code は `secrets.get("EVENT_SHEET_GAS_TOKEN")` で透過呼び出し

### D5: Cron backend を抽象化
- 現行 `backend/scripts/sync_event_kb.py` をそのまま使う
- 起動 trigger:
  - GCP 運用: Cloud Scheduler → Cloud Run Job (現行のまま)
  - OSS deployer: GitHub Actions cron / systemd timer / `apscheduler` in-process (例 documentation 提供)
- script 側は trigger に依存しない CLI として実装維持

### D6: Container hosting を deployer choice にする
- Backend `Dockerfile` は既に `python:3.11-slim` ベース、portable
- Frontend `Dockerfile` も同様 (next.js standalone build 対応)
- 新規 `docker-compose.yml` を repo root に追加 (OSS deployer がローカルで全 stack を起動可能):
  - services: backend, frontend, supabase (or postgres + pgvector), loki, prometheus, grafana, alertmanager, otel-collector
- 既存 Cloud Run deploy path (`.github/workflows/ci.yml`) は保持

### D7: Legacy Google STT/TTS client を削除
- `backend/agents/stt_agent.py` の `GoogleSTTClient` クラス削除
- `backend/agents/voice_agent.py` の `GoogleTTSClient` クラス削除
- 影響: 現在も production primary 路線 (Qwen / Piper) は無傷
- これで Application code から GCP SDK 完全除去

### D8: DEPLOYMENT.md を 2 deployment path 構造に
- 「Path A: GCP Production (Cloud Run + Vercel + Supabase)」 — 現状 terisuke が運用中
- 「Path B: OSS Self-Hosted (docker-compose)」 — OSS deployer 向け
- 両 path で共通: env vars, secrets schema, OTel Collector config

## Consequences

### Positive
- **OSS contributor が GCP account なしで full stack を self-host できる**
- Application code から GCP SDK 完全除去 → 移植性 100%
- Observability backend を deployer が選択可能 (Cloud Monitoring / Grafana / Datadog / 他)
- Alert rule が単一 YAML source、両環境で共通
- 既存 GCP 運用 (terisuke 本番) は **無傷で継続**
- Wave 3 既存設計 (ADR-027) の Theme A も OSS-friendly に進化

### Negative
- Wave 3 工数増加 (約 +8 日 = Theme C 5d + Theme A 改修 3d)
- OpenTelemetry SDK の学習コスト (Python / TS 双方)
- 2 つの infra config (GCP exporter / OTLP) を維持するオーバーヘッド
- OSS deployer の SMTP server 確保が前提 (docker-compose に mailhog 同梱で開発時は OK)

### Out of scope (本 ADR では実装しない)
- BigQuery export sink (将来検討)
- Kubernetes Helm chart (Wave 4+ 検討)
- Multi-cloud abstraction (AWS / Azure adapter) — 本 ADR は OSS portability に focus、multi-cloud 商用化は別判断
- Frontend Vercel 脱却 (Next.js standalone は対応するが、Cloudflare Pages / Netlify 等 migration は Wave 4+)

## Follow-up

- Wave 3 完了後 1 ヶ月: OSS deployer の docker-compose path で実際に self-host 検証してくれる external contributor を募集
- Wave 4 検討: Helm chart, Kubernetes manifest example, Terraform module for AWS/Azure (商用 multi-cloud に進化判断したら)
- ADR-027 の Decision D4 / D5 (Cloud Logging metrics / GCP-only alerts) は **本 ADR で superseded**

## Approvals

- Proposed: Claude (2026-05-18) — OSS portability audit 後の追加 ADR
- 承認待ち: Terada Kousuke (terisuke)

## References

- [ADR-027 Wave 3 Observability & Refactor Foundation](./027-wave3-observability-and-refactor-foundation.md)
- [OSS Portability Audit (2026-05-18)](../plans/oss-portability-audit-2026-05-18.md)
- [ADR-026 Wave 2 Kiosk UX Reliability Baseline](./026-wave2-kiosk-ux-reliability-baseline.md)
- [README OSS License declaration](../../README.md)
- [LICENSE](../../LICENSE) (ISC)
- [docs/OSS-LICENSE-POSTURE.md](../OSS-LICENSE-POSTURE.md)
- OpenTelemetry Python SDK: https://opentelemetry.io/docs/instrumentation/python/
- OpenTelemetry Collector: https://opentelemetry.io/docs/collector/
- Grafana Loki: https://grafana.com/oss/loki/
- Prometheus Alertmanager: https://prometheus.io/docs/alerting/latest/alertmanager/
- HashiCorp Vault: https://www.vaultproject.io/
- sops (Mozilla): https://github.com/getsops/sops
