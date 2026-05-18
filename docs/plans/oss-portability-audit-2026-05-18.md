# OSS Portability Audit (2026-05-18)

> **対象**: terisuke + Backend / Frontend / Infra 全担当
> **作成**: 2026-05-18, Claude Code session
> **目的**: OSS として公開している (ISC license) Engineer Cafe Navigator の GCP プラットフォーム依存度を実測し、Wave 3 で OSS-portable 基盤への移行計画を策定するための監査レポート
> **トリガー**: terisuke 指摘 (Cloud Monitoring/Alert がプラットフォーム依存なので OSS deployer が使えない)

---

## 0. Executive Summary

| 領域 | GCP 依存度 | OSS deployer 影響 | 移行難度 |
|------|-----------|-----------------|---------|
| **Application code (backend)** | **低** (2 ファイル、legacy fallback のみ) | 小 | ⭐ 容易 |
| **Application code (frontend)** | **ゼロ** | なし | — |
| **Observability (logs / metrics / alerts)** | **高** (infra/terraform/ 全 GCP-locked) | 大 (OSS だと観測不能) | ⭐⭐⭐ 中-高 |
| **Secret management** | **高** (Secret Manager 専用) | 中 (env 直書き fallback あり) | ⭐⭐ 中 |
| **Cron / scheduled jobs** | **高** (Cloud Scheduler) | 中 (GitHub Actions cron で代替可) | ⭐⭐ 中 |
| **Compute / hosting** | **高** (Cloud Run) | 中 (Dockerfile 既存、k8s/Compose 可) | ⭐⭐ 中 |
| **CI/CD** | **高** (gcloud 26 hits) | 中 (GHCR + 他 host で可) | ⭐⭐ 中 |
| **Database** | **ゼロ** (Supabase = self-hostable) | なし | — |
| **LLM provider** | **ゼロ** (OpenRouter = vendor-neutral) | なし | — |

### 結論
**コードは既に 95% OSS-portable、infra (terraform/CI/scripts) が GCP-locked**。Wave 3 で OSS-friendly な observability/secrets/cron 基盤を追加 (既存 GCP は GCP exporter として保持) すれば、両方の deployer (terisuke の本番運用 + OSS contributor) が共存できる。

---

## 1. 詳細監査結果

### 1.1 Application code (Backend Python)

**Backend Python の google-* import 実測 (`git ls-tree origin/develop` + grep)**:

| File | line | import | 用途 |
|------|------|--------|------|
| `backend/agents/stt_agent.py` | 1491 | `from google.cloud import speech` | **GoogleSTTClient** (legacy fallback、現行は Qwen primary) |
| `backend/agents/voice_agent.py` | 444 | `from google.oauth2 import service_account` | **GoogleTTSClient** (legacy Wavenet TTS、現行は Piper primary) |
| `backend/agents/voice_agent.py` | 471 | `from google.auth.transport.requests` | 上記 access token refresh |

**Backend dependencies**:
- `requirements.txt`: `google-auth>=2.0.0` (transitive、access token refresh 用)
- `google-cloud-speech` は実は requirements.txt に **書かれていない** (Cloud Run image でのみ available) → already abstracted as optional

**結論**: Application code の GCP 結合は **legacy fallback path 2 箇所のみ**。primary path (Qwen + Piper) は完全 vendor-neutral。

### 1.2 Application code (Frontend)

**Frontend `@google-cloud/*` direct import grep 結果: ZERO**

`@opentelemetry/api` が `frontend/package-lock.json` に transitive dep で出現するが、direct import なし。
→ Frontend は **完全 OSS-portable**。

### 1.3 Infrastructure (infra/terraform/)

**全 11 ファイル、全 GCP-locked**:

| File | 内容 | GCP resource |
|------|------|------------|
| `providers.tf` | provider 宣言 | `google` only |
| `variables.tf` | GCP project_id / region default | `aipartner-426616` / `asia-northeast1` |
| `secrets.tf` | Secret Manager 管理 | `google_secret_manager_secret` |
| `log_metrics.tf` | log-based metrics (chat_response_count 等) | `google_logging_metric` |
| `alerts.tf` | SLO burn rate alert (chat fallback 等) | `google_monitoring_alert_policy` |
| `dashboard.tf` | STT latency dashboard | `google_monitoring_dashboard` |
| `outputs.tf` | output 定義 | GCP resource id 系 |
| `locals.tf` | local 変数 (metric.type 等) | GCP-specific naming |

