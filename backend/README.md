# Engineer Cafe Navigator Backend

Python + FastAPI + LangGraph 1.0.8 を使用したAIエージェントバックエンドシステムです。

## 🤖 実装済みエージェント（12種）

| エージェント | ファイル | 責務 |
|-------------|----------|------|
| OrchestratorAgent | `orchestrator_agent.py` | Supervisor Pattern によるルーティング（LLM動的ルーティング） |
| BusinessInfoAgent | `business_info_agent.py` | 営業時間・料金・アクセス |
| FacilityAgent | `facility_agent.py` | 設備・Wi-Fi・地下施設 |
| EventAgent | `event_agent.py` | カレンダー・Connpassイベント |
| SlideAgent | `slide_agent.py` | スライド表示・ナレーション |
| GeneralKnowledgeAgent | `general_knowledge_agent.py` | Web検索 + メモリクエリ（範囲外質問） |
| ClarificationAgent | `clarification_agent.py` | 曖昧解消 |
| VoiceAgent | `voice_agent.py` | TTS（VoiceVox/Google） |
| STTAgent | `stt_agent.py` | STT（Vosk/Google） |
| CharacterControlAgent | `character_control_agent.py` | VRM制御 |
| OCRAgent | `ocr_agent.py` | OCR処理 |
| MemoryAgent | `memory_agent.py` | **DEPRECATED** → GeneralKnowledgeAgent に統合 |

**テスト状況**: 1166件収集 ✅（2026-02-16）

## セットアップ

### 方法1: Dockerを使用する場合（推奨）

ローカル開発環境をDockerで起動します。PostgreSQLも同時に起動されるため、LangGraph Checkpointerのテストも可能です。

```bash
# プロジェクトルートで実行
docker-compose up -d

# バックエンドのみ起動
docker-compose up -d backend postgres
```

### 方法2: uvを使用する場合（推奨）

