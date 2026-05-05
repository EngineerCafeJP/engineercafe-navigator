# デプロイガイド

> **索引**: [Documentation hub（README.md）](README.md)
>
> Engineer Cafe Navigator の本番デプロイ運用ガイド
> Last updated: 2026-05-05（ライブ revision・run ID は [STATUS.md](STATUS.md) を正とする）

## インフラ構成

```text
Browser / Kiosk
     |
     v
Vercel (Next.js 15 frontend)
  - 本番公開面
  - App Router + API proxy routes
     |
     v
Cloud Run: engineer-cafe-backend (asia-northeast1)
  - FastAPI + LangGraph
  - protected API の本体
     |
     +---> Supabase (PostgreSQL + pgvector)
     |
     +---> Cloud Run: piper-plus / voicevox-proto (TTS 経路)
     |
     +---> OpenRouter / Gemini / Cerebras (LLM 経路)
```

### サービス一覧

| サービス | プラットフォーム | リージョン | 用途 |
| --- | --- | --- | --- |
| Frontend | Vercel | Global CDN | Next.js UI + API プロキシ |
| Backend | Cloud Run `engineer-cafe-backend` | `asia-northeast1` | FastAPI + LangGraph |
| PiperPlus / VoiceVox | Cloud Run | `asia-northeast1` / `asia-northeast2` | TTS 経路（deploy 設定に従う） |
| Database | Supabase (PostgreSQL + pgvector) | Managed | 会話履歴・ナレッジ・セッション等 |
| LLM プロバイダ | OpenRouter / Gemini / Cerebras | Managed | 応答生成・fast フォールバック・フィラー |

### フロントエンド origin の正本

- 正規の production origin は Vercel プロジェクトの primary production ドメイン
- 任意の preview URL を正本にしない
- backend 側の `FRONTEND_PRODUCTION_ORIGIN` と `ALLOWED_ORIGINS` はこの値と一致させる

### レガシー注記

- 旧 Cloudflare Workers frontend は現行 production default ではない
- 運用判断は Vercel + Cloud Run を正とする

## 環境変数

### フロントエンド（Vercel）

Vercel project の Environment Variables に設定する。

| Variable | Required | Description |
| --- | --- | --- |
| `NEXT_PUBLIC_BACKEND_API_URL` | Yes | browser から見える backend URL |
| `BACKEND_API_URL` | Yes (server) | server-side proxy の転送先 |
| `BACKEND_API_KEY` | Yes (server) | protected backend route へ送る `X-API-Key` |
| `ADMIN_API_SECRET` | Yes | `/api/admin/*`, `/api/cron/*`, `/api/monitoring/*` を保護 |
| `ALERT_WEBHOOK_SECRET` | If used | `/api/alerts/webhook` POST を保護 |
| `NEXT_PUBLIC_SUPABASE_URL` | Yes | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Yes | Supabase anon key |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | server-only の service role |
| Other AI / optional keys | As needed | frontend README と CI 設定に合わせる |

### バックエンド（Cloud Run）

正本は `.github/workflows/ci.yml` の deploy job。

典型的な deploy 設定:

- `--memory 8Gi --cpu 4 --concurrency 1 --min-instances 1 --max-instances 3`
- non-secret env 例:
  - `ENVIRONMENT=production`
  - `TTS_PROVIDER=piper`
  - `STT_PROVIDER=qwen-primary`
  - `QWEN_STT_TIMEOUT=45`
  - `QWEN_STT_HEDGE_DELAY_SECONDS=4`
  - `QWEN_STT_HEDGE_GRACE_SECONDS=6`
  - `FRONTEND_PRODUCTION_ORIGIN=<vercel-production-origin>`
  - `ALLOWED_ORIGINS=<vercel-production-origin>`
- secret は `--update-secrets` で更新する

| Variable | Required | Description |
| --- | --- | --- |
| `API_SECRET_KEY` | Yes (production) | frontend -> backend 認証の正本 |
| `ENVIRONMENT` | Yes | Cloud Run では `production` |
| `OPENROUTER_API_KEY` | Yes | LLM provider |
| `FAST_LLM_ENABLED` | If using fast path | identity 以外の daily/general light fast LLM を有効化 |
| `FAST_LLM_PRIMARY_PROVIDER` / `FAST_LLM_PRIMARY_MODEL` | If using fast path | fast answer の primary provider / model |
| `FAST_LLM_FALLBACK_PROVIDER` / `FAST_LLM_FALLBACK_MODEL` | If using fast path | fast answer の fallback provider / model |
| `FAST_LLM_TERTIARY_PROVIDER` | If using Cerebras | OpenRouter primary/fallback 失敗後の tertiary provider |
| `CEREBRAS_ENABLED` | If using Cerebras | Cerebras tertiary fallback / filler を有効化 |
| `CEREBRAS_API_KEY` | If using Cerebras | Cerebras fast answer / filler provider |
| `CEREBRAS_FAST_MODEL` | If using Cerebras | default: `gpt-oss-120b` |
| `CEREBRAS_REASONING_EFFORT` | If using Cerebras GPT OSS | `low` / `medium` / `high`; alpha fast path は `low` |
| `SUPABASE_URL` / `SUPABASE_KEY` / `SUPABASE_DB_URI` | Yes | Supabase / Postgres 接続 |
| `ALLOWED_ORIGINS` | Yes | CORS origin |
| `TTS_PROVIDER` / `STT_PROVIDER` | Per deploy | 音声経路設定 |
| `VOICEVOX_API_URL` | If using VoiceVox | `voicevox-proto` URL |