**既存 alerts.tf の中身** (重要):
- `Engineer Cafe chat fallback burn rate` (1h / 6h burn rate, SLO 98%) — Issue #513 Phase 1b で land 済
- `notification_channels = var.notification_channel_ids` (デフォ `[]`、apply 前に手動セット)
- → **既に GCP-locked な alert は存在するが、notification channel が未設定 (default empty)**

### 1.4 CI / CD (.github/workflows/ci.yml)

**gcloud 関連の hits: 26** (主要):

| ライン | 操作 | GCP service |
|-------|------|------------|
| 531 | `google-github-actions/auth@v3` | Workload Identity Federation |
| 539 | `gcloud auth configure-docker` | Artifact Registry |
| 545-551 | `docker build/push asia-northeast1-docker.pkg.dev/...` | Artifact Registry |
| 565-570 | `gcloud secrets create / versions add` | Secret Manager (CI 経由で API key sync) |
| 604-624 | `gcloud secrets versions access` | Secret Manager 読み (5 secrets) |
| 630 | `gcloud run deploy` | Cloud Run service deploy |
| 654 | `gcloud run services update-traffic` | Cloud Run traffic split |
| 672 | `gcloud services enable cloudscheduler.googleapis.com run.googleapis.com` | API enable |
| 683 | `gcloud run jobs deploy` | Cloud Run Job (cron) |
| 699-716 | `gcloud scheduler jobs create/update http` | Cloud Scheduler |
| 731 | `gcloud run jobs execute` | Cron 実行 |
| 829 | `gcloud secrets versions access --secret=API_SECRET_KEY` | Smoke test 用 |

**他の workflow**:
- `alpha-live-verification.yml`: 5 hits (Cloud Run revision 確認)
- `terraform-plan.yml`: 1 hit (terraform PR validation)
- `voice-e2e-nightly.yml`: 1 hit (API key 取得)

**Scripts**:
- `cloud-logging-verify.sh`: 5 hits (`gcloud logging read`)
- `onsite-voice-live-proof.sh`: 5 hits (Secret Manager + gcloud)
- `stt-postdeploy-logging-check.sh`: 3 hits
- 他 10 script 程度

### 1.5 Cloud Run hosting

- backend, piper-plus, voicevox-proto の 3 service が Cloud Run で稼働
- Dockerfile は `python:3.11-slim` ベース、portable
- env vars / secrets が GCP Secret Manager bind
- Workload Identity Federation で SA 認証

### 1.6 OSS / LICENSE 宣言

- ルート `LICENSE` = **ISC License** (very permissive)
- `docs/OSS-LICENSE-POSTURE.md` で third-party dependency posture を整理
- `README.md` で「**OSS / ライセンス: LICENSE (ISC)**」を明示
- 一方で `DEPLOYMENT.md` は Cloud Run + Vercel 前提のみ記述 ← **OSS contributor が deploy できない**

---

## 2. OSS Portable Alternative マッピング

