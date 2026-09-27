# ローカル運用への移行計画（GCP 停止後）

- 作成: 2026-09-27
- 対象: `origin/develop` @ `eaf3d323`（2026-08-11）
- 状態: **論点 D1〜D4 は回答済み（2026-09-27）・実装は未着手**。Phase 0 の一部は実施済み
- 根拠: `git grep` による全件棚卸し（14 パターン・114 ファイル）と、主要箇所の抜き取り照合

## 1. 背景

- 運用方針: 当面はローカル運用とし、GCP は完全に停止する。
- GCP の状態（2026-09-27）
  - `aipartner-426616`: 2026-09-27 にプロジェクトごと削除した（`gcloud projects undelete` で 2026-10-27 まで復元可）。本番バックエンドの Cloud Run `engineer-cafe-backend`、Cloud Run job `event-kb-sync`、本番 TTS の Cloud Run `piper-plus`・`voicevox-proto` がここにあった
  - 本リポジトリから参照されない別プロジェクトにある Secret Manager の secret も、課金停止の予定がある（§5 の Phase 0）
- GCP の外にある Supabase は稼働中で、本計画の対象外

## 2. 結論

1. **アプリの実行時コードは GCP の API を呼んでいない。** LLM・埋め込み・RAG・STT・TTS には、すべてローカルへの切替手段が既にある（PR #943 の完全オフラインデモ）。
2. **GCP 依存は CI・運用スクリプト・Terraform に集中している。** ヒットした 114 ファイルのうち実行時コードは 5 ファイルで、どれも GCP API の呼び出しではない。
3. **今すぐ起きている影響**
   - 本番バックエンドと本番 TTS は停止した
   - develop への backend 変更の push は `ci-success` で必ず失敗する（`.github/workflows/ci.yml:1046-1051` が `backend-deploy-staging` の成功を要求している）
   - `voice-e2e-nightly.yml`（毎日 03:17 JST）は本番バックエンドに対して走り、失敗すると Issue を自動で起票する（`voice-e2e-nightly.yml:130-137`）。直近の成功は 2026-09-26 の実行。2026-09-27 に無効化した（Phase 0-1）

## 3. 棚卸し

### 3.1 件数（origin/develop）

| パターン | ヒット / ファイル |
| --- | --- |
| `aipartner-426616` | 83 / 35 |
| `GOOGLE_` | 141 / 47 |
| `gcloud` | 237 / 51 |
| `run\.app` | 41 / 28 |
| `@google-cloud/` | 30 / 2（29 件は未使用の `frontend/package-lock.json`） |
| `google-auth-library\|google\.oauth2\|google\.auth` | 23 / 7 |
| `secretmanager\|SecretManager\|secret_manager` | 3 / 3 |
| `texttospeech\|TextToSpeech` | 32 / 14 |
| `speech_v1\|speech\.googleapis\|SpeechClient\|google\.cloud\.speech` | 17 / 5 |
| `generativelanguage\|GoogleGenerativeAI\|@google/genai\|google\.genai\|google-genai` | 22 / 8 |
| `cloudfunctions` / `firestore` / `vertexai\|aiplatform` | 0 / 0 |

ヒットした 114 ファイルを、1 ファイル 1 分類で振り分けた結果:

| 分類 | ファイル数 |
| --- | --- |
| (a) デプロイ設定・IaC・GCP 運用ツール | 14 |
| (b) CI workflow | 6 |
| (c) 実行時コード | 5 |
| (d) 認証・SA・資格情報の読み込み | 0 |
| (e) Secret Manager からの取得 | 8 |
| (f) 文書・テストのみ | 81 |

### 3.2 実行時コード（分類 c）