[uv](https://github.com/astral-sh/uv) は高速なPythonパッケージマネージャーです。プライマリパッケージマネージャーとして使用します。

```bash
cd backend

# uvでインストール
uv pip install -e ".[dev]"

# または uv sync を使用
uv sync
```

### 方法3: Poetryを使用する場合

```bash
cd backend
poetry install
poetry shell
```

### 方法4: pipを使用する場合

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### ローカルPostgreSQLセットアップ（LangGraph Checkpointer用）

LangGraph Checkpointerを使用するには、Supabase Local（PostgreSQL含む）を使用します。

```bash
# Supabase CLIをインストール（未インストールの場合）
brew install supabase/tap/supabase

# Supabase Localを起動（PostgreSQL含む）
supabase start

# 起動後に表示される情報:
#   DB URL: postgresql://postgres:postgres@127.0.0.1:54322/postgres
#   API URL: http://127.0.0.1:54321
#   Studio URL: http://127.0.0.1:54323

# .envに接続URIを設定
SUPABASE_URL=http://127.0.0.1:54321
SUPABASE_KEY=<表示されたservice_role key>
SUPABASE_DB_URI=postgresql://postgres:postgres@127.0.0.1:54322/postgres

# 停止する場合
supabase stop
```

## 環境変数の設定

`.env`ファイルを作成し、以下の環境変数を設定してください（`.env.example` を参照）：

```env
# OpenRouter API (Required - Primary AI Provider)
# 統一されたLLMアクセスポイント（ルーティング、QA等すべてのモデルに使用）
# Get your key at: https://openrouter.ai/keys
OPENROUTER_API_KEY=your_openrouter_api_key

# OpenAI API (Optional - Embeddings/Evaluation用)
OPENAI_API_KEY=your_openai_api_key

# Google API (Optional - Gemini Grounding Search用)
GOOGLE_API_KEY=your_google_api_key

# Google Calendar ICS Feed
GOOGLE_CALENDAR_ICAL_URL=your_calendar_ical_url

# Connpass API
CONNPASS_API_KEY=your_connpass_api_key

# Supabase（RAG + Checkpointer）
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
SUPABASE_DB_URI=postgresql://postgres:postgres@127.0.0.1:54322/postgres

# LangSmith（Optional - トレーシング・評価）
LANGSMITH_API_KEY=your_langsmith_api_key

# その他
ENVIRONMENT=development
PORT=8000
APP_URL=http://localhost:3000
```

### フォールバック戦略

OpenRouter APIは自動フォールバック機能を持っています：

1. **HTTPエラー時**（500, 503など）:
   - プライマリモデル失敗 → フォールバックモデルに自動切り替え
   - 例: `GEMINI_3_FLASH` → `GEMINI_2_5_FLASH`

2. **ネットワークエラー時**（タイムアウト、接続エラーなど）:
   - フォールバックモデルを自動的に試行
   - 無限ループ防止のため、フォールバック試行は1回まで

3. **フォールバック回数制限**:
   - 各リクエストで最大1回のフォールバック試行
   - ログ出力でフォールバック発生を記録

詳細は `backend/llm/README.md` を参照してください。

## 実行

### 開発サーバーの起動

```bash
# プライマリ: uv run を使用
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000

# または poetry を使用
poetry run uvicorn main:app --reload --host 0.0.0.0 --port 8000

# または直接実行
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## APIエンドポイント

- `GET /health` - ヘルスチェック
- `POST /api/chat` - チャットエンドポイント
- `POST /api/agent/invoke` - LangGraphエージェントの実行

## テスト

```bash
# 全テスト実行（1166件収集）
uv run pytest
# または
poetry run pytest

# 特定のエージェントテスト
uv run pytest tests/agents/ -v

# ツールテスト
uv run pytest tests/tools/ -v

# カバレッジ付き
uv run pytest --cov=agents --cov=tools --cov=workflows --cov-report=html
```

### 評価テスト（RAGAS + LLM-as-Judge）

マルチエージェントシステム向けのRAGAS評価とLLM-as-Judge評価を実行できます。

```bash
# RAGAS評価パイプライン（Faithfulness, Answer Correctness, Context Relevance）
uv run pytest tests/evaluation/test_ragas_pipeline.py -v

# LLM Judge評価（APIキー必要）
uv run pytest tests/evaluation/test_llm_judge.py -v --run-llm

# ルーティング精度評価
uv run pytest tests/evaluation/test_routing_accuracy.py -v
```

テストデータは実際のエンジニアカフェの公開情報に基づいています。詳細は [tests/fixtures/README.md](tests/fixtures/README.md) を参照してください。

## コード品質

```bash
# リンター（プライマリ: uv run）
uv run ruff check .

# フォーマット
uv run black .

# 型チェック
uv run mypy .

# または poetry を使用
poetry run ruff check .
poetry run black .
poetry run mypy .
```

## プロジェクト構造

```
backend/
├── main.py                 # FastAPIアプリケーション
├── agents/                 # LangGraphエージェント（12種）
│   ├── orchestrator_agent.py     # Supervisor Pattern ルーティング
│   ├── business_info_agent.py    # 営業情報
│   ├── facility_agent.py         # 設備情報
│   ├── event_agent.py            # イベント情報
│   ├── slide_agent.py            # スライド表示
│   ├── general_knowledge_agent.py # Web検索 + メモリクエリ
│   ├── clarification_agent.py    # 曖昧解消
│   ├── voice_agent.py            # TTS
│   ├── stt_agent.py              # STT
│   ├── character_control_agent.py # VRM制御
│   ├── ocr_agent.py              # OCR処理
│   ├── memory_agent.py           # DEPRECATED（GeneralKnowledgeAgentに統合）
│   └── agent_tools.py            # LangChain Tool定義
├── config/                 # 設定・定数
│   ├── routing_constants.py
│   ├── settings.py               # Pydantic BaseSettings
│   └── prompts/                  # プロンプトテンプレート
├── workflows/              # LangGraphワークフロー
│   └── main_workflow.py          # StateGraph + RetryPolicy
├── tools/                  # エージェントツール
│   ├── enhanced_rag.py           # RAG（Supabase + 階層検索 + セクションチャンキング）
│   ├── calendar_service.py       # Google Calendar ICS Feed
│   ├── connpass_service.py       # Connpass API v2
│   ├── web_search.py             # Google Gemini Grounding Search
│   └── tavily_search.py          # Tavily Search
├── llm/                    # LLMプロバイダー抽象化
│   ├── openrouter.py             # OpenRouter APIクライアント
│   └── models.py                 # モデル設定・フォールバック定義
├── utils/                  # ユーティリティ
│   ├── exceptions.py             # カスタム例外階層（AgentSystemError等）
│   ├── input_sanitizer.py        # 入力バリデーション・サニタイズ
│   ├── memory_interface.py       # メモリシステムインターフェース
│   ├── checkpointer.py           # AsyncPostgresSaver シングルトン
│   ├── language_processor.py     # 言語検出・応答言語決定
│   └── clarification_templates.py # 曖昧解消テンプレート
├── evaluation/             # RAGAS評価パイプライン
│   └── ragas_pipeline.py
└── tests/                  # テスト（1166件収集）
    ├── agents/             # エージェントテスト
    ├── tools/              # ツールテスト
    ├── workflows/          # ワークフローテスト
    ├── integration/        # 統合テスト
    ├── evaluation/         # 評価テスト（LLM Judge, RAGAS）
    ├── config/             # 設定テスト
    ├── utils/              # ユーティリティテスト
    └── fixtures/           # テストフィクスチャ・ゴールデンデータセット
```

### 主要機能

#### 1. RetryPolicy（LangGraph）
LLMノードに `RetryPolicy` を適用し、一時的な障害に対する自動リトライを実現（`max_attempts=3`）。

#### 2. ストリーミング対応
`astream()` メソッドでServer-Sent Events（SSE）によるリアルタイム応答をサポート。

#### 3. カスタム例外階層
`AgentSystemError` を基底とするドメイン固有例外（`RoutingError`, `LLMGenerationError`, `MemorySystemError` 等）でエラーハンドリングを標準化。

#### 4. RAGAS評価パイプライン
- **Faithfulness**: 回答の忠実性（コンテキストとの一貫性）
- **Answer Correctness**: 回答の正確性（Ground Truthとの比較）
- **Context Relevance**: コンテキストの関連性（質問との適合度）

#### 5. Enhanced RAG（強化版RAG）
- **セクションチャンキング**: ドキュメントを意味的なセクションに分割
- **カテゴリ別検索戦略**: カテゴリごとに最適な検索パラメータを適用
- **適応的閾値調整**: クエリタイプに応じた類似度閾値の動的調整
- **階層的検索**: Supabase `pgvector` による高速ベクトル検索

### 共有インフラストラクチャモジュール

| モジュール | 目的 |
|-----------|------|
| `config/routing_constants.py` | ルーティングキーワード、エージェントマッピング、`extract_request_type()` 等のヘルパー関数を集約。全エージェントが共通利用 |
| `config/prompts/` | エージェント固有のプロンプトテンプレート。ロジックとプロンプトを分離し保守性向上 |
| `utils/input_sanitizer.py` | プロンプトインジェクション検出、制御文字除去、長さ制限等のセキュリティ関連バリデーション |
| `utils/exceptions.py` | `AgentSystemError` を基底とするドメイン固有例外階層（`RoutingError`, `LLMGenerationError`, `MemorySystemError` 等） |
| `utils/checkpointer.py` | LangGraph用 `AsyncPostgresSaver` シングルトン（Supabase PostgreSQL使用） |

## 📖 関連ドキュメント

- **[プロジェクト全体ドキュメント](../docs/README.md)** - 全ドキュメント一覧
- **[LangGraph開発ガイド](../docs/development/LANGGRAPH-DEVELOPMENT-GUIDE.md)** - LangGraph開発詳細
- **[エージェント実装ガイド](../docs/development/AGENT-QUICKSTART.md)** - エージェント開発クイックスタート
- **[API仕様](../docs/api/API.md)** - REST API仕様書