| 領域 | 現状 GCP | OSS / Portable 代替 | 移行コスト | 既存資産活用 |
|------|---------|------------------|----------|------------|
| **構造化ログ** | Cloud Logging (stdout 経由) | stdout JSON (既に出力済) → Grafana Loki / Vector / journald | **ゼロ** (既に portable) | structured_logger.py そのまま使える |
| **Metrics** | Cloud Logging log-based metrics | OpenTelemetry SDK → Prometheus / VictoriaMetrics | ⭐⭐ | terraform spec を OTel semantic convention に翻訳 |
| **Alerts** | google_monitoring_alert_policy (Terraform) | Prometheus Alertmanager (rule YAML) | ⭐⭐ | alerts.tf の condition を YAML alert rule に変換 |
| **通知 (email)** | google_monitoring_notification_channel | Alertmanager SMTP receiver | ⭐ (SMTP server 必要) | 同 `company@cor-jp.com` を target |
| **Dashboard** | google_monitoring_dashboard | Grafana dashboard JSON | ⭐⭐ | dashboard.tf の widget spec を Grafana JSON に翻訳 |
| **Secrets** | Secret Manager + Workload Identity | (a) `.env` + sops-encrypted, (b) HashiCorp Vault, (c) Doppler | ⭐⭐ | env vars 経由のため app code は変更不要 |
| **Cron** | Cloud Scheduler → Cloud Run Job | (a) GitHub Actions cron, (b) systemd timer, (c) APScheduler in-process | ⭐ | sync_event_kb.py を Python script として直接呼べる |
| **Compute** | Cloud Run | docker-compose / Kubernetes / Fly.io / Railway / VPS | ⭐ | Dockerfile 既存、追加 compose.yaml だけ |
| **Container Registry** | Artifact Registry | GHCR (GitHub Container Registry) / Docker Hub | ⭐ | CI 設定変更のみ |
| **Frontend hosting** | Vercel | Cloudflare Pages / Netlify / Docker self-host (Next.js standalone) | ⭐ | Vercel 専用 API 未使用 |

### 重要: ハイブリッド戦略 (推奨)

「**Application は vendor-neutral、infra は deployer choice**」を実現:

```
              ┌─ Backend (Python, ZERO GCP coupling in primary path)
              │   ├─ logs.info(extra={"event":..., ...}) → stdout JSON
              │   └─ otel.metric.record(...)              → OTel SDK
              │
              ├─ Frontend (Next.js, ZERO GCP coupling)
              │   └─ navigator.sendBeacon('/api/telemetry/voice', ...)
              │
              v
       ┌──────────────────────────┐
       │ OpenTelemetry Collector  │  ← sidecar or external
       └──────────────────────────┘
              │
   ┌──────────┼──────────────────────────────┐
   v          v                              v
[GCP exporter]   [OTLP/Prometheus exporter]   [stdout exporter (dev)]
   │                  │                          │
   v                  v                          v
Cloud Logging   Loki/Prometheus/Grafana   docker logs
+ Monitoring    + Alertmanager (OSS)      (local dev)
(現行)          (OSS contributor)         (CI)
```

**メリット**:
- Application code から GCP SDK を **完全除去**できる
- terisuke は GCP exporter で Cloud Monitoring 経由運用継続
- OSS contributor は docker-compose で Grafana stack を立てて使える
- 同じ alert rule YAML を双方で使える (Prometheus rule format → GCP に変換できる converter あり)

---

## 3. 現在 Wave 3 ADR-027 / Issue 群との衝突点

### 3.1 ADR-027 の問題点
- **GCP-specific な alert/metric を「全部新規作成」前提**で書いてある
- 既存 `infra/terraform/alerts.tf` の Phase 1b 資産を考慮していない
- OSS portability の視点が完全に欠如

### 3.2 Issue の修正必要箇所
- **#883 FU-24** "Cloud Logging log-based metrics 9 個作成" → OpenTelemetry semantic convention で metric 定義に変更
- **#884 FU-25** "Notification channel + Alert policies" → Prometheus alert YAML + Alertmanager (GCP は exporter として保持)
- 新規 **Theme C** 追加: OSS Portability (FU-31〜35)

### 3.3 PR #890 への対応
- そのまま merge OK (ADR-027 として "Proposed" 状態)
- merge 後に **ADR-028 (OSS Portability)** を追加で起票し、ADR-027 の D4/D5 を OSS-friendly に置き換える形で superseded
- または PR #890 を update して ADR-027 と ADR-028 を同 PR に統合

---

## 4. 推奨アクション (3 段階)

### 段階 1: 即時 (本セッション)
- [ ] 本 audit doc を `feat/wave3-design` branch に追加
- [ ] **ADR-028: OSS-Portable Observability & Infrastructure** を起草
- [ ] Wave 3 Epic #877 に Theme C 追加コメント
- [ ] FU-24 #883 / FU-25 #884 を「OSS-friendly に改定 (Theme C 待ち)」とコメント
- [ ] 新 Theme C sub-issues (FU-31〜35) を起票

