# Engineer Cafe Navigator — 総合リファクタリング計画（ドキュメントのみ）

**作成日**: 2026-05-05  
**更新**: 2026-05-08 — Post-alpha 実行注記を追加。2026-05-05 — §3A を追加し、`main.py` / `main_workflow.py` のファイル単位・PR 粒度まで具体化。
**スコープ**: 現行実装を **変更しない** 前提での調査結果と、今後の改善計画の整理  
**正本との関係**: 運用上の優先判断は引き続き [`docs/STATUS.md`](../STATUS.md)、[ADR 018](../adr/018-alpha-fast-response-and-assistant-profile-routing.md)、および実装コードを優先する。

---

## 1. 目的と境界

### 1.1 目的

- フロントエンド／バックエンド／ドキュメント／スクリプト／テスト／CI／GCP／Terraform／Supabase 関連までを横断的に棚卸しし、**安全に段階実施できる** リファクタリングのロードマップを用意する。
- **このファイル作成時点ではコード変更・設定変更を一切行わない**。

### 1.2 非目標（本計画では手を付けない）

- 機能追加・プロンプト改変・RAG 品質そのものの「改善」（別Issue／Remediation と連動）。
- 本番環境の無検証デプロイや、`--set-env-vars` による Cloud Run 全上書き。

### 1.3 Post-alpha 実行注記（2026-05-08）

- 別ロードマップ上の Phase 2 新機能／外部連携拡張は、現時点では優先度を下げる。
- 当面の実行範囲は、既存の voice / STT / TTS / OCR / RAG 品質の hardening と、安全なリファクタリング hygiene に限定する。
- 本書 §5 の Phase 2（`backend/main.py` 分割）は、新機能追加ではなく既存挙動を保つ機械的整理として扱う。

---

## 2. 現状インベントリ（メトリクス）

調査時点のおおよその規模感。


| 領域                  | 観測                                                                                                                                                                                                                                                                  |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| バックエンドエントリ          | `backend/main.py` は **約 1,585 行**。`/health`、`/api/chat`、`/api/chat/stream`、`/api/voice`、カレンダー・スライド・キャラクター等が同一ファイルに集約され、`backend/api/*` ルータは末尾で `include_router`。                                                                                                    |
| LangGraph メインワークフロー | `backend/workflows/main_workflow.py` **約 1,917 行**。Supervisor パターン、受付ゲート、tRAG、ビジョン等多機能が単一モジュール。                                                                                                                                                                     |
| オーケストレータ            | `backend/agents/orchestrator_agent.py` **約 379 行**。                                                                                                                                                                                                                 |
| エージェントモジュール         | `backend/agents/*.py` **13 ファイル**。                                                                                                                                                                                                                                  |
| バックエンドテスト           | `backend/tests/`** に **約 183 個** の `test_*.py`。markers は `pyproject.toml` に集約（`ragas`, `e2e`, `integration`, `slow`, `vision`, `perf`, `adversarial`, `voice_pipeline` 等）。                                                                                          |
| フロントエンド API プロキシ    | `frontend/src/app/api/**/route.ts` **28 ファイル**。共通ユーティリティ [`frontend/src/lib/api/backend-proxy.ts`](../../frontend/src/lib/api/backend-proxy.ts) で `BACKEND_API_URL` / `BACKEND_API_KEY` / タイムアウトを集約。                                                                |
| フロントエンド TS/TSX      | `frontend/src` 配下 **約 190 ファイル**。                                                                                                                                                                                                                                   |
| ミドルウェア              | [`frontend/src/middleware.ts`](../../frontend/src/middleware.ts): `/api/admin`, `/api/cron`, `/api/monitoring` は Bearer、`/api/voice`, `/api/qa`, `/api/character`, `/api/slides`, `/api/reception/*` は UA トレース用マッチ。**新規の機密 API は matcher に明示追加が必要**（README の警告どおり）。 |
| Docker              | [`backend/Dockerfile`](../../backend/Dockerfile): development / production マルチステージ、Vosk・Qwen・翻訳モデル取得、`PYTHONPATH` の symlink パターン。 [`frontend/Dockerfile`](../../frontend/Dockerfile) 別途。                                                                            |
| 依存関係定義              | `backend/requirements.txt` と [`backend/pyproject.toml`](../../backend/pyproject.toml)（Poetry セクション + Hatch + uv dev-deps）の **二重管理**。Makefile は `pip install -r requirements.txt`。                                                                                   |
| Supabase（リポジトリ内）    | [`backend/supabase/migrations/`](../../backend/supabase/migrations/) に **12 個** のマイグレーション SQL（init / RAG / metrics / monitoring / embedding 次元 / hierarchical RAG / reception 系）。リポジトリルートには [`supabase/snippets/create_sensor_events.sql`](../../supabase/snippets/create_sensor_events.sql) のみ。`backend/supabase/migrations` が **schema の単一ソース**として運用されているかを runbook で明文化する余地あり（dashboard 適用差分の検知は `db-schema-drift.yml`）。 |
| Terraform           | [`infra/terraform/`](../../infra/terraform/) にダッシュボード・アラート等 **9 `.tf` ファイル**。`.github/workflows/terraform-plan.yml` が連動。                                                                                                                                            |
| ルートスクリプト            | [`scripts/`](../../scripts/) に検証・スモーク・RAG live・STT・音声パイプライン・P0 タイムアウト検証（`.mjs`）など複数。                                                                                                                                                                                |
| CI ワークフロー           | `.github/workflows/` に `ci.yml`, `alpha-live-verification.yml`, `ragas-evaluation.yml`, `voice-e2e-nightly.yml`, `db-schema-drift.yml`, `frontend-latency-probe.yml`, `frontend-production-smoke.yml`, `terraform-plan.yml` 等。                                      |


