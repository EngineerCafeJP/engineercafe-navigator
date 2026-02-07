# Engineer Cafe Navigator Backend

Python版LangGraphを使用したAIエージェントバックエンドシステムです。

## 🤖 実装済みエージェント（9種）

| エージェント | ファイル | 責務 |
|-------------|----------|------|
| RouterAgent | `router_agent.py` | クエリルーティング・分類 |
| BusinessInfoAgent | `business_info_agent.py` | 営業時間・料金・アクセス |
| FacilityAgent | `facility_agent.py` | 設備・Wi-Fi・地下施設 |
| EventAgent | `event_agent.py` | イベント・カレンダー |
| SlideAgent | `slide_agent.py` | スライド表示・ナレーション |
| GeneralKnowledgeAgent | `general_knowledge_agent.py` | Web検索（範囲外質問） |
| MemoryAgent | `memory_agent.py` | 会話履歴・コンテキスト |
| ClarificationAgent | `clarification_agent.py` | 曖昧解消 |
| VoiceAgent | `voice_agent.py` | 音声処理（STT/TTS） |
| CharacterControlAgent | `character_control_agent.py` | VRM制御 |

**テスト状況**: 62件全パス ✅

## セットアップ

### 方法1: Dockerを使用する場合（推奨）

ローカル開発環境をDockerで起動します。PostgreSQLも同時に起動されるため、LangGraph Checkpointerのテストも可能です。

```bash
# プロジェクトルートで実行
docker-compose up -d

# バックエンドのみ起動
docker-compose up -d backend postgres
```

### 方法2: uvを使用する場合

[uv](https://github.com/astral-sh/uv) は高速なPythonパッケージマネージャーです。

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

`.env`ファイルを作成し、以下の環境変数を設定してください：

```env
# OpenRouter API (Required - Primary AI Provider)
# All AI models (Router, QA, etc.) use OpenRouter API
# Get your key at: https://openrouter.ai/keys
OPENROUTER_API_KEY=your_openrouter_api_key

# Google API (GeneralKnowledgeAgent用)
GOOGLE_API_KEY=your_google_api_key

# Supabase
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key

# LangSmith（評価・トレーシング）
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_langsmith_api_key
LANGCHAIN_PROJECT=engineer-cafe-navigator

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
poetry run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

または

```bash
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## APIエンドポイント

- `GET /health` - ヘルスチェック
- `POST /api/chat` - チャットエンドポイント
- `POST /api/agent/invoke` - LangGraphエージェントの実行

## テスト

```bash
# 全テスト実行
poetry run pytest

# 特定のエージェントテスト
poetry run pytest tests/agents/test_router_agent.py -v

# カバレッジ付き
poetry run pytest --cov=agents --cov-report=html
```

### 評価テスト（LangChain Evaluations拡張）

マルチエージェントシステム向けのLLM-as-Judge評価とルーティング精度評価を実行できます。

```bash
# 評価テスト全体
poetry run pytest tests/evaluation/ -v

# ルーティング精度評価
poetry run pytest tests/evaluation/test_routing_accuracy.py -v

# LLM Judge評価（APIキー必要）
poetry run pytest tests/evaluation/test_llm_judge.py -v --run-llm
```

テストデータは実際のエンジニアカフェの公開情報に基づいています。詳細は [tests/fixtures/README.md](tests/fixtures/README.md) を参照してください。

## コード品質

```bash
# フォーマット
poetry run black .

# リンター
poetry run ruff check .

# 型チェック
poetry run mypy .
```

## プロジェクト構造

```
backend/
├── main.py                 # FastAPIアプリケーション
├── agents/                 # LangGraphエージェント（9種）
│   ├── __init__.py
│   ├── router_agent.py           # クエリルーティング
│   ├── business_info_agent.py    # 営業情報
│   ├── facility_agent.py         # 設備情報
│   ├── event_agent.py            # イベント情報
│   ├── slide_agent.py            # スライド表示
│   ├── general_knowledge_agent.py # Web検索
│   ├── memory_agent.py           # 会話履歴
│   ├── clarification_agent.py    # 曖昧解消
│   ├── voice_agent.py            # 音声処理
│   └── character_control_agent.py # VRM制御
├── workflows/              # LangGraphワークフロー
│   ├── __init__.py
│   └── main_workflow.py
├── tools/                  # エージェントツール
│   └── ...
├── models/                 # データモデル
│   └── ...
├── utils/                  # ユーティリティ
│   └── ...
└── tests/                  # テスト
    ├── agents/             # エージェントテスト
    ├── evaluation/         # 評価テスト（LangChain Evaluations拡張）
    ├── fixtures/           # テストフィクスチャ・ゴールデンデータセット
    │   └── golden_datasets/  # 実データ（リファレンス資料に基づく）
    └── utils/              # ユーティリティテスト
        └── evaluators/     # 評価器（LLM Judge, ルーティング精度）
```

## 📖 関連ドキュメント

- **[プロジェクト全体ドキュメント](../docs/README.md)** - 全ドキュメント一覧
- **[LangGraph開発ガイド](../docs/development/LANGGRAPH-DEVELOPMENT-GUIDE.md)** - LangGraph開発詳細
- **[エージェント実装ガイド](../docs/development/AGENT-QUICKSTART.md)** - エージェント開発クイックスタート
- **[API仕様](../docs/api/API.md)** - REST API仕様書