### 段階 2: Wave 3 実装中 (1〜2 週間)
- [ ] FU-31: Legacy GoogleSTTClient + GoogleTTSClient を削除 (Qwen + Piper のみに統一)
- [ ] FU-32: docker-compose.yaml (backend + frontend + Loki + Prometheus + Grafana + Alertmanager + SMTP) 追加
- [ ] FU-33: Secret backend 抽象化 (`backend/utils/secrets.py` で env / sops / Vault を pluggable)
- [ ] FU-34: Cron backend 抽象化 (Cloud Scheduler / GitHub Actions cron / APScheduler の例 documentation)
- [ ] FU-35: `docs/DEPLOYMENT.md` 改訂 — Cloud Run path + OSS Docker Compose path の 2 つを記述

### 段階 3: Wave 4+ (1〜2 月)
- OpenTelemetry SDK 全面導入 (Backend Python + Frontend TS)
- terraform/cloud-monitoring/ の GCP 専用 resource を、OpenTelemetry 経由の汎用定義 + GCP exporter config に置き換え
- `infra/k8s/` 新設 (OSS deployer 向けの Kubernetes manifest example)

---

## 5. 工数見積 (Wave 3 拡張版)

| Theme | 既存工数 | OSS 化追加 | 合計 |
|-------|---------|----------|------|
| Theme A (Observability) | 7.5d | +3d (OTel SDK 導入) | 10.5d |
| Theme B (Refactor) | 9d | 変更なし | 9d |
| **Theme C (OSS Portability)** | — | **+5d (新規)** | 5d |
| 合計 | 16.5d | +8d | **24.5d** |

人員: Backend 2-3 名 + Frontend 1-2 名 + Infra 1 名 並列で **約 10〜14 営業日** (Theme C を Theme A/B と並列実施)

---

## 6. リスク & トレードオフ

| Risk | 影響 | 緩和策 |
|------|------|--------|
| Wave 3 工数増 (16.5d → 24.5d) | リリース遅延 1 週間 | Theme C は P1 として後回し可、Theme A/B 優先で alpha closer 維持 |
| OpenTelemetry 学習コスト | engineer 慣れ要 | Python OTel SDK は標準 API、Datadog/Sentry 経験者は流用可 |
| 2 つの infra config 維持コスト | infra engineer 工数 | OTel Collector config 1 本で両方カバー、terraform は GCP exporter config のみ |
| OSS deployer の SMTP server 確保 | external dependency | docker-compose に `mailhog` (開発用) + production は OS 提供 SMTP に委譲 |
| GCP-only feature (Workload Identity Federation) 失う | CI セキュリティ低下 | OSS deployer は env-based secret 経由、CI も別 path |

---

## 7. 結論

terisuke 指摘は **的確かつ実現可能**:

1. ✅ **Application code は既に 95% portable** (Backend 2 ファイル + 全 Frontend が GCP-free)
2. ✅ **既存 structured_logger.py は stdout JSON 出力で既に vendor-neutral**
3. ⚠️ **infra/terraform/, CI workflow, scripts は GCP-locked** だが、これらは OSS deployer 視点では再生成可能
4. ⭐ **OpenTelemetry + Grafana stack + docker-compose の追加で OSS deployer が完全に self-host 可能になる**
5. 🔄 **既存 GCP 資産 (infra/terraform/alerts.tf 等) は GCP exporter として保持**、Wave 3 で削除しない

→ **Wave 3 に Theme C (OSS Portability) を追加** し、Application は完全 vendor-neutral、infra は deployer choice の構造に進化させるのが最適解。

---

## 8. Reference

- ADR-027 (Wave 3 設計、本 audit で改定提案): `docs/adr/027-wave3-observability-and-refactor-foundation.md`
- ADR-028 (OSS Portability、本 audit から起草予定): `docs/adr/028-oss-portable-observability-and-infrastructure.md`
- 既存 GCP infra: `infra/terraform/`
- OSS license posture: `docs/OSS-LICENSE-POSTURE.md`
- README ISC license 宣言: `README.md`
- Wave 3 Epic: #877
- Wave 3 PR (本 audit と合流): #890
