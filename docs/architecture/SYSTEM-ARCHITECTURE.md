# システムアーキテクチャ

> **動線**: [Documentation hub](../README.md) → [ADR 索引](../adr/README.md) → 本書。運用ゲート・数値の正本は [STATUS.md](../STATUS.md)。コマンド・API フロー・CI の硬性制約はルート `CLAUDE.md`。
>
> **ドキュメント基準日**: 2026-05-05。本文とコードが矛盾する場合は **コードと OpenAPI を優先**してください。

## 概要

Engineer Cafe Navigator は、福岡・赤レンガエリアのエンジニアカフェ来館者向けの **多言語ボイス対応 AI 案内**です。ブラウザ／キオスクの Next.js が UI と `/api/*` プロキシを担い、Python FastAPI + LangGraph が会話・RAG・音声・受付ワークフローの **正本ランタイム**です。

Alpha Phase 4 の会話 UX・fast path・identity まわりは [ADR 018](../adr/018-alpha-fast-response-and-assistant-profile-routing.md) を優先します。

## アーキテクチャの層

### 1. フロントエンド層

- **フレームワーク**: Next.js 15（App Router）
- **UI**: React 19 + TypeScript
- **3D アバター**: Three.js（VRM）
- **音声**: Web Audio API（モバイル互換を考慮）

### 2. バックエンド AI / LangGraph 層（Python）

- **オーケストレーション**: LangGraph（Supervisor パターン — OrchestratorAgent が動的ルーティング）
- **API**: FastAPI（async）
- **LLM**: OpenRouter（Gemini 等）および環境フラグに応じた fast 系プロバイダ
- **埋め込み**: OpenAI `text-embedding-3-small`（1536 次元）を **OpenRouter API** 経由で取得し、**Supabase / pgvector** に保存
- **チェックポインタ**: LangGraph AsyncPostgresSaver（PostgreSQL 上の会話状態）
- **リトライ**: LLM 依存ノードに RetryPolicy（例: max_attempts=3）
- **ストリーミング**: `astream()` 等（将来 SSE 拡張と整合）
- **ログ**: エラー経路で構造化ログ（`exc_info` 付与）

### 3. データ層

- **DB**: PostgreSQL + pgvector（Supabase）
- **ベクトル検索**: 1536 次元コサイン類似度
- **RAG**: チャンク戦略・カテゴリ別閾値・親コンテキスト展開など（実装は `enhanced_rag` 系）
- **短期記憶**: エージェントメモリ TTL（例: 約 3 分）などコード準拠

**ナレッジベース**: コーパスは **日本語中心**。英語クエリは埋め込み検索前に日本語へ寄せる **tRAG**、中国語・韓国語はクロスリンガル埋め込みで検索する方針です（詳細は CLAUDE.md・コード）。

### 4. 連携層

- **カレンダー**: Google Calendar（公開 ICS）+ Connpass API v2（福岡イベント）
- **Web 検索**: Tavily 等（**current-info 系意図に限定**して利用）
- **音声**: デプロイ設定に応じて PiperPlus / VoiceVox / Google Cloud などへフォールバック
- **STT**: Qwen 主軸 + Vosk / Google Cloud 等のフォールバック（環境依存）
- **OCR**: `POST /api/ocr`（会員証・手書き等）

## 主要コンポーネント

### Enhanced RAG

- Supabase `knowledge_base` と RPC（例: `search_knowledge_base()`、`search_knowledge_base_hierarchical`）による検索
- **親コンテキスト展開**などは `backend/tools/enhanced_rag.py`（`search_hierarchical`、`_expand_parent_context`）を参照
- カテゴリ・閾値は実装および評価パイプラインに依存（固定値の過信は避ける）

### LangGraph の状態

- AsyncPostgresSaver によるスレッド単位の永続化
- 状態スキーマはコードの `ConversationState` 等を正とする

### エージェント構成（概要）

**ワークフロー上の専門エージェント（例）**: 営業情報（BusinessInfo）、施設（Facility）、イベント（Event）、スライド（Slide）、一般知識・Web 検索（GeneralKnowledge）、別れ挨拶（Farewell）など。