---

## 3. 領域別の現状評価とリファクタリング論点

### 3.1 バックエンド — アプリケーション構造

**観察**

- `main.py` が **設定・ミドルウェア・レート制限・多数のエンドポイント実装・内部ヘルパ** を一手に担う「ゴッドファイル」化している。
- 一部ドメインは既に `backend/api/` に抽出済み（knowledge, stt_vocabulary, monitoring, alerts, reception, ocr）だが、voice / chat / calendar / slides / character は `main.py` に残存。
- ワークフロー側は `main_workflow.py` が巨大で、ノード関数・ルーティング・tRAG・状態変換が同居しやすい。

**計画の詳細（行レンジ・ファイル名・PR 順）は [§3A](#3a-具体分割仕様粒度ファイルpr順) に集約した。** ここでは論点のみ。

- **ルータ分割**: 現状の `backend/api/*` には **2 系統のルータパターン**が混在しているため、抽出時はどちらに揃えるかを 1 行目で明示する:
  - **A 系**: `APIRouter(prefix="/api/<domain>")` を内部に持ち、`main.py` 側は `include_router(<router>)`（prefix 引数なし）。例: `reception.py` (`/api/reception`)、`ocr.py` (`/api/ocr`)、`monitoring.py` (`/api/monitoring`)、`alerts.py` (`/api/alerts`)。
  - **B 系**: `APIRouter(tags=[...])` だけを定義し、`main.py` 側で `include_router(<router>, prefix="/api")` を付与。例: `knowledge.py`、`stt_vocabulary.py`。
  - 新規抽出ルータは、ドメイン名がそのままパス先頭に立つもの（calendar / voice / chat / character / slides 等）を **A 系**に揃え、`main.py` 末尾は `include_router` のみに縮小する方針が単純。`dependencies=[Depends(verify_api_key)]` は **A 系では `include_router` 側に付与**する（`backend/main.py:1554-1579` の現行パターンに合わせる）。
- **ワークフロー分割**: `MainWorkflow` を **Mixin／サブモジュールへの移動のみ** から始め、ノードを「素の関数」に落とすかどうかは第2段で判断する（`add_node` は Callable を受け取れるが、`self` 依存の整理コストが大きい）。
- **import エイリアス**: `OrchestratorAgent as RoutingLogicAgent` は実装時にどちらかへ統一し、grep で参照を一括置換する。

---

### 3.2 バックエンド — 依存関係とビルド

**観察**

- `requirements.txt` と `pyproject.toml` / Poetry メタデータの二系統。ズレると Docker とローカルで異なるパッケージ集合になりうる。
- Dockerfile は `requirements.txt` ベース（クラウドビルドの主流）。

**計画**

- **単一ソースに収束**: （案A）`requirements.txt` を CI／Docker の唯一のソースとし、`pyproject.toml` はメタデータ＋ツール設定のみ。（案B）`uv export` 等で `requirements.txt` を生成するパイプラインを CI で強制。
- `Makefile` の `pip install -r requirements.txt` とドキュメント上の Poetry／uv の説明を一致させる。

**検収**: ロックファイルまたは生成物でバージョンが固定され、`Docker build` と `pytest` が同一ロックから復元できること。

---

### 3.3 データベース・Supabase

**観察**

- `CLAUDE.md` では PostgreSQL + pgvector + RPC と記載。リポジトリ内のマイグレーション類が薄く、`scripts/check-db-schema-drift.sh` と `db-schema-drift.yml` がドリフト検知に寄与している前提。
- `ENVIRONMENT-VARIABLES.md` 冒頭で deprecated 記載が残る可能性への注意書きあり。

**計画**

- **スキーマの単一ソースの明示**: Dashboard 管理／別リポジトリ／生成物のどれかを README／RUNBOOK に一文で固定。
- **RPC・テーブル定義の IaC 化検討**: 運用が許せば `supabase/migrations` へ寄せ、レビュー可能な差分にする。
- **環境変数ドキュメントの棚卸し**: `SUPABASE_DB_URI`（チェックポイント）、`SUPABASE_URL`/`SUPABASE_KEY` の役割分担をコード準拠で整理し、`ENVIRONMENT-VARIABLES.md` の deprecated 箇所を段階的に削除または archive へ移動。

---

### 3.4 フロントエンド

**観察**

- `backendFetch` にタイムアウト階層と Issue #696 由来の定数が集約されている（Vercel 120s と Cloud Run 300s の関係は別検証スクリプトと連動）。
- README が `[frontend/README.md](../../frontend/README.md)` で、`src/lib/env.ts` が「権威あるランタイム契約ではない」と明記。
- API ルートが多く、パスの対応関係（`/api/marp` とバックエンド `/api/slides` の違い等）は CLAUDE のクリティカル制約。

**計画（ファイル粒度は [§3A.5](#3a5-frontendnextjsapi-プロキシ)）**

1. **環境変数スキーマ**: サーバー専用 env を Zod で検証するモジュールを追加し、`backend-proxy.ts` が参照する変数名と 1:1 で一致させる。
2. **プロキシファクトリ**: 「JSON POST → `backendFetch` → ステータスそのまま返す」パターンを共通関数化する（例外レスポンス形式も固定）。
3. **middleware**: `matcher` 配列と `isProtectedOperationalRoute` を **同一ソース**（定数配列）から生成し、追加漏れを防ぐ。

**検収**: `pnpm lint && pnpm typecheck && pnpm build`、既存 E2E／単体テスト。

---

### 3.5 テスト戦略

**観察**

- マーカーは整理済みだが、`tests/templates/agent_template.py` に **未実装 TODO のテンプレ** が残っている（教育用かつノイズになりうる）。
- `integration`, `e2e`, `ragas` は外部キー依存。CI の `SUPABASE_DB_URI=postgresql://test:test@localhost:0/test` は実接続試行がありうる（CLAUDE の注意）。

**計画**

- **テストピラミッドの明示**: PR 必須は軽量セット、夜間／手動で heavy／ragas。
- **モック境界の統一**: LLM・外部 HTTP のスタブを共通フィクスチャ化し、フレーク削減。
- **テンプレートの整理**: 未使用なら archive、使用するなら最小実装のサンプル1つに絞る。

---

### 3.6 ドキュメント

**観察**

- `docs/` にアーキテクチャ・ADR・プラン・ステータス・アーカイブが豊富だが、`docs/archive/` と現行ドキュメントで **重複・時系列の読み替え** が必要。
- `docs/architecture/SYSTEM-ARCHITECTURE.md` と CLAUDE.md に類似情報。
- `docs/STATUS.md` が「現在の真理」に近いが更新コストが高い。

**計画**

- **ナビゲーション層の追加**: `docs/README.md`（または既存インデックスの強化）で「読む順番」を定義: STATUS → ADR 018 → アーキテクチャ → 開発ガイド。
- **アーカイブ方針**: 旧計画は `archive/` に閉じ、現行ドキュメントからはリンクのみ。
- **自動生成できる部分**: API 一覧は OpenAPI（FastAPI）からスナップショット生成を検討。

---

### 3.7 スクリプトと運用

**観察**

- `scripts/` に検証・スモーク・live テストが集中。`alpha-*`, `voice-pipeline-*`, `rag-*` など名前が似ており、**どれが CI／手動／証跡用か** が読み取りにくい可能性。
- `gcloud secrets` 参照を含むスクリプトあり（ローカル運用前提）。

**計画**

- [§3A.6](#3a6-scriptssh-初期カタログ案scriptsreadmemd-用) のカタログを `scripts/README.md` に転記し、**初見がどれを叩けばよいか** を一枚にまとめる。
- `fetch_api_key_from_gcloud` 相当の重複は `scripts/lib/gcp-secrets.sh` のような **source 用ファイル** に抽出する（bash のみ、依存追加なし）。

---

### 3.8 CI/CD・GCP・Terraform

**観察**

- `ci.yml`: paths-filter で frontend/backend を分割、P0 タイムアウト検証は `tsx` + `node scripts/validate-p0-cloudrun-vercel-timeouts.mjs`。
- Cloud Run デプロイはコメントアウトまたは条件付きの記述がある（ファイル後半要確認）。本番慣習: `--update-env-vars`。
- `**infra/terraform`**: オブザーバビリティ・アラート。ADR 014/017 と関連。
- **音声・STT**: Dockerfile で Qwen／Vosk／翻訳モデルがイメージに乗る設計。別サービス VoiceVox は CLAUDE に記載。

**計画**

1. **デプロイパスのドキュメント化**: どのブランチが Vercel／Cloud Run に流れるか、Secret Manager のキー対応表。
2. **Terraform と実環境のドリフト確認**: `terraform plan` を定期実行し、手動コンソール変更を検知。
3. **イメージサイズ・レイヤー**: STT モデル分割や別サービス化はパフォーマンス／コールドスタート計画（既存 Qwen Cloud Run 検証ドキュメント）と連動。

---

## 3A. 具体分割仕様（粒度・ファイル・PR 順）

> **行番号**はドキュメント作成時点の `backend/main.py` / `backend/workflows/main_workflow.py` に基づく。**実装着手前に必ず再取得**（`rg -n '^@app\.|^async def |^def ' backend/main.py` 等）。

### 3A.1 粒度ポリシー（リポジトリ共通）


| ルール      | 内容                                                                                                                                             |
| -------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| PR サイズ   | **振る舞い変更なしの移動のみ** を原則とし、1 PR あたり **差分 ~400 行以内**（自動フォーマット除く）を目安。超える場合は「機械的 cut-paste」のみに限定する。                                                  |
| モジュールサイズ | 抽出後の Python ファイルは **200〜600 行** を狙い、単一責任（chat / voice / reception-gate / format 等）。上限超過ならサブパッケージ化。                                             |
| 禁止       | 同一 PR で **リネーム＋ロジック変更**、または **ルータ抽出とワークフロー改変** を混在させない。                                                                                        |
| 検証       | 各 PR 終了時に `ruff check`、`black --check`、`pytest -m "not ragas and not slow"`（対象領域にテストがあれば追加）。フロントは `pnpm lint && pnpm typecheck && pnpm build`。 |


### 3A.2 `backend/main.py` — 現状ブロックと提案ファイル

**A. アプリ組み立て（残す・薄くする）**


| 概ね行       | 内容                                                                                         | 提案モジュール                                                                                            |
| --------- | ------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------- |
| 53–67     | `_float_env`、`REQUEST_TIMING_LOG_THRESHOLD`                                                | `backend/app/env_utils.py`                                                                         |
| 68–151    | `RequestIDMiddleware` / `RequestTimingMiddleware` / `TokenTrackerMiddleware`               | `backend/app/middleware.py`                                                                        |
| 152–231   | `lifespan`                                                                                 | `backend/app/lifespan.py`                                                                          |
| 232–339   | `FastAPI()` 生成、`Limiter` 初期化、`add_middleware`、`verify_api_key`、CORS、`add_security_headers` | `backend/app/factory.py` に「`create_app() -> FastAPI`」として集約し、`main.py` は `app = create_app()` のみでも可 |
| 1548–1585 | `include_router` 群                                                                         | **現状どおり `main.py` 末尾** または `backend/app/routers_registry.py` に一覧だけ退避                               |


**B. ドメインルータ（`main.py` から完全搬出）**

A 系パターン（§3.1 参照）に合わせ `APIRouter(prefix="/api/<domain>", tags=[...])` で抽出し、`dependencies=[Depends(verify_api_key)]` は **`include_router` 側で付与**する（`backend/main.py:1554-1579` の現行慣習に合わせる）。`reception.py` / `ocr.py` / `monitoring.py` / `alerts.py` がこのパターン。


| 概ね行       | 公開パス                                                                | 移動先ファイル（提案）                                                    | 含めるもの                                                                                                                                                           |
| --------- | ------------------------------------------------------------------- | -------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 341–359   | （モデル）                                                               | `backend/api/schemas_chat.py` または `backend/api/chat.py` 内      | `ChatRequest`, `ChatResponse`, `InterruptRequest`                                                                                                               |
| 364–372   | `POST /api/interrupt`                                               | `backend/api/chat.py`                                          | `interrupt_session`                                                                                                                                             |
| 375–590   | （chat 向けヘルパ・`/health` より前）                                          | `backend/api/chat.py` または `backend/services/chat_fast_path.py` | `_run_workflow_with_tracking`, `_build_workflow_payload`, `_general_fast_path_*`, `_try_chat_general_fast_path`, `_request_id_from_request`, `_upstream_status` |
| 591–625   | `GET /health`                                                       | `**backend/api/health.py`**（別 PR でも可）                          | `health_check`。監視専用に分離する場合は chat ルータから除外                                                                                                                        |
| 627–820   | `POST /api/chat`, `POST /api/chat/stream`, `POST /api/agent/invoke` | `backend/api/chat.py`                                          | `chat` (627–747), `chat_stream` (748–793), `invoke_agent` (794–820)                                                                                              |
| 822–968   | `POST /api/voice/filler` + filler 系モデル／ヘルパ                          | `backend/api/voice.py`                                         | `VoiceRequest`/`VoiceResponse` は voice と共有するため **同一ファイル上部** に配置                                                                                                 |
| 969–1135  | `GET /api/voice` と STT/TTS ヘルパ群                                    | 同上 `backend/api/voice.py`                                      | `_get_stt_agent`, `_handle_stt`, `_handle_stt_warmup`, `voice_get_api` 等。**voice POST (1183–1344) と同一ファイルに集約**                                                  |
| 1166–1182 | `GET /api/calendar`                                                 | `**backend/api/calendar.py`**                                  | voice と独立。**別ファイル推奨**（循環 import 防止）                                                                                                                             |
| 1183–1344 | `POST /api/voice`                                                   | `backend/api/voice.py`（上の voice helpers と同一ファイル）              | `voice_api`                                                                                                                                                     |
| 1345–1420 | `POST /api/slides`                                                  | `backend/api/slides.py`                                        | `SlidesRequest` / `SlidesResponse` / `slides_api`                                                                                                               |
| 1422–1547 | `GET/POST /api/character`, `POST /api/character/auto`               | `backend/api/character.py`                                     | キャラクター系モデル＋ハンドラ                                                                                                                                                 |


`**factory.py` 側の注意**: `limiter` と `_rate_limit` はデコレータがルータ関数を参照するため、**(1)** `Limiter` を `app.state` に載せた後にルータモジュールを import するか、**(2)** デコレータを遅延評価するラッパにするか、のどちらかで **ImportError／参照順** を固定する（実装 PR の冒頭で設計コメント必須）。

**推奨 PR 順序（`main.py`）**


| ID    | 内容                                                | 狙い                                          |
| ----- | ------------------------------------------------- | ------------------------------------------- |
| BE-M1 | `middleware.py` + `lifespan.py` + env ヘルパ         | 依存が薄く、挙動がログ／起動のみ                            |
| BE-M2 | `calendar.py` ルータ一本                               | 最短・循環リスク低・即リグレッション確認しやすい                    |
| BE-M3 | `slides.py`                                       | 中規模・voice と独立                               |
| BE-M4 | `character.py`                                    | voice と独立だがタイムアウト設定に注意                      |
| BE-M5 | `chat.py`（モデル＋interrupt＋fast path ヘルパ→最後にエンドポイント） | **最大**・`tests/api/test_chat_api.py` とセットで確認 |
| BE-M6 | `voice.py`（filler→voice GET/POST）                 | STT/TTS・セッション・レート制限が絡むため最後尾が安全              |
| BE-M7 | `factory.py` に `create_app` 集約、`main.py` はエントリのみ  | 任意・BE-M1〜6 が安定してから                          |


### 3A.3 `backend/workflows/main_workflow.py` — 機能塊と提案モジュール

**現状の塊（メソッド単位・概算行幅）**


| 塊         | 主なシンボル                                                                                                                                                   | 行幅の目安 | 提案ファイル                                                                                                                   |
| --------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- | ------------------------------------------------------------------------------------------------------------------------ |
| モジュール先頭   | `_get_trag_client`, `_translate_llm_with_retry`, tRAG 用正規表現・定数                                                                                           | ~160  | `backend/workflows/trag_runtime.py`（クラス外関数のみ）                                                                            |
| 状態型       | `WorkflowStateDict`, `WorkflowContext`                                                                                                                   | 数十行   | `backend/workflows/workflow_state.py`                                                                                    |
| 受付・ゲート    | `_store_reception_session`, `_reception_`*, `_should_bypass_*`, `_active_reception_*`, `_keyword_router_*`, `_input_type_decision` ほか判定系 `@staticmethod` | ~400+ | `backend/workflows/reception_and_precheck.py` **または** `ReceptionGateMixin` を `mixins/reception.py` に                     |
| Vision    | `_vision_node`, `_decode_image_data`                                                                                                                     | ~80   | `backend/workflows/nodes_vision.py`（`MainWorkflow` に delegate する関数として切り出し、第1段は `def vision_node(workflow, state)` 形式でも可） |
| メモリ       | `_memory_loader_node`                                                                                                                                    | ~182  | `backend/workflows/nodes_memory.py`                                                                                      |
| インライン応答   | `_handle_emergency`, `_handle_greeting`, `_handle_clarification`, `_handle_topic_guard`, `_build_routing_payload`                                        | ~210  | `backend/workflows/inline_intent_handlers.py`                                                                            |
| オーケストレーター | `_orchestrator_node`                                                                                                                                     | ~114  | `backend/workflows/nodes_orchestrator.py`                                                                                |
| エージェントノード | `_business_info_node` … `_general_knowledge_node`, `_notify_discord_emergency`                                                                           | ~165  | `backend/workflows/nodes_agents.py`                                                                                      |
| フォーマット    | `_format_response_node`, ネスト関数 `_is_fast_path_memory` / `_write_long_term_memory`, `_should_translate_answer_to_english`                                 | ~290  | `backend/workflows/nodes_format.py`                                                                                      |
| 公開 API    | `_prepare_state`, `_ensure_checkpointer_ready`, `ainvoke_from_reception`, `ainvoke`, `astream`, `close`                                                  | ~275  | `**main_workflow.py` に残す**（エントリポイント固定）または `workflow_invoke.py`                                                           |
| シングルトン    | `get_workflow`, `get_workflow_sync`, `reset_workflow`                                                                                                    | 末尾    | `workflow_singleton.py` へ退避可（循環に注意）                                                                                      |


`**_build_graph`（311 行前後〜）** は **グラフのエッジ一覧が読めるよう `graph_builder.py` に単独設置**するのが理想だが、`add_node` に渡す Callable が `self` バウンドだと **第1段では `MainWorkflow` 内に残す** のが安全。第2段で「ノード Callable をすべてモジュールレベル関数」にし、`MainWorkflow` は依存注入コンテナに縮小する。

**推奨 PR 順序（ワークフロー）**


| ID   | 内容                                                                    |
| ---- | --------------------------------------------------------------------- |
| WF-1 | `workflow_state.py` + `trag_runtime.py`（import のみ差し替え・挙動変更なし）         |
| WF-2 | `nodes_vision.py` + `_decode_image_data` の移動                          |
| WF-3 | `nodes_memory.py`（`_memory_loader_node` のみ）                           |
| WF-4 | `inline_intent_handlers.py`                                           |
| WF-5 | `nodes_orchestrator.py`                                               |
| WF-6 | `nodes_agents.py`                                                     |
| WF-7 | `nodes_format.py`（副作用・LTM 書き込みがあるため単独 PR）                             |
| WF-8 | reception／keyword 判定群を `reception_and_precheck.py` または Mixin へ（最大・最後） |


各 WF-* で `**pytest backend/tests/workflows/`** および `invoke` 経路の統合テストを実行。

### 3A.4 `backend/workflows/reception_workflow.py`

本計画では **ファイルサイズが main に比べ小さい**ため、**機能追加がない限り**後回しでよい。分割する場合は **ノード関数単位**（`greet_visitor`, `hear_purpose`, …）を `backend/workflows/reception/nodes.py` に閉じ、`get_reception_workflow` は `graph.py` に。

### 3A.5 Frontend（Next.js API プロキシ）

**新規ファイル案**


| ファイル                                                | 責務                                                                                                                                     |
| --------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `frontend/src/lib/env/server-runtime.ts`            | `z.object({ BACKEND_API_URL: z.string().url(), ... })` — **Route Handler と middleware で共通利用しない**（middleware は Edge のため）。サーバー Route のみ。 |
| `frontend/src/lib/api/create-json-proxy-handler.ts` | `(backendPath: string, options?: { method; transformBody }) => (req: NextRequest) => Promise<NextResponse>`                            |
| `frontend/src/lib/api/protected-route-prefixes.ts`  | `PROTECTED_OPERATIONAL_PREFIXES` と `UA_TRACE_PATHS` を定数化し、`middleware.ts` がこれを import                                                  |


**ルートのグルーピング（移動イメージのみ・ディレクトリ再編は任意）**


| グループ       | 現状パス例                                                   | 共通化の可否                                        |
| ---------- | ------------------------------------------------------- | --------------------------------------------- |
| Reception  | `reception/`*, `_shared.ts` あり                          | `_shared` を `create-json-proxy-handler` へ段階移行 |
| Admin KB   | `admin/knowledge/`**                                    | 同一バックエンド `/api/knowledge/`* — **ファクトリ化の効果大**  |
| Monitoring | `monitoring/`*                                          | Bearer 保護とセットでプレフィックス定数と一致確認                  |
| 単発         | `qa`, `voice`, `calendar`, `ocr`, `character`, `slides` | 1 ファイルずつファクトリに寄せる                             |


**PR 順**: FE-1 `protected-route-prefixes` + middleware リファクタ → FE-2 `server-runtime.ts` + 1 ルートで試験導入 → FE-3 admin knowledge 群。

### 3A.6 `scripts/*.sh` — 初期カタログ案（`scripts/README.md` 用）


| スクリプト                                      | 目的サマリ                                         | 典型認証／入力                  | 主な利用シーン                      |
| ------------------------------------------ | --------------------------------------------- | ------------------------ | ---------------------------- |
| `validate-p0-cloudrun-vercel-timeouts.mjs` | Vercel・`backend-proxy.ts`・Cloud Run のタイムアウト整合 | ローカルファイルのみ               | **CI**（`ci.yml`）             |
| `alpha-quality-gates.sh`                   | Alpha GO 用 Q/M 等ゲート                           | `API_SECRET_KEY`、ホスト URL | 手動／ワークフロー                    |
| `alpha-smoke.sh`                           | P0 シナリオ.smoke                                 | key / host               | デプロイ直後                       |
| `alpha-smoke-comprehensive.sh`             | 総合 live smoke                                 | key / host               | リリース前                        |
| `check-db-schema-drift.sh`                 | Supabase スキーマドリフト                             | `SUPABASE_`* トークン        | **CI** `db-schema-drift.yml` |
| `cloud-logging-verify.sh`                  | Cloud Logging 構造化ログ検証                         | gcloud / project         | Alpha 証跡                     |
| `onsite-voice-live-proof.sh`               | **実機マイク**証跡                                   | WAV manifest             | 現地                           |
| `welcome-live-preflight.sh`                | Welcome UI・fixture 音声                         | live backend             | デプロイ前                        |
| `voice-pipeline-live-preflight.sh`         | STT→TTS クリティカルパス                              | live                     | GO/NO-GO                     |
| `stt-live-preflight.sh`                    | STT latency ログ分析                              | Logging API              | #658 系                       |
| `profile_stt.sh`                           | `/api/voice` プロファイル                           | key + WAV                | 性能調査                         |
| `rag-api-live-test.sh`                     | `/api/chat` 経由 RAGAS                          | OpenAI + key             | C スイート寄り                     |
| `rag-live-test.sh`                         | Direct RAG + RAGAS                            | OpenAI                   | 評価ハーネス                       |
| `verify-deployment.sh`                     | エンドポイント認証まわり総叩き                               | `API_SECRET_KEY`         | デプロイ後                        |
| `verify-frontend-production.sh`            | Vercel→Cloud Run 実経路                          | prod URL                 | デプロイ後                        |


### 3A.7 テスト／ドキュメントの追随マップ


| 実装 PR               | 追随させるテスト・ドキュメント                                                                                                                 |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| BE-M5 `chat.py`     | `backend/tests/api/test_chat_api.py`、`evaluation/` 内で `/api/chat` を叩くスクリプトの import パスは変更不要（HTTP 層）                              |
| BE-M6 `voice.py`    | `backend/tests/api/test_voice_api.py`, `test_voice_filler_api.py`                                                               |
| BE-M2 `calendar.py` | `backend/tests/api/test_calendar_api.py`                                                                                        |
| WF-*                | `backend/tests/workflows/`**、エージェント統合テストで `MainWorkflow` を直接 import している箇所（`rg MainWorkflow`）                                   |
| FE-*                | `frontend/src/__tests__/`、`e2e/`、`[docs/plans/alpha-ui-e2e-hardening-2026-04-12.md](alpha-ui-e2e-hardening-2026-04-12.md)` のゲート |
| 依存ロック統一             | `backend/Dockerfile`, `Makefile`, `docs/development/DEVELOPER-GUIDE.md`, `CLAUDE.md` のインストール手順                                  |


### 3A.8 Terraform / GCP（ファイル粒度）


| 対象               | 現状                          | 推奨                                                                      |
| ---------------- | --------------------------- | ----------------------------------------------------------------------- |
| アラート・ダッシュボード     | `infra/terraform/*.tf`      | **モジュール分割は任意**（ファイル数が少ないため）。変更時は `terraform plan` を PR 証跡に添付            |
| Cloud Run サービス定義 | リポジトリ外（コンソール／ gcloud）が混在しうる | `**docs/runbook/` にサービス名・リージョン・最小メモリ／タイムアウト表**を 1 ページに固定し Terraform と突合 |


---

---

## 4. 優先度付け（リスクとインパクト）


| 優先  | テーマ                                  | 理由                                         |
| --- | ------------------------------------ | ------------------------------------------ |
| P0  | `main.py` / `main_workflow.py` の分割設計 | 変更コスト・レビュー負荷・バグ混入リスクが最大。着手前にテスト・契約テストを固める。 |
| P0  | 依存関係の単一ソース化                          | 環境差分バグの予防。                                 |
| P1  | フロント env 検証とプロキシ共通化                  | 本番設定ミスの早期検知。                               |
| P1  | ドキュメント索引と STATUS の保守プロセス             | オンボーディングと判断ミス削減。                           |
| P2  | Supabase スキーマのリポジトリ寄せ                | 長期的なレビュー可能性（運用制約次第）。                       |
| P2  | scripts のカタログ化                       | 運用ミス削減。                                    |
| P3  | テンプレート／アーカイブ整理                       | ノイズ低減。                                     |


---

## 5. 推奨フェーズと PR 対応表（実装は各フェーズで別 PR）

### Phase 0 — 準備（コード変更なし〜最小）


| タスク              | 成果物                                                                        |
| ---------------- | -------------------------------------------------------------------------- |
| ADR／Issue／本計画の突合 | Notion または Issue にリンク一覧のみ                                                  |
| HTTP スナップショット表   | `docs/plans/` または runbook に「パス・メソッド・認証要否・代表 200/403/504」を **機械ではなく表形式**で固定 |
| `rg` 基準線         | `main.py` / `main_workflow.py` の定義行リストを一度エクスポートし、リファクタ後の差分比較に使う            |


### Phase 1 — 安全な機械的整理


| ID   | 内容                                                     |
| ---- | ------------------------------------------------------ |
| P1-A | `requirements.txt` 単一ソース化または `uv export` で生成物を CI にゲート |
| P1-B | `scripts/README.md` — §3A.6 を転記し、「CI で動く／動かない」を明示      |
| P1-C | `docs/README.md`（短い索引）— STATUS → ADR 018 → §3A         |


### Phase 2 — バックエンド `main.py`

§3A.2 の **BE-M1 → BE-M7** を順に実施。Calendar → Slides → Character → Chat → Voice の順がリスク低い。

### Phase 3 — バックエンド `main_workflow.py`

§3A.3 の **WF-1 → WF-8** を順に実施。WF-8 は仕様影響が広いため **単独リリース推奨**。

### Phase 4 — フロントエンド

§3A.5 の **FE-1 → FE-3**。

### Phase 5 — データ・インフラ


| ID  | 内容                                                        |
| --- | --------------------------------------------------------- |
| D1  | Supabase: マイグレーションの置き場（Dashboard のみ／CLI）を runbook に一文で決める |
| D2  | Terraform: PR に `terraform plan` テキストを添付する運用ルール化          |


**各フェーズの終了条件**: 該当 PR 群マージ後に **CI 全緑**、かつ Phase 0 の HTTP スナップショット表に **ステータスコードの後退なし**（変更不要なパスは省略可）。

---

## 6. リスクと緩和


| リスク                           | 緩和                                |
| ----------------------------- | --------------------------------- |
| ルータ移動で依存注入や `Depends` の順序が変わる | 小さな PR、エンドポイント単位の移動、契約テスト         |
| LangGraph 状態キーの取り違え           | グラフの単体テスト・固定フィクスチャ                |
| Docker イメージとローカル依存の不一致        | ロック単一ソース                          |
| ドキュメントだけ更新して実装と乖離             | STATUS／コードへのリンクを「二重記載」せず一方を正とする規約 |


---

## 7. この計画書の保守

- 大きな構造変更が完了したら、本ファイルの「現状インベントリ」を更新するか、**完了済みセクションを archive へ移す**。
- 実装着手時は **本ファイルではなく個別 PR／Issue** でトラッキングし、本ファイルはロードマップの概要に留める。

---

## 8. 参照インデックス（調査時に確認した主なパス）


| 種別            | パス                                                                                   |
| ------------- | ------------------------------------------------------------------------------------ |
| バックエンドエントリ    | `backend/main.py`                                                                    |
| ワークフロー        | `backend/workflows/main_workflow.py`, `backend/workflows/reception_workflow.py`      |
| API ルータ（抽出済み） | `backend/api/*.py`                                                                   |
| エージェント        | `backend/agents/*.py`                                                                |
| プロキシ          | `frontend/src/lib/api/backend-proxy.ts`, `frontend/src/app/api/**/route.ts`          |
| ミドルウェア        | `frontend/src/middleware.ts`                                                         |
| CI            | `.github/workflows/ci.yml` ほか                                                        |
| インフラ          | `infra/terraform/*.tf`, `backend/Dockerfile`                                         |
| ステータス・運用      | `docs/STATUS.md`, `docs/setup-guide.md`, `docs/development/ENVIRONMENT-VARIABLES.md` |
| アーキテクチャ       | `docs/architecture/SYSTEM-ARCHITECTURE.md`, ルート `CLAUDE.md`                          |


---

**結論**: 現行コードは機能的に成熟している一方、`**main.py` と `main_workflow.py` の集中度** と **Python 依存の二重管理** が技術的負債の中心にある。本書 §3A で **ファイル名・行ブロック・PR ID** まで落としたので、実装は *BE-M / WF-* / FE-* の順に機械的移動**で進め、挙動変更は別 Issue に切り出すのが最も安全である。
