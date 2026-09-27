# ローカル運用への移行計画（GCP 停止後）

- 作成: 2026-09-27
- 対象: `origin/develop` @ `eaf3d323`（2026-08-11）
- 状態: **提案（承認待ち）**。承認前に大きなコード変更はしない
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
   - `voice-e2e-nightly.yml`（毎日 03:17 JST）は本番バックエンドに対して走り、失敗すると Issue を自動で起票する（`voice-e2e-nightly.yml:130-137`）。直近の成功は 2026-09-26 の実行で、次回から毎日失敗する見込み

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

## 4. 決めてほしいこと

| ID | 論点 | 選択肢 |
| --- | --- | --- |
| D1 | RAG のベクトル検索 | Supabase を続ける / `local-pgvector` に移す |
| D2 | LLM | Ollama（完全ローカル）/ OpenRouter を続ける（GCP ではないクラウド API） |
| D3 | 施設外アクセスとデバイス | オンサイト専用にする / トンネルなどで HTTPS の口を作る |
| D4 | 実行機 | どのローカル機で常時動かすか |

## 5. 実装順の提案（PR の粒度）

**Phase 0 — 運用のノイズを止める（コード変更なし・可逆）**

- 0-1 `voice-e2e-nightly.yml` を無効化する（`gh workflow disable voice-e2e-nightly.yml -R EngineerCafeJP/engineercafe-navigator`。戻すときは `enable`）
- 0-2 `ragas-evaluation.yml` を無効化する（同上）
- 0-3 課金停止を予定している Secret Manager から、ローカル運用で使う secret を環境変数の管理先へ移す。課金停止の後は、課金を戻すまで取り出せなくなるため、順番を守る

**Phase 1 — `ci:` CI から GCP を外す**（`.github/workflows` の変更なので、H5 の guard マーカーが要る）

- PR-1 `ci:` `backend-deploy-staging` と `ci-success` の該当条件を削除し、timeout validator の Cloud Run 前提を外す
- PR-2 `ci:` `frontend-playwright-voice-live` を compose のローカルバックエンドで回すか、`ci-success` から外す
- PR-3 `ci:` `alpha-live-verification` / `terraform-plan` / `voice-e2e-nightly` / `ragas-evaluation` の live 部分を削除するか、ローカル向けにする

**Phase 2 — `refactor:` 運用スクリプト**

- PR-4 `refactor:` Secret Manager を読む 8 本を、環境変数から読むように変え、既定の URL を localhost にする
- PR-5 `refactor:` `gcloud logging read` を使う 5 本を、ローカルの Loki の参照に置き換えるか、退役させる

**Phase 3 — `feat:` ローカル本番構成**（D1〜D4 の回答が前提）

- PR-6 `feat:` デモ構成を土台に、常用の compose プロファイルを作る（LLM・埋め込み・RAG・TTS の切替を固定し、warmup を同梱）。環境変数の注入方法を含む起動手順書を付ける
- PR-7 `feat:` イベント KB 同期を、実行機の定期実行（launchd か systemd timer）で動かす
- PR-8 `feat:` デバイス用の HTTPS の口（D3 の回答による）

**Phase 4 — `chore:` / `docs:` 片付け**

- PR-9 `chore:` `infra/terraform/` と、未使用の `frontend/package-lock.json` を削除する
- PR-10 `docs:` `docs/DEPLOYMENT.md`・`docs/setup-guide.md`・`CLAUDE.md` などの GCP 前提の記述を更新する

## 6. 計画全体の完了条件

- GCP の資格情報なしで、実行機で起動・会話・音声応答・イベントの質問ができる（PR-6 の手順書どおりに実機で確認する）
- develop への push で、CI が GCP を参照せずに green になる
- `git grep -nE "aipartner-426616|gcloud secrets" origin/develop -- ':!docs' ':!*.md'` の結果が 0 件（2026-09-27 時点は 61 件）