**サポート経路**: Voice（TTS 等）、STT、キャラクター制御、OCR など。

**統合・廃止の例**: 旧 RouterAgent は Orchestrator に統合。Clarification はオーケストレータ側のインライン処理に吸収。旧 MemoryAgent は GeneralKnowledge 側に統合された経緯があります。

階層ナレッジの設計議論は [HIERARCHICAL-RAG-ARCHITECTURE.md](./HIERARCHICAL-RAG-ARCHITECTURE.md) にあります。

## データフロー

### 標準チャット（Q&A）

```
ユーザー入力 → Next.js → FastAPI
    → OrchestratorAgent（受付アクティブなら先に受付経路）
    → 専門エージェント（RAG / カレンダー / Web 検索 / スライド等）
    → 応答生成 → フロント（アバター・TTS・UI）
```

### 受付フロー（概要）

```
センサー／ボタン → Welcome UI
    →（任意）POST /api/ocr で visitor_identity
    → POST /api/reception/start（visitor_identity は任意）
    → POST /api/chat または /api/voice
    → MainWorkflow が受付 LangGraph サブグラフを進行
    → 受付完了後は同じ MainWorkflow 内で専門エージェントへルーティング
```

### LangGraph 処理パイプライン（概念）

1. STT（音声入力時）と STT 補正
2. 言語検出・多言語処理
3. OrchestratorAgent — 動的ルート選択、意図抽出、リトライ
4. 専門処理 — Enhanced RAG、ICS/Connpass、fast path（ADR 018）、current-info のみ Web 連携 等
5. 応答生成 — deterministic fast path / fast LLM / ドメイン LLM
6. TTS・リップシンク・キャラクター制御

## 重要な製品要件（ADR 018）

キオスク UX のための identity / help / daily / current-info の経路分離などは [ADR 018](../adr/018-alpha-fast-response-and-assistant-profile-routing.md) を参照。

## 品質・評価・テスト

- **RAGAS** 等のオフライン評価（`pytest` マーカー `ragas` 等）
- **CI**: ルート `CLAUDE.md` のコマンドがゲート

## 設定・環境変数

[development/ENVIRONMENT-VARIABLES.md](../development/ENVIRONMENT-VARIABLES.md)、各 `.env.example`、[DEPLOYMENT.md](../DEPLOYMENT.md) を正とする。

## バックエンド API 早見（2026-05-05 時点）

原則 **Next.js の `/api/*` プロキシ経由**。詳細は OpenAPI `http://localhost:8000/docs` と [backend/README.md](../../backend/README.md)。

| メソッド | パス | 役割（概要） |
|----------|------|----------------|
| GET | `/health` | ヘルスチェック |
| POST | `/api/chat` | メイン Q&A |
| POST | `/api/chat/stream` | ストリーミング |
| POST | `/api/agent/invoke` | エージェント呼び出し |
| GET | `/api/voice` | クエリアクション（例: 対応言語） |
| POST | `/api/voice` | STT/TTS 等（`action` で切替） |
| GET | `/api/calendar` | カレンダー |
| POST | `/api/slides` | スライド／ナレーション |
| POST | `/api/character` | キャラクター制御 |
| POST | `/api/ocr` | OCR |
| POST | `/api/interrupt` | 割り込み |
| — | `/api/reception/*` | 受付 |
| — | `/api/knowledge/*`, `/api/stt-vocabulary/*` | ナレッジ・語彙 |

**誤記防止**: `/api/marp`（FE の Marp→HTML）と `/api/slides`（BE）は **別用途**（`CLAUDE.md`）。

## デプロイ要件（概要）

- Frontend: Node.js 24 系・Next.js 15（Vercel 想定）
- Backend: Python 3.11+・Cloud Run 想定
- DB: PostgreSQL + pgvector
- HTTPS は音声・ブラウザ制約のため必須

---

## 参照

- [Documentation hub](../README.md)
- [STATUS.md](../STATUS.md)
- [DEPLOYMENT.md](../DEPLOYMENT.md)
- [API（日本語）](../api/API-ja.md)