注意:

- Cloud Run の env 更新は `--update-env-vars` を使う
- `--set-env-vars` で既存値を消さない
- 新しい secret provider を追加した場合は、GitHub Actions secret と Google Secret Manager の両方を更新する
- Gemini preview model は deploy 前に実 API model id / region / quota を確認する。docs 上の marketing name をそのまま Cloud Run env に入れない

## デプロイ手順

### デプロイ手順: フロントエンド（Vercel）

1. `develop` へ merge する
2. Vercel の Git integration または deploy hook で build / deploy を走らせる
3. production domain を canonical URL として扱う

リリース前のローカル確認:

```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm build
```

### デプロイ手順: バックエンド（Cloud Run）

`develop` への push で backend path に変更がある場合、GitHub Actions の
`backend-deploy-staging` が image build と Cloud Run deploy を実施する。

manual deploy をする場合も、workflow と同じ前提に寄せる:

- `linux/amd64` build
- Artifact Registry push
- `gcloud run deploy`
- secret は `--update-secrets`

### Cerebras のシークレット設定

Cerebras を有効化する場合は、local secret を chat や issue comment に貼らない。

GitHub Actions:

```bash
gh secret set CEREBRAS_API_KEY --body "$CEREBRAS_API_KEY"
```

Google Secret Manager:

```bash
gcloud secrets create CEREBRAS_API_KEY --replication-policy=automatic
printf "%s" "$CEREBRAS_API_KEY" | \
  gcloud secrets versions add CEREBRAS_API_KEY --data-file=-
```

既に secret がある場合は `gcloud secrets create` は不要。

Cloud Run deploy command では `--update-secrets` に次を追加する。

```text
CEREBRAS_API_KEY=CEREBRAS_API_KEY:latest
```

Terraform では `infra/terraform/secrets.tf` に runtime secret container を定義している。ただし既存 Secret Manager resource との衝突を避けるため、`manage_runtime_secrets` の default は `false` とする。Terraform 管理へ移す場合は、先に `google_secret_manager_secret.runtime["CEREBRAS_API_KEY"]` を import するか、未作成環境で `manage_runtime_secrets=true` を使う。secret version / 値は Terraform state に入れない。

## CI / CD

- Pull request: lint・typecheck・build・backend テスト・Playwright マージゲート
- Backend 自動デプロイ: `develop` push → GitHub Actions → Cloud Run
- Frontend 自動デプロイ: `develop` push → Vercel

## 本番設定の確認方法

### バックエンド（Cloud Run）

```bash
gcloud run services describe engineer-cafe-backend \
  --region asia-northeast1 \
  --project aipartner-426616 \
  --format yaml
```

確認ポイント:

- image
- env vars
- secret bindings
- traffic / revision

### フロントエンド（Vercel）

- Vercel dashboard の Deployments / Domains を確認
- CLI を使う場合は `vercel list --yes`
- `FRONTEND_PRODUCTION_ORIGIN` が production domain と一致していることを確認

### 最近のログ確認

- Cloud Run: deploy 後 15-60 分は `gcloud logging read` を見る
- Vercel: deployment history を first signal とし、`vercel logs` だけに依存しない
- Supabase: 現行 operator flow では CLI だけで十分な recent runtime log が取れない場合がある

### ヘルスチェック

```bash
curl -sf "$(gcloud run services describe engineer-cafe-backend --region asia-northeast1 --format='value(status.url)')/health"
```

## リリース前チェック

### リリース前（毎回）

- CI が green
- Vercel target 環境に `BACKEND_API_KEY` がある
- Cloud Run target 環境に `API_SECRET_KEY` がある
- Vercel に `ADMIN_API_SECRET` がある
- `FRONTEND_PRODUCTION_ORIGIN` が Vercel production domain と一致
- backend の `ALLOWED_ORIGINS` が同じ origin を含む
- 新しい env var を追加した場合は docs を更新済み
- schema change がある場合は Supabase migration 適用済み
- Apple Silicon で build する場合は `--platform linux/amd64`
- identity / help / capability route が provider self-disclosure を返さない
- daily/general light route が RAG miss だけで Tavily / web search に落ちない
- Gemini / Cerebras の model id は公式 API availability check と benchmark 結果で採用理由が残っている

