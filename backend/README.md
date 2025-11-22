# Engineer Cafe Navigator Backend

Python版LangGraphを使用したAIエージェントバックエンドシステムです。

## 📋 目次

- [セットアップ](#セットアップ)
- [環境変数の設定](#環境変数の設定)
- [実行](#実行)
- [プロジェクト構造](#プロジェクト構造)
- [開発](#開発)
- [テスト](#テスト)
- [APIエンドポイント](#apiエンドポイント)

## セットアップ

### Poetryを使用する場合

```bash
cd backend
poetry install
poetry shell
```

### pipを使用する場合

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 環境変数の設定

`.env.example`をコピーして`.env`を作成：

```bash
cp .env.example .env
# .envを編集して必要なAPIキーを設定
```

必須の環境変数：
- `OPENAI_API_KEY`: OpenAI APIキー（埋め込みベクトル用）
- `GOOGLE_API_KEY`: Google Gemini APIキー（応答生成用）
- `SUPABASE_URL`: Supabase URL
- `SUPABASE_KEY`: Supabase キー

詳細は`.env.example`を参照してください。

## 実行

### 開発サーバーの起動

```bash
poetry run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

または

```bash
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## プロジェクト構造

```
backend/
├── agents/              # LangGraphエージェント
│   ├── __init__.py
│   ├── router_agent.py  # ルーターエージェント（実装予定）
│   ├── business_info_agent.py  # 営業情報エージェント（実装予定）
│   └── ...
├── workflows/           # LangGraphワークフロー
│   ├── __init__.py
│   └── main_workflow.py  # メインワークフロー
├── tools/               # エージェントツール
│   ├── __init__.py
│   ├── rag_tools.py     # RAG検索ツール（実装予定）
│   ├── ocr_tools.py     # OCR処理ツール（実装予定）
│   └── ...
├── models/              # データモデル・型定義
│   ├── __init__.py
│   ├── types.py         # 共通型定義（WorkflowState等）
│   └── agent_response.py  # エージェント応答モデル
├── utils/               # 共通ユーティリティ
│   ├── __init__.py
│   ├── logger.py        # ロギングユーティリティ
│   ├── error_handler.py  # エラーハンドリング
│   └── language_processor.py  # 言語処理
├── config/              # 設定管理
│   ├── __init__.py
│   └── settings.py      # アプリケーション設定
├── tests/               # テスト
│   ├── __init__.py
│   ├── conftest.py      # pytest設定
│   ├── agents/          # エージェントテスト
│   ├── workflows/       # ワークフローテスト
│   └── integration/     # 統合テスト
├── examples/            # 実装例
│   ├── __init__.py
│   └── basic_agent_example.py  # 基本的なエージェント実装例
├── main.py              # FastAPIアプリケーション
├── requirements.txt     # 依存関係
├── pyproject.toml       # Poetry設定
├── pytest.ini          # pytest設定
└── .env.example        # 環境変数テンプレート
```

## 開発

### コードスタイル

```bash
# フォーマット
black backend/

# リンター
ruff check backend/

# 型チェック
mypy backend/
```

### 新しいエージェントの追加

1. `agents/{agent_name}_agent.py`を作成
2. `workflows/main_workflow.py`に統合
3. テストを`tests/agents/test_{agent_name}_agent.py`に追加

実装例は`examples/basic_agent_example.py`を参照してください。

## テスト

### テストの実行

```bash
# すべてのテスト
pytest tests/

# 単体テストのみ
pytest tests/ -m unit

# カバレッジ付き
pytest tests/ --cov=backend --cov-report=html
```

### テストカバレッジ

目標: 80%以上

## APIエンドポイント

### `GET /health`

ヘルスチェック

**Response:**
```json
{
  "status": "ok",
  "service": "engineer-cafe-navigator-backend"
}
```

### `POST /api/chat`

チャットエンドポイント

**Request:**
```json
{
  "query": "営業時間は何時ですか？",
  "session_id": "session-123",
  "language": "ja",
  "context": {}
}
```

**Response:**
```json
{
  "answer": "営業時間は9:00〜22:00です。",
  "emotion": "relaxed",
  "metadata": {
    "agent": "BusinessInfoAgent",
    "category": "business"
  }
}
```

### `POST /api/agent/invoke`

LangGraphエージェントの直接実行

**Request:**
```json
{
  "query": "営業時間は何時ですか？",
  "session_id": "session-123",
  "language": "ja",
  "context": {}
}
```

**Response:**
```json
{
  "status": "success",
  "result": {
    "answer": "営業時間は9:00〜22:00です。",
    "emotion": "relaxed",
    "metadata": {}
  }
}
```

## 参考資料

- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [開発標準](../docs/migration/DEVELOPMENT-STANDARDS.md)
- [コードレビューガイド](../docs/migration/CODE-REVIEW-GUIDE.md)