| ファイル | 内容 | GCP API |
| --- | --- | --- |
| `backend/tools/calendar_service.py:83` | Google カレンダーの ICS URL を HTTPS で取得 | なし（GCP プロジェクトに依存しない） |
| `backend/scripts/sync_event_kb.py:22-23, 78` | イベント KB 同期のバッチ（旧 Cloud Run job） | なし |
| `frontend/next.config.js:88` | CSP の `connect-src` に `https://*.run.app` | なし |
| `frontend/src/lib/api/voice-client.ts` | 型名への誤検出 | なし |
| `frontend/src/app/components/voice-interface/useVoiceTurnProcessor.ts` | 型名への誤検出 | なし |

### 3.3 機能別の現状と、既存のローカル代替

| 機能 | GCP 停止前の本番 | 既存のローカル代替 | 残課題 |
| --- | --- | --- | --- |
| LLM | OpenRouter（Gemini 系のモデル名）と Cerebras | `LLM_PROVIDER=ollama`（`backend/llm/provider.py:110, 136`）、`OLLAMA_BASE_URL`・`OLLAMA_MODEL` | OpenRouter を直接呼ぶ 3 箇所は切替の対象外（`backend/agents/stt/postprocess.py:144-170`、`backend/agents/stt_agent.py:338-350`、`backend/workflows/main_workflow.py:84-86`）。キーが無ければスキップする |
| 埋め込み | OpenRouter `text-embedding-3-small` | `EMBEDDING_API_URL` ほか（`backend/utils/embedding_service.py:40-43`）。デモは Ollama の `nomic-embed-text` | 次元が変わる場合は KB の再埋め込みが要る |
| RAG | Supabase の RPC | `RAG_VECTOR_BACKEND=local-pgvector`（`backend/tools/enhanced_rag.py:39, 146`） | Supabase を続けるかの判断（D1） |
| STT | Vosk / Qwen3-ASR（ローカル） | 変更不要。Google STT のフォールバックは撤去済み（`backend/agents/stt_agent.py:185-187`） | なし |
| TTS | Cloud Run の `piper-plus` / `voicevox-proto`（`ci.yml:673`） | `docker/piper-plus`、compose の `voicevox`・`kokoro-tts`（voice プロファイル）。コードの既定は localhost | 本番の話者・速度の設定をローカルで再現できるかの確認 |
| Secret | Secret Manager（CI が Cloud Run に注入） | `SECRET_BACKEND=env` が既定（`backend/utils/secrets.py:188`） | 値の置き場を、環境変数を注入する方式へ移す |
| イベント KB 同期 | Cloud Run job と Cloud Scheduler（毎日 09:00 JST） | `--ics-file` 対応の CLI、systemd timer の雛形（`infra/systemd/`）、GitHub Actions の雛形（`.github/workflows/event-kb-sync.example.yml`） | 実行機での定期実行の方法 |
| 監視 | Cloud Monitoring（`infra/terraform/`） | compose の OTel / Loki / Prometheus / Grafana（`docker-compose.yml:87-176`） | なし |

代替が無いもの:

- **engineercafe-device**（`backend/engineercafe-device/`）: ファームウェアが HTTPS と CA のピン留めで webhook に接続する前提になっている（`secrets.example.h:5` は `https://YOUR_SERVICE.run.app/...`）。ローカル運用では、デバイスから届く HTTPS の口（ローカル CA かトンネル）の設計が要る（D3）
- **施設の外からのアクセス**: ローカル運用では外部公開の口が無くなる（D3）

### 3.4 使えなくなった workflow とスクリプト

- `ci.yml` の `backend-deploy-staging`（533 行〜）: `GCP_SA_KEY` で認証し、Cloud Run のサービス・job・Scheduler をデプロイする。`ci-success` の必須条件（1046-1051 行）
- `ci.yml` の `frontend-playwright-voice-live`（223-316 行）: 本番バックエンドに対して実行する。`ci-success` の needs に入っている（1012 行）
- `ci.yml` の `frontend-timeout-guard`: `scripts/validate-p0-cloudrun-vercel-timeouts.mjs` が、`ci.yml` に Cloud Run のデプロイフラグがあることを要求している
- `voice-e2e-nightly.yml`: 毎日の cron で本番バックエンドへ。失敗時は Issue を起票する
- `ragas-evaluation.yml`: 週次の cron で live-api モード（2026-09-07 以降、既に失敗が続いている）
- `alpha-live-verification.yml`（手動実行）、`terraform-plan.yml`（infra の PR と手動実行）
- スクリプト: Secret Manager を読む 8 本（`scripts/alpha-quality-gates.sh` ほか）、`gcloud logging read` を使う 5 本、`scripts/verify-deployment.sh`
- IaC: `infra/terraform/`（監視・ログベースのメトリクス・Secret のコンテナ）