### デプロイ後

- backend `/health` が `200`
- backend protected route に `X-API-Key` なしで投げると `403`
- frontend が critical console error なしで表示される
- admin route は `ADMIN_API_SECRET` なしで `401`
- voice path の smoke test が通る
- production frontend 経由の `GET /api/voice?action=supported_languages` が `200`
- production frontend 経由の `POST /api/character` が `200`
- `frontend-latency-probe` workflow で `/api/qa` `/api/voice` `/api/character` の p50 / p95 / p99 を採取する
- Cloud Run logs に immediate な `403` / `5xx` spike がない
- Cloud Run logs で `assistant_profile` / `daily_conversation` / `general_light` / `current_info` の route 分布を確認する
- `あなたの名前は`, `何ができますか`, `明日のイベントを教えて` を production frontend 経由で確認する

## リリース時のガードレール

現在の最重要 release risk は、backend auth 自体の欠如ではなく、次の不整合です。

- Vercel `BACKEND_API_KEY`
- Cloud Run `API_SECRET_KEY`

frontend は `BACKEND_API_KEY` が missing / stale でも startup 自体は止まりません。
そのため release validation では、実際の Vercel -> Cloud Run 経路を通す必要があります。

最低限の運用ルール:

1. target production deployment を Vercel で特定する
2. その deployment に対して frontend-authenticated smoke check を実行する
3. 同じ時間帯の Cloud Run logs を確認する
4. ここまで通って初めて healthy deploy とみなす

実装済みの補助:

- manual / local 実行: `scripts/verify-frontend-production.sh`
- GitHub Actions: `.github/workflows/frontend-production-smoke.yml`

## レイテンシのベースライン

live 検証の前に、frontend 実経路の遅延を最低 1 回は採取する。

### GitHub Actions（ワークフロー）

- workflow: `Frontend Latency Probe`
- trigger: `workflow_dispatch`
- artifact:
  - `artifacts/latency-probe.json`
  - `artifacts/latency-probe.md`

### ローカル実行

```bash
python scripts/latency_probe.py \
  --base-url https://frontend-delta-six-20.vercel.app \
  --iterations 3
```

この probe は以下を対象にする。

- `POST /api/qa`
- `POST /api/voice` (`text_to_speech`)
- `POST /api/character`

field verification で iPad 系の音声停止が出たため、数値だけでなく実機再生も合わせて確認する。

### Alpha fast response のゲート

ADR 018 の実装後は、release 前に次の gate を通す。

| 経路 | ゲート |
| --- | --- |
| identity / help / capability | p95 1s 未満、LLM / RAG / web search 不使用、provider self-disclosure 0 件 |
| daily/general light | p95 3s 未満、current-info でない限り Tavily / web search 不使用 |
| current-info | calendar / web search を使う理由が route metadata に残る |
| voice full turn | STT / chat / TTS の区間別 p50 / p95 を採取し、#613 に追記 |

## ロールバック

### フロントエンド（Vercel）

- Vercel Deployments から previous deployment を promote / revert

### バックエンド（Cloud Run）

```bash
gcloud run revisions list \
  --service engineer-cafe-backend \
  --region asia-northeast1 \
  --project aipartner-426616

gcloud run services update-traffic engineer-cafe-backend \
  --region asia-northeast1 \
  --project aipartner-426616 \
  --to-revisions REVISION_NAME=100
```

## データベース（Supabase）

- RLS は有効
- service role access は server-side only

```bash
supabase db push
```

代表 table:

- `knowledge_base`
- `conversation_sessions`
- `conversation_history`
- `agent_memory`
- `reception_sessions`

## トラブルシューティング

### デプロイ後のバックエンドエラー

```bash
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="engineer-cafe-backend"' \
  --project aipartner-426616 \
  --limit 50 \
  --format "table(timestamp, textPayload)"
```

### フロントの admin ルート設定ミス

- `ADMIN_API_SECRET` が Vercel 側と一致しているか確認

### `POST /api/character` で `403` が増える

まず deploy / config mismatch を疑う:

- Vercel の `BACKEND_API_KEY` を確認
- Cloud Run の `API_SECRET_KEY` を確認
- `scripts/verify-frontend-production.sh <frontend_url>` で frontend-authenticated smoke check を再実行
- 同じ deploy window の Cloud Run logs を確認

### Supabase errors

- `SUPABASE_DB_URI` が CI placeholder になっていないか確認

## 現在の本番リスク

追跡先:

- `#468`: deploy-time auth drift guardrails
- `#140`: latency / load baseline
- `#458`: emotion / animation contract mismatch
- `#138` / `#398`: multilingual quality closure

[ドキュメント索引へ](README.md)