## 4. 論点と回答（2026-09-27）

| ID | 論点 | 回答 |
| --- | --- | --- |
| D1 | RAG のベクトル検索 | コード上は Supabase の経路を残す（今後も使う）。ただし Supabase プロジェクトは一旦削除する（削除前に DB をダンプして非公開の場所に保管） |
| D2 | LLM | コード上は Ollama と OpenRouter の両方を残し、環境変数で切り替える |
| D3 | 施設外アクセスとデバイス | コード上はオンサイト専用と HTTPS の口の両方の経路を残す |
| D4 | 実行機 | 未定。先に GCP の課金を止める |

D1 の帰結: Supabase を削除している間は、既定の RAG（Supabase の RPC）が動かない。ローカル運用では `RAG_VECTOR_BACKEND=local-pgvector` を使う。このときの検索先は `knowledge_base` ではなく `knowledge_embeddings`（`backend/tools/local_rag.py` が呼ぶ `search_knowledge_base_local`、`backend/scripts/sql/local_rag_schema.sql`）なので、ダンプの `knowledge_base` 886 行を `knowledge_embeddings` へ変換し、件数を照合する必要がある（Phase 3 の PR-6）。KB の埋め込みを作ったモデルとローカルの埋め込みモデルが違う場合は、再埋め込みも要る。

Supabase を使うのは RAG だけではない。ナレッジの CRUD API（`backend/api/knowledge.py`）、受付セッションの保存（`backend/utils/reception_repository.py`）、イベント KB の同期（`backend/scripts/sync_event_kb.py` と `backend/services/event_kb_sync.py`）も Supabase の API を直接呼ぶ。ダンプをローカルの PostgreSQL に戻しても Supabase の API は提供されないので、これらは移行するか、対象外として止めて確かめる（PR-6・PR-7）。

## 5. 実装順の提案（PR の粒度）

**Phase 0 — 運用のノイズを止める（コード変更なし・可逆）**

- 0-1 **（2026-09-27 実施済み）** `voice-e2e-nightly.yml` を無効化した（戻すときは `gh workflow enable voice-e2e-nightly.yml -R EngineerCafeJP/engineercafe-navigator`）
- 0-2 **（2026-09-27 実施済み）** `ragas-evaluation.yml` を無効化した（同上）
- 0-3 **（2026-09-27 実施済み）** Secret Manager にある secret のうち、GCP と無関係な実値 9 件を環境変数の管理先へ移し（値の一致をハッシュで確認）、残りは GCP プロジェクトごと削除した（次に GCP を使うときに作り直す）
- 0-4 **（2026-09-27 実施済み）** Supabase の DB をダンプしてから（`public` と `supabase_migrations`、`knowledge_base` 886 行を照合）、Supabase プロジェクトを削除した（D1）
- 0-5 **（2026-09-27 実施済み）** `frontend-production-smoke.yml`（develop への push で、本番のフロント→バックエンドの疎通を確かめる）を無効化した。戻すときは `gh workflow enable frontend-production-smoke.yml -R EngineerCafeJP/engineercafe-navigator`
- 0-6 Vercel の Production をメンテナンス表示にする（#953。`MAINTENANCE_MODE`、`frontend/README.md` の「メンテナンス表示」）
- 0-7 （人間の作業、#953 のマージ後）Vercel の Production から、停止したサービスの値（`BACKEND_API_URL`・`BACKEND_API_KEY`・`NEXT_PUBLIC_SUPABASE_URL`・`NEXT_PUBLIC_SUPABASE_ANON_KEY`）を消す。メンテナンス表示の間は、ビルド時と起動時の必須チェックがこれらを求めない

**Phase 1 — `ci:` CI から GCP を外す**（`.github/workflows` の変更なので、H5 の guard マーカーが要る）

- PR-1 `ci:` `backend-deploy-staging` と `frontend-playwright-voice-live` を削除し、`ci-success` の該当条件を外す（#954）。当初は 2 本に分けていたが、`ci.yml` は CI の path filter で frontend の変更として扱われるため、先に出した方の PR で残った方の `frontend-playwright-voice-live` が停止済みのバックエンドに接続して落ち、`ci-success` も落ちてマージできない（`.github/workflows/ci.yml` の paths-filter と `ci-success`）。そのため 1 本にまとめた。timeout validator（`scripts/validate-p0-cloudrun-vercel-timeouts.mjs`）が `ci.yml` に求めていたデプロイフラグの確認も、同じ PR で外した
- PR-3 `ci:` `alpha-live-verification` / `terraform-plan` / `voice-e2e-nightly` / `ragas-evaluation` の live 部分を削除するか、ローカル向けにする

**Phase 2 — `refactor:` 運用スクリプト**

- PR-4 `refactor:` Secret Manager を読む 8 本を、環境変数から読むように変え、既定の URL を localhost にする
- PR-5 `refactor:` `gcloud logging read` を使う 5 本を、ローカルの Loki の参照に置き換えるか、退役させる

**Phase 3 — `feat:` ローカル本番構成**（D1〜D4 の回答が前提）

- PR-6 `feat:` デモ構成を土台に、常用の compose プロファイルを作る。LLM（Ollama / OpenRouter）と RAG（Supabase / `local-pgvector`）はどちらも残して環境変数で切り替え（D1・D2）、warmup を同梱する。環境変数の切り替えだけでは起動しないので、次も含める
  - 起動時の検証を構成に合わせる。今は production で `openrouter_api_key` と Supabase の 3 つを無条件に必須にしている（`backend/utils/env_validator.py` の `REQUIRED_PRODUCTION`）
  - ローカル検索のときは Supabase のクライアントを作らない。今は `EnhancedRAGSearch.__init__` が常に `create_client` を呼ぶ（`backend/tools/enhanced_rag.py`）
  - ダンプの `knowledge_base` を `knowledge_embeddings` へ変換する手順（必要なら再埋め込み）と、886 行の件数照合
  - ナレッジの CRUD API（`backend/api/knowledge.py`）と受付セッションの保存（`backend/utils/reception_repository.py`）を、ローカルの保存先へ移すか、ローカル構成では止めて確かめる
  - 環境変数の注入方法を含む起動手順書
- PR-7 `feat:` イベント KB 同期をローカルで動かす。定期実行（launchd か systemd timer）に替えるだけでは動かない。今の同期は Supabase の URL とキーを必須にし（`backend/scripts/sync_event_kb.py`）、Supabase の API で `knowledge_base` に書き込む（`backend/services/event_kb_sync.py`）ので、ローカルの検索先（`knowledge_embeddings`）へ書く経路も含める
- PR-8 `feat:` デバイス用の HTTPS の口（D3 の回答による）

**Phase 4 — `chore:` / `docs:` 片付け**

- PR-9 `chore:` `infra/terraform/` と、未使用の `frontend/package-lock.json` を削除する
- PR-10 `docs:` `docs/DEPLOYMENT.md`・`docs/setup-guide.md`・`CLAUDE.md` などの GCP 前提の記述を更新する

## 6. 計画全体の完了条件

- GCP の資格情報なしで、実行機で起動・会話・音声応答・イベントの質問ができる（PR-6 の手順書どおりに実機で確認する）
- develop への push で、CI が GCP を参照せずに green になる
- `git grep -nE "aipartner-426616|gcloud secrets" origin/develop -- ':!docs' ':!*.md'` の結果が 0 件（2026-09-27 時点は 61 件）
